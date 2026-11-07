#!/usr/bin/env python3
"""Install/remove one udev name-compatibility rule for BlueZ's Sony cable pairing."""
import argparse
import json
import os
from pathlib import Path
import subprocess

RULE = Path('/etc/udev/rules.d/71-aroundos-navcon-bluetooth.rules')
STATE = Path('/var/lib/aroundos-navcon')
TEXT = '''# BlueZ 5.82 matches the legacy name; hid-sony prefixes it with Sony.
# Applies only to Sony Navigation Controller 054c:042f over USB.
SUBSYSTEM=="hid", ENV{HID_ID}=="0003:0000054C:0000042F", ENV{HID_NAME}="Navigation Controller"
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'remove'])
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('This one-time Bluetooth compatibility rule requires administrator authentication.')
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = STATE / 'udev-backup.json'
    if args.action == 'install':
        if not backup.exists():
            backup.write_text(json.dumps({'text': RULE.read_text() if RULE.exists() else None}))
            backup.chmod(0o600)
        RULE.write_text(TEXT)
        RULE.chmod(0o644)
    else:
        if not backup.exists(): raise SystemExit('No managed compatibility rule is installed.')
        old = json.loads(backup.read_text())['text']
        if old is None: RULE.unlink(missing_ok=True)
        else: RULE.write_text(old)
        backup.unlink()
    subprocess.run(['udevadm', 'control', '--reload-rules'], check=True)
    for raw in Path('/sys/class/hidraw').glob('hidraw*'):
        device = (raw / 'device').resolve()
        try: details = (device / 'uevent').read_text()
        except OSError: continue
        if 'HID_ID=0003:0000054C:0000042F' not in details: continue
        subprocess.run(['udevadm', 'trigger', '--action=change', str(device)], check=True)
        subprocess.run(['udevadm', 'settle', '--timeout=10'], check=True)
        if args.action == 'install':
            subprocess.run(['udevadm', 'trigger', '--action=add', str(raw.resolve())], check=True)
    print('Sony Navigation Controller Bluetooth compatibility rule ' + ('installed.' if args.action == 'install' else 'removed.'))


if __name__ == '__main__': main()
