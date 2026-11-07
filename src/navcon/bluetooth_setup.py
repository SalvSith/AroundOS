#!/usr/bin/env python3
"""Authorize BlueZ cable pairing only for the attached Sony Navigation Controller."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
import gi
from gi.repository import Gio, GLib
from linux_input import discover

HID_UUID = '00001124-0000-1000-8000-00805f9b34fb'
AGENT_XML = '''<node><interface name="org.bluez.Agent1">
<method name="Release"/>
<method name="RequestPinCode"><arg type="o" direction="in"/><arg type="s" direction="out"/></method>
<method name="RequestPasskey"><arg type="o" direction="in"/><arg type="u" direction="out"/></method>
<method name="DisplayPasskey"><arg type="o" direction="in"/><arg type="u" direction="in"/><arg type="q" direction="in"/></method>
<method name="RequestConfirmation"><arg type="o" direction="in"/><arg type="u" direction="in"/></method>
<method name="RequestAuthorization"><arg type="o" direction="in"/></method>
<method name="AuthorizeService"><arg type="o" direction="in"/><arg type="s" direction="in"/></method>
<method name="Cancel"/>
</interface></node>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--setup', action='store_true', help='Install the scoped compatibility rule via a desktop authentication prompt')
    args = parser.parse_args()
    devices = [d for d in discover() if d['transport'] == 'USB' and d['address']]
    if not devices: raise SystemExit('Connect the Sony Navigation Controller by USB for one-time pairing.')
    addresses = {device['address'].upper() for device in devices}
    if len(addresses) != 1:
        raise SystemExit('Connect just one Sony Navigation Controller while pairing.')
    expected = addresses.pop()
    suffix = '/dev_' + expected.replace(':', '_')
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    path = '/org/aroundos/NavCon/Pairing'
    loop = GLib.MainLoop()
    started = time.monotonic()
    authorized = False
    succeeded = False
    helper = None
    auth_agent = None

    def bluez(obj, interface, method, value=None):
        return bus.call_sync('org.bluez', obj, interface, method, value, None, Gio.DBusCallFlags.NONE, 5000, None)

    def method_call(conn, sender, obj, iface, method, params, invocation):
        nonlocal authorized
        values = params.unpack()
        if method in ('Release', 'Cancel'):
            invocation.return_value(None)
            return
        allowed = values and values[0].endswith(suffix)
        allowed = allowed and method in ('RequestAuthorization', 'AuthorizeService', 'RequestConfirmation')
        if method == 'AuthorizeService': allowed = allowed and values[1].lower() == HID_UUID
        if allowed:
            authorized = True
            print('Authorized cable pairing for the attached Sony controller.', flush=True)
            invocation.return_value(None)
        else:
            invocation.return_dbus_error('org.bluez.Error.Rejected', 'This setup accepts only the attached Sony controller.')

    registration = bus.register_object(path, Gio.DBusNodeInfo.new_for_xml(AGENT_XML).interfaces[0], method_call, None, None)
    try:
        bluez('/org/bluez', 'org.bluez.AgentManager1', 'RegisterAgent', GLib.Variant('(os)', (path, 'NoInputNoOutput')))
        bluez('/org/bluez', 'org.bluez.AgentManager1', 'RequestDefaultAgent', GLib.Variant('(o)', (path,)))
        # A soft-block can be lifted through the active user's rfkill ACL.
        subprocess.run(['/usr/sbin/rfkill', 'unblock', 'bluetooth'], check=False)
        objects = bluez('/', 'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects').unpack()[0]
        for obj, interfaces in objects.items():
            if 'org.bluez.Adapter1' in interfaces:
                bluez(obj, 'org.freedesktop.DBus.Properties', 'Set', GLib.Variant('(ssv)', ('org.bluez.Adapter1', 'Powered', GLib.Variant('b', True))))
            # A record made by BlueZ 5.82 lacks its cable-pairing marker.
            # Let the built-in plugin redo authorization for this exact device.
            if obj.endswith(suffix) and interfaces.get('org.bluez.Device1', {}).get('Trusted') and not interfaces.get('org.bluez.Device1', {}).get('CablePairing'):
                bluez(obj, 'org.freedesktop.DBus.Properties', 'Set', GLib.Variant('(ssv)', ('org.bluez.Device1', 'Trusted', GLib.Variant('b', False))))
        if args.setup:
            script = Path(__file__).resolve().parents[2] / 'scripts/navcon-bluetooth-compat.py'
            print('Approve the administrator prompt on the Pi to install the one-device compatibility rule.', flush=True)
            # An SSH-launched process is in a different logind session from
            # the desktop's authentication agent. Register an existing native
            # agent for this session, using the Pi screen for its prompt.
            if os.environ.get('SSH_CONNECTION'):
                auth_agent = subprocess.Popen(['/usr/bin/lxpolkit'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(.6)
            helper = subprocess.Popen(['pkexec', '--disable-internal-agent', '/usr/bin/python3', str(script), 'install'])
        else:
            print('Waiting for cable pairing. Reconnect the USB cable if needed.', flush=True)

        def poll():
            nonlocal succeeded
            if helper and helper.poll() not in (None, 0):
                print('Administrator authentication was cancelled or setup failed.', flush=True); loop.quit(); return False
            if time.monotonic() - started > 150:
                print('Pairing timed out. Keep USB connected and retry setup.', flush=True); loop.quit(); return False
            objects = bluez('/', 'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects').unpack()[0]
            for obj, interfaces in objects.items():
                device = interfaces.get('org.bluez.Device1', {})
                if not obj.endswith(suffix): continue
                # Require the fixed BlueZ cable-pairing marker as well as the
                # USB-derived address, vendor/product and stored HID record.
                if (device.get('CablePairing') and HID_UUID in device.get('UUIDs', []) and
                        device.get('Modalias', '').lower().startswith('usb:v054cp042f') and
                        (authorized or device.get('Trusted'))):
                    bluez(obj, 'org.freedesktop.DBus.Properties', 'Set', GLib.Variant('(ssv)', ('org.bluez.Device1', 'Trusted', GLib.Variant('b', True))))
                    succeeded = True
                    print('Bluetooth registered. Unplug USB and press PS to connect wirelessly.', flush=True)
                    loop.quit(); return False
            return True
        GLib.timeout_add(500, poll)
        loop.run()
    finally:
        try: bluez('/org/bluez', 'org.bluez.AgentManager1', 'UnregisterAgent', GLib.Variant('(o)', (path,)))
        except GLib.Error: pass
        bus.unregister_object(registration)
        if auth_agent:
            auth_agent.terminate()
            auth_agent.wait(timeout=3)
    return 0 if succeeded else 1


if __name__ == '__main__': sys.exit(main())
