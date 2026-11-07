#!/usr/bin/env python3
"""Request one prepared administrative action through the Pi's password dialog."""
import os
from pathlib import Path
import subprocess
import sys
import time

root=Path(__file__).resolve().parent
actions={'navcon-bluetooth-compat.py':('install','remove'),
         'navcon-pairing-backup.py':('backup',),
         'navcon-hid-diagnostic.py':('capture',)}
actions['navcon-raw-access.py']=('install','remove')
if len(sys.argv)!=3 or sys.argv[2] not in actions.get(sys.argv[1],()):
    raise SystemExit('Choose a NavCon runtime or compatibility helper and its action.')
os.environ.setdefault('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}')
os.environ.setdefault('WAYLAND_DISPLAY','wayland-0')
os.environ.setdefault('DBUS_SESSION_BUS_ADDRESS',f"unix:path={os.environ['XDG_RUNTIME_DIR']}/bus")
os.environ.setdefault('DISPLAY',':0')
agent=None
try:
    if os.environ.get('SSH_CONNECTION'):
        agent=subprocess.Popen(['/usr/bin/lxpolkit'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        time.sleep(.6)
    result=subprocess.run(['pkexec','--disable-internal-agent','/usr/bin/python3',str(root/sys.argv[1]),sys.argv[2]])
finally:
    if agent:agent.terminate();agent.wait(timeout=3)
raise SystemExit(result.returncode)
