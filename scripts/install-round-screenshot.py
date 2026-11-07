#!/usr/bin/env python3
"""Install the Print shortcut without changing other desktop preferences."""
import datetime
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

SOURCE = Path(__file__).resolve().parents[1] / 'src/round-desktop/round_record.py'


def configure(root, source=SOURCE):
    ns = root.tag.split('}')[0] + '}' if '}' in root.tag else ''
    keyboards = root.findall(ns + 'keyboard')
    if not keyboards:
        keyboards = [ET.SubElement(root, ns + 'keyboard')]
    for keyboard in keyboards:
        for key in list(keyboard.findall(ns + 'keybind')):
            if key.get('key', '').casefold() == 'print':
                keyboard.remove(key)
    key = ET.SubElement(keyboards[0], ns + 'keybind', key='Print')
    ET.SubElement(key, ns + 'action', name='None')
    rules = root.find(ns + 'windowRules')
    if rules is None:
        rules = ET.SubElement(root, ns + 'windowRules')
    for rule in list(rules.findall(ns + 'windowRule')):
        if rule.get('title') == 'Recording · AroundOS':
            rules.remove(rule)



def make_mask():
    import cairo
    mask = SOURCE.parent / 'record-mask.png'
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, 1080, 1080)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(0, 0, 0)
    ctx.paint()
    ctx.arc(540, 540, 540, 0, math.tau)
    ctx.set_source_rgb(1, 1, 1)
    ctx.fill()
    surface.write_to_png(str(mask))


def main():
    environment = os.environ.copy()
    if not environment.get('LABWC_PID'):
        pids = subprocess.check_output(
            ['pgrep', '-u', str(os.getuid()), '-x', 'labwc'], text=True).split()
        if len(pids) != 1:
            raise SystemExit('Run in the target desktop session with LABWC_PID set')
        environment['LABWC_PID'] = pids[0]
    rc = Path.home() / '.config/labwc/rc.xml'
    if len(sys.argv) == 3 and sys.argv[1] == 'restore':
        text = Path(sys.argv[2]).read_text()
        ET.fromstring(text)
    elif len(sys.argv) == 1:
        import cairo  # Check the existing runtime before editing configuration.
        if not shutil.which('grim') or not SOURCE.exists():
            raise SystemExit('grim and round_record.py must be installed first')
        make_mask()
        tree = ET.parse(rc)
        root = tree.getroot()
        if '}' in root.tag:
            ET.register_namespace('', root.tag.split('}')[0][1:])
        configure(root)
        ET.indent(root)
        text = ET.tostring(root, encoding='unicode') + '\n'
        backup = Path.home() / '.local/state/aroundos-round' / datetime.datetime.now().strftime('before-screenshot-%Y%m%d-%H%M%S-%f')
        backup.mkdir(parents=True)
        shutil.copy2(rc, backup / 'rc.xml')
        print('Backup:', backup / 'rc.xml')
        autostart = Path.home() / '.config/autostart/aroundos-recording.desktop'
        autostart.parent.mkdir(parents=True, exist_ok=True)
        autostart.write_text('[Desktop Entry]\nType=Application\nName=AroundOS Recording\n'
                             f'Exec=/usr/bin/python3 "{SOURCE}" --daemon\n'
                             'X-GNOME-Autostart-enabled=true\n')
    else:
        raise SystemExit('Usage: install-round-screenshot.py [restore BACKUP_RC_XML]')
    temporary = rc.with_suffix('.xml.screenshot-tmp')
    temporary.write_text(text)
    temporary.replace(rc)
    subprocess.run(['labwc', '--reconfigure'], check=True, env=environment)


if __name__ == '__main__':
    main()
