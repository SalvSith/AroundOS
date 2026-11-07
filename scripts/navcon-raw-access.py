#!/usr/bin/env python3
"""Grant the existing input group read-only access to Sony Navigation reports."""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess

RULE = Path('/etc/udev/rules.d/72-aroundos-navcon-raw.rules')
BACKUP = Path('/var/lib/aroundos-navcon/raw-access-backup.json')
TEXT = '''# NavCon reads the original axes to avoid hid-sony ABS_X aliasing.
# Only Sony Navigation Controller 054c:042f; no raw-device write access.
SUBSYSTEM=="hidraw", KERNELS=="0005:054C:042F.*", GROUP="input", MODE="0640"
SUBSYSTEM=="hidraw", KERNELS=="0003:054C:042F.*", GROUP="input", MODE="0640"
'''


def nodes():
    for raw in Path('/sys/class/hidraw').glob('hidraw*'):
        props = dict(line.split('=', 1) for line in (raw/'device/uevent').read_text().splitlines() if '=' in line)
        ident = props.get('HID_ID')
        if ident in ('0005:0000054C:0000042F', '0003:0000054C:0000042F'):
            yield raw, ident, Path('/dev') / raw.name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'remove'])
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Administrator authentication is required for the device access rule.')
    current = list(nodes())
    if args.action == 'install':
        if not BACKUP.exists():
            BACKUP.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            perms = {}
            for _, ident, path in current:
                st = path.stat()
                perms[ident] = [st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode)]
            BACKUP.write_text(json.dumps({'rule': RULE.read_text() if RULE.exists() else None, 'permissions': perms}))
            BACKUP.chmod(0o600)
        RULE.write_text(TEXT)
        RULE.chmod(0o644)
    else:
        if not BACKUP.exists():raise SystemExit('No managed raw-input access rule to remove.')
        saved = json.loads(BACKUP.read_text())
        if saved['rule'] is None:RULE.unlink(missing_ok=True)
        else:RULE.write_text(saved['rule'])
        for _, ident, path in current:
            uid, gid, mode = saved['permissions'].get(ident, [0, 0, 0o600])
            os.chown(path, uid, gid)
            os.chmod(path, mode)
    subprocess.run(['udevadm', 'control', '--reload-rules'], check=True)
    for raw, _, _ in current:
        subprocess.run(['udevadm', 'trigger', '--action=change', str(raw.resolve())], check=True)
    subprocess.run(['udevadm', 'settle', '--timeout=10'], check=True)
    if args.action == 'remove':BACKUP.unlink()
    print('Sony Navigation Controller read-only raw access ' + ('installed.' if args.action == 'install' else 'removed.'))


if __name__ == '__main__':main()
