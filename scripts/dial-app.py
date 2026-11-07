#!/usr/bin/env python3
"""Install or remove Dial's desktop launcher; no sudo or desktop reconfiguration."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'local-assets/dial-package'
STATE = Path.home() / '.local/state/aroundos-dial'
ENTRY = Path.home() / '.local/share/applications/aroundos-dial.desktop'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'remove'])
    args = parser.parse_args()
    baseline = STATE / 'launcher-backup.json'
    if args.action == 'remove':
        if not baseline.exists():
            raise SystemExit('No managed Dial launcher is installed.')
        old = json.loads(baseline.read_text())
        if old['content'] is None:
            ENTRY.unlink(missing_ok=True)
        else:
            ENTRY.write_text(old['content'])
        baseline.unlink()
        print('Dial launcher removed. Source, package, and browser profile retained.')
    else:
        if not shutil.which('chromium') or not Path('/usr/bin/labwc').exists():
            raise SystemExit('Run this installer on the Raspberry Pi desktop.')
        manifest = json.loads((ASSETS / 'manifest.json').read_text())
        for name, expected in manifest['files'].items():
            if hashlib.sha256((ASSETS / name).read_bytes()).hexdigest() != expected:
                raise SystemExit('Package verification failed: ' + name)
        STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not baseline.exists():
            baseline.write_text(json.dumps({'content': ENTRY.read_text() if ENTRY.exists() else None}))
        ENTRY.parent.mkdir(parents=True, exist_ok=True)
        ENTRY.write_text('\n'.join([
            '[Desktop Entry]', 'Type=Application', 'Name=Dial',
            'Comment=Original circular watch faces — hold to change, swipe down from the top to exit',
            f'Exec=/usr/bin/python3 "{ROOT / "src/dial/app.py"}"',
            f'Icon={ASSETS / "DIAL_thumb.png"}', 'Terminal=false', 'Categories=Utility;Clock;',
            'StartupWMClass=chrome-127.0.0.1__aroundos-dial_-Default', 'StartupNotify=false', ''
        ]))
        print('Installed Dial', manifest['revision'], 'in Apps.')
    if shutil.which('update-desktop-database'):
        subprocess.run(['update-desktop-database', str(ENTRY.parent)], check=True)


if __name__ == '__main__':
    main()
