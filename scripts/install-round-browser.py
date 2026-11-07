#!/usr/bin/env python3
"""Install only Browser, preserving the current desktop and Terminal changes."""
import configparser
import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

HOME = Path.home()
SOURCE = Path(__file__).resolve().parents[1] / 'src/round-desktop/round_browser.py'
FILES = ['.config/labwc/rc.xml', '.local/share/applications/aroundos-browser.desktop', '.config/mimeapps.list',
         '.config/wf-panel-pi/wf-panel-pi.ini']
STATE = HOME / '.local/state/aroundos-round'


def install():
    import gi
    gi.require_version('WebKit2', '4.1')  # Fail before changing any preferences.
    backup = STATE / datetime.datetime.now().strftime('before-browser-%Y%m%d-%H%M%S')
    backup.mkdir(parents=True)
    manifest = {}
    for relative in FILES:
        path = HOME / relative
        manifest[relative] = path.exists()
        if path.exists():
            target = backup / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    entry = HOME / '.local/share/applications/aroundos-browser.desktop'
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text('\n'.join(['[Desktop Entry]', 'Type=Application', 'Name=Browser',
        'Comment=Browse the web on the circular display', 'Icon=web-browser',
        f'Exec=/usr/bin/python3 "{SOURCE}" %U', 'Terminal=false', 'Categories=Network;WebBrowser;',
        'StartupWMClass=aroundos-browser', 'MimeType=x-scheme-handler/http;x-scheme-handler/https;', '']))
    mime = HOME / '.config/mimeapps.list'
    config = configparser.ConfigParser(interpolation=None, strict=False)
    config.optionxform = str
    if mime.exists():
        config.read(mime)
    if not config.has_section('Default Applications'):
        config.add_section('Default Applications')
    for scheme in ('http', 'https'):
        config.set('Default Applications', 'x-scheme-handler/' + scheme, 'aroundos-browser.desktop;')
    mime.parent.mkdir(parents=True, exist_ok=True)
    with mime.open('w') as stream:
        config.write(stream, space_around_delimiters=False)
    panel = HOME / '.config/wf-panel-pi/wf-panel-pi.ini'
    if panel.exists():
        lines = panel.read_text().splitlines()
        for index, line in enumerate(lines):
            if line.startswith('launchers='):
                names = line.split('=', 1)[1].split()
                lines[index] = 'launchers=' + ' '.join('aroundos-browser' if name in ('x-www-browser', 'chromium', 'chromium-browser') else name for name in names)
        panel.write_text('\n'.join(lines) + '\n')
    rc = HOME / '.config/labwc/rc.xml'
    tree = ET.parse(rc)
    root = tree.getroot()
    ns = root.tag.split('}')[0] + '}' if '}' in root.tag else ''
    if ns:
        ET.register_namespace('', ns[1:-1])
    rules = root.find(ns + 'windowRules')
    if rules is None:
        rules = ET.SubElement(root, ns + 'windowRules')
    if not any(rule.get('identifier') == 'aroundos-browser' for rule in rules):
        rule = ET.SubElement(rules, ns + 'windowRule', identifier='aroundos-browser', serverDecoration='no')
        ET.SubElement(rule, ns + 'action', name='Maximize')
    tree.write(rc, encoding='unicode')
    subprocess.run(['update-desktop-database', str(entry.parent)], check=True)
    print('Browser installed. Backup:', backup)
    print('The dock updates next time the panel starts. Browser is available in Apps now.')


def restore(backup):
    backup = Path(backup)
    manifest = json.loads((backup / 'manifest.json').read_text())
    for relative in FILES:
        if relative not in manifest:
            continue
        path = HOME / relative
        if manifest[relative]:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup / relative, path)
        else:
            path.unlink(missing_ok=True)
    subprocess.run(['update-desktop-database', str(HOME / '.local/share/applications')], check=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'restore':
        restore(sys.argv[2])
    elif len(sys.argv) == 1:
        install()
    else:
        sys.exit('Usage: install-round-browser.py [restore BACKUP_DIRECTORY]')
