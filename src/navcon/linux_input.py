"""Read Sony 054c:042f raw reports, retaining an exclusive evdev gamepad grab.

hid-sony can map the unused DS3 Z axis onto ABS_X for Navigation Controllers,
so evdev's horizontal value can be overwritten during an unchanged stick hold.
Decode the same original report bytes as the Mac app instead.
"""
import fcntl
import os
from pathlib import Path
from core import Report

REPORT_BUTTONS = {'l3': (2, 2), 'up': (2, 16), 'right': (2, 32),
                  'down': (2, 64), 'left': (2, 128), 'l2': (3, 1),
                  'l1': (3, 4), 'circle': (3, 32), 'cross': (3, 64), 'ps': (4, 1)}


def ior(number, size):
    return (2 << 30) | (size << 16) | (ord('E') << 8) | number


def decode_report(data):
    # Complete input reports contain both stick axes and the analog L2 byte.
    if len(data) < 19 or data[0] != 1 or data[1] == 0xff:
        return None
    buttons = {name for name, (offset, mask) in REPORT_BUTTONS.items() if data[offset] & mask}
    return Report(data[6], data[7], data[18] / 255, buttons)


def discover():
    result = []
    raw_devices = [(entry, (entry / 'device').resolve())
                   for entry in Path('/sys/class/hidraw').glob('hidraw*')]
    for entry in sorted(Path('/sys/class/input').glob('event*')):
        device = entry / 'device'
        try:
            if int((device / 'id/vendor').read_text(), 16) != 0x054c or int((device / 'id/product').read_text(), 16) != 0x042f:
                continue
            parents = device.resolve().parents
            raw = next((raw for raw, parent in raw_devices if parent in parents), None)
            result.append({'path': '/dev/input/' + entry.name,
                           'raw_path': '/dev/' + raw.name if raw else None,
                           'transport': 'Bluetooth' if int((device / 'id/bustype').read_text(), 16) == 5 else 'USB',
                           'name': (device / 'name').read_text().strip(),
                           'address': (device / 'uniq').read_text().strip()})
        except (OSError, ValueError): pass
    return sorted(result, key=lambda d: d['transport'] != 'Bluetooth')


class Device:
    def __init__(self, info):
        self.info = info
        self.fd = self.evdev_fd = None
        self.events = 0
        self.report = None  # Never arm from a fabricated neutral snapshot.
        try:
            if not info.get('raw_path'):
                raise OSError('Navigation Controller raw input is unavailable')
            try:
                self.fd = os.open(info['raw_path'], os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
            except PermissionError as exc:
                raise PermissionError('NavCon needs its Sony-controller raw-input access rule installed') from exc
            self.evdev_fd = os.open(info['path'], os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
            # Stop other apps from also treating this controller as a gamepad.
            fcntl.ioctl(self.evdev_fd, 0x40044590, 1)  # EVIOCGRAB
        except Exception:
            self.close()
            raise

    def snapshot(self):
        # Full raw reports are authoritative, including every button release.
        return self.report

    def read(self):
        reports = []
        while True:
            try: data = os.read(self.fd, 128)
            except BlockingIOError: break
            if not data: raise OSError('Controller disconnected')
            report = decode_report(data)
            if report is not None:
                self.events += 1
                self.report = report
                reports.append(report)
        return reports

    def close(self):
        if self.evdev_fd is not None:
            try: fcntl.ioctl(self.evdev_fd, 0x40044590, 0)
            except OSError: pass
            os.close(self.evdev_fd)
            self.evdev_fd = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
