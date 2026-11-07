#!/usr/bin/env python3
"""Install/restore just Task Manager without replacing the existing desktop."""
import datetime
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import xml.etree.ElementTree as ET

HOME = Path.home()
ROOT = Path(__file__).resolve().parents[1]
STATE = HOME / '.local/state/aroundos-round'
ENTRY = '.local/share/applications/lxtask.desktop'
CLASSIC_ENTRY = '.local/share/applications/aroundos-classic-task-manager.desktop'
CONFIG = '.config/labwc/rc.xml'
FILES = (ENTRY, CLASSIC_ENTRY, CONFIG)


def reload_compositor():
    result = subprocess.run(['pgrep', '-u', str(os.getuid()), '-x', 'labwc'], capture_output=True, text=True)
    for pid in result.stdout.split():
        os.kill(int(pid), signal.SIGHUP)


def install():
    import gi
    gi.require_version('Gtk', '3.0')
    if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
        raise RuntimeError('Task Manager needs Linux pidfd support.')
    for name in ('round_tasks.py', 'round_processes.py', 'round_ui.py'):
        source = ROOT / 'src/round-desktop' / name
        compile(source.read_text(), str(source), 'exec')
    tree = ET.parse(HOME / CONFIG)
    root = tree.getroot()
    ns = root.tag.split('}')[0] + '}' if '}' in root.tag else ''
    if ns:
        ET.register_namespace('', ns[1:-1])
    rules = root.find(ns + 'windowRules')
    if rules is None:
        rules = ET.SubElement(root, ns + 'windowRules')
    if not any(rule.get('title') == 'Task Manager · AroundOS' for rule in rules):
        rule = ET.SubElement(rules, ns + 'windowRule', title='Task Manager · AroundOS', serverDecoration='no')
        ET.SubElement(rule, ns + 'action', name='Maximize')
    backup = STATE / datetime.datetime.now().strftime('before-tasks-%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True)
    entry = HOME / ENTRY
    manifest = {}
    for relative in FILES:
        path = HOME / relative
        manifest[relative] = path.exists()
        if path.exists():
            target = backup / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    # Extend the general desktop's restore coverage without altering its baseline.
    pointer = STATE / 'original-backup'
    if pointer.exists():
        original = Path(pointer.read_text().strip())
        saved = json.loads((original / 'manifest.json').read_text())
        for relative in FILES:
            path = HOME / relative
            if relative not in saved['files']:
                saved['files'][relative] = path.exists()
                if path.exists():
                    target = original / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
        (original / 'manifest.json').write_text(json.dumps(saved, indent=2))
    entry.parent.mkdir(parents=True, exist_ok=True)
    temporary = entry.with_suffix('.aroundos-tmp')
    temporary.write_text('\n'.join([
        '[Desktop Entry]', 'Type=Application', 'Name=Task Manager',
        'Comment=Processes and system usage for the circular display',
        'Icon=utilities-system-monitor',
        f'Exec=/usr/bin/python3 "{ROOT / "src/round-desktop/round_tasks.py"}"',
        'Terminal=false', 'Categories=GTK;System;Monitor;',
        'StartupWMClass=lxtask', 'Keywords=process;CPU;memory;monitor;', '']))
    temporary.replace(entry)
    (HOME / CLASSIC_ENTRY).write_text('\n'.join([
        '[Desktop Entry]', 'Type=Application', 'Name=Classic Task Manager',
        'Comment=Open the original LXTask process manager',
        'Icon=utilities-system-monitor', 'Exec=lxtask', 'TryExec=lxtask',
        'Terminal=false', 'Categories=GTK;System;Monitor;',
        'Keywords=process;CPU;memory;monitor;LXTask;', '']))
    config_temp = (HOME / CONFIG).with_suffix('.aroundos-tmp')
    tree.write(config_temp, encoding='unicode')
    config_temp.replace(HOME / CONFIG)
    subprocess.run(['update-desktop-database', str(entry.parent)], check=True)
    reload_compositor()
    print('Task Manager installed. Backup:', backup)


def restore(backup):
    backup = Path(backup)
    manifest = json.loads((backup / 'manifest.json').read_text())
    for relative in FILES:
        if relative not in manifest:
            continue
        if manifest[relative]:
            shutil.copy2(backup / relative, HOME / relative)
        else:
            (HOME / relative).unlink(missing_ok=True)
    subprocess.run(['update-desktop-database', str((HOME / ENTRY).parent)], check=True)
    reload_compositor()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'restore':
        restore(sys.argv[2])
    elif len(sys.argv) == 1:
        install()
    else:
        sys.exit('Usage: install-round-tasks.py [restore BACKUP_DIRECTORY]')
