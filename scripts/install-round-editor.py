#!/usr/bin/env python3
"""Register the round editor without restarting the desktop. Run as the Pi user."""
import datetime
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

from gi.repository import Gio

ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
STATE = HOME / '.local/state/aroundos-round'
APPS = Path('.local/share/applications')
EDITOR = APPS / 'aroundos-editor.desktop'
OLD = [APPS / name for name in ('org.xfce.mousepad.desktop', 'org.xfce.mousepad-settings.desktop')]
LABWC = Path('.config/labwc/rc.xml')
PATHS = [LABWC, EDITOR, *OLD, Path('.config/mimeapps.list')]
TYPES = ('text/plain', 'application/x-zerosize', 'text/markdown', 'text/x-log', 'text/x-readme', 'text/x-python',
         'text/x-shellscript', 'text/x-ini', 'text/x-csrc', 'text/x-chdr',
         'application/json', 'application/x-yaml', 'application/toml')


def snapshot(folder, files):
    for path in PATHS:
        if str(path) in files:
            continue
        files[str(path)] = (HOME / path).exists()
        if files[str(path)]:
            (folder / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(HOME / path, folder / path)


def hide_title_bar(path):
    tree = ET.parse(path) if path.exists() else ET.ElementTree(ET.Element('labwc_config'))
    root = tree.getroot()
    ns = root.tag.rpartition('}')[0] + '}' if '}' in root.tag else ''
    if ns:
        ET.register_namespace('', ns[1:-1])
    rules = root.find(ns + 'windowRules')
    if rules is None:
        rules = ET.SubElement(root, ns + 'windowRules')
    title = 'Text Editor * AroundOS'
    rule = rules.find(f"{ns}windowRule[@title='{title}']")
    if rule is None:
        rule = ET.SubElement(rules, ns + 'windowRule', title=title)
    rule.set('serverDecoration', 'no')
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding='utf-8')


def install():
    backup = STATE / datetime.datetime.now().strftime('before-editor-%Y%m%d-%H%M%S-%f')
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
    (HOME / EDITOR).write_text('\n'.join([
        '[Desktop Entry]', 'Type=Application', 'Name=Text Editor', f'Icon={ROOT / "src/round-desktop/dock-icons/round/editor.png"}',
        'Comment=Edit plain text on the round display',
        f'Exec=/usr/bin/python3 "{ROOT / "src/round-desktop/round_editor.py"}" %F',
        'Terminal=false', 'Categories=Utility;TextEditor;', 'StartupWMClass=aroundos-editor',
        'MimeType=' + ';'.join(TYPES) + ';', '']))
    for old in OLD:
        (HOME / old).write_text('[Desktop Entry]\nType=Application\nName=Mousepad\nHidden=true\n')
    subprocess.run(['update-desktop-database', str(HOME / APPS)], check=True)
    editor = Gio.DesktopAppInfo.new(EDITOR.name)
    for mime in TYPES:
        editor.set_as_default_for_type(mime)
    hide_title_bar(HOME / LABWC)
    subprocess.run(['labwc', '--reconfigure'], check=True)
    print('Editor registered. Backup:', backup)


if __name__ == '__main__':
    install()
