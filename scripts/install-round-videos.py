#!/usr/bin/env python3
"""Register the round video player without restarting the desktop. Run as the Pi user."""
import datetime
import json
from pathlib import Path
import shutil
import subprocess
import os
import xml.etree.ElementTree as ET

from gi.repository import Gio

ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
STATE = HOME / '.local/state/aroundos-round'
APPS = Path('.local/share/applications')
ENTRY = APPS / 'aroundos-videos.desktop'
PATHS = [ENTRY, Path('.config/mimeapps.list'), Path('.config/labwc/rc.xml')]
import sys
sys.path.insert(0, str(ROOT / 'src/round-desktop'))
from round_videos import MIME_TYPES as TYPES


def snapshot(folder, files):
    for path in PATHS:
        if str(path) in files:
            continue
        files[str(path)] = (HOME / path).exists()
        if files[str(path)]:
            (folder / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(HOME / path, folder / path)


def configure_window():
    path = HOME / '.config/labwc/rc.xml'
    if not path.exists(): return
    ET.register_namespace('', 'http://openbox.org/3.4/rc')
    tree = ET.parse(path); root = tree.getroot()
    prefix = root.tag.split('}')[0]+'}' if '}' in root.tag else ''
    rules = root.find(prefix+'windowRules')
    if rules is None: rules = ET.SubElement(root, prefix+'windowRules')
    rule = next((r for r in rules if r.get('title') == 'Videos · AroundOS'), None)
    if rule is None: rule = ET.SubElement(rules, prefix+'windowRule', title='Videos · AroundOS')
    rule.set('serverDecoration', 'no')
    if not any(a.get('name') == 'Maximize' for a in rule):
        ET.SubElement(rule, prefix+'action', name='Maximize')
    ET.indent(tree)
    temp = path.with_suffix('.videos-tmp'); tree.write(temp, encoding='unicode'); temp.replace(path)
    result = subprocess.run(['pgrep', '-u', str(os.getuid()), '-x', 'labwc'], capture_output=True, text=True)
    for pid in result.stdout.split():
        subprocess.run(['labwc', '--reconfigure'], env={**os.environ, 'LABWC_PID': pid}, check=True)


def install():
    from round_videos import Gst
    Gst.init(None)
    if not all(Gst.ElementFactory.find(name) for name in ('playbin', 'gtksink')):
        raise SystemExit('Install gstreamer1.0-gtk3 and the codec packages listed in docs/round-desktop/videos.md first.')
    backup = STATE / datetime.datetime.now().strftime('before-videos-%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True)
    manifest = {}
    snapshot(backup, manifest)
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    pointer = STATE / 'original-backup'
    if pointer.exists():
        original = Path(pointer.read_text().strip())
        saved = json.loads((original / 'manifest.json').read_text())
        snapshot(original, saved['files'])
        (original / 'manifest.json').write_text(json.dumps(saved, indent=2))
    (HOME / APPS).mkdir(parents=True, exist_ok=True)
    (HOME / ENTRY).write_text('\n'.join([
        '[Desktop Entry]', 'Type=Application', 'Name=Videos', f'Icon={ROOT / "src/round-desktop/dock-icons/round/photos.png"}',
        'Comment=Play local videos on the round display',
        f'Exec=/usr/bin/python3 "{ROOT / "src/round-desktop/round_videos.py"}" %F',
        'Terminal=false', 'Categories=AudioVideo;Video;Player;', 'StartupWMClass=aroundos-videos',
        'MimeType=' + ';'.join(TYPES) + ';', '']))
    subprocess.run(['update-desktop-database', str(HOME / APPS)], check=True)
    editor = Gio.DesktopAppInfo.new(ENTRY.name)
    for mime in TYPES:
        editor.set_as_default_for_type(mime)
    configure_window()
    print('Videos registered. Backup:', backup)


if __name__ == '__main__':
    install()
