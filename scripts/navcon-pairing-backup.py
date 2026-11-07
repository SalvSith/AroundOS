#!/usr/bin/env python3
"""Back up a locally paired Sony Navigation Controller without restarting Bluetooth."""
import configparser
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys

ADDRESS = re.compile(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', re.IGNORECASE)
BLUETOOTH_STATE = Path('/var/lib/bluetooth')
BACKUPS = Path('/var/lib/aroundos-navcon/pairing-backups')


def controller_records(state):
    for path in sorted(state.glob('*/*/info')):
        if not all(ADDRESS.fullmatch(name) for name in path.parts[-3:-1]):
            continue
        record = configparser.ConfigParser(interpolation=None)
        with path.open() as stream:
            record.read_file(stream)
        modalias = record.get('General', 'Modalias', fallback='').lower()
        device_id = (record.getint('DeviceID', 'Source', fallback=0),
                     record.getint('DeviceID', 'Vendor', fallback=0),
                     record.getint('DeviceID', 'Product', fallback=0))
        if modalias.startswith('usb:v054cp042f') or device_id == (2, 0x054C, 0x042F):
            yield path, record


def main():
    if sys.argv[1:] != ['backup'] or os.geteuid() != 0:
        raise SystemExit('Run as administrator with action backup.')
    os.umask(0o077)
    records = list(controller_records(BLUETOOTH_STATE))
    if len(records) != 1:
        raise SystemExit('Expected exactly one registered Sony Navigation Controller record.')
    info, record = records[0]
    flags = {key: record.getboolean('General', key, fallback=False)
             for key in ('Trusted', 'CablePairing', 'Blocked')}
    if not flags['Trusted'] or not flags['CablePairing'] or flags['Blocked']:
        raise SystemExit('Controller needs a trusted, unblocked cable pairing before backup.')
    controller = info.parent
    adapter = controller.parent
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    BACKUPS.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = BACKUPS / stamp
    partial = BACKUPS / ('.' + stamp)
    partial.mkdir(mode=0o700)
    try:
        shutil.copytree(controller, partial / controller.name)
        cache = adapter / 'cache' / controller.name
        if cache.is_file():
            (partial / 'cache').mkdir(mode=0o700)
            shutil.copy2(cache, partial / 'cache' / controller.name)
        manifest = {'adapter': adapter.name, 'controller': controller.name,
                    'flags': flags, 'source': str(info), 'backup': str(target)}
        (partial / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        partial.rename(target)
    except BaseException:
        shutil.rmtree(partial)
        raise
    print(f'Controller pairing backed up to {target}.')


if __name__ == '__main__':
    main()
