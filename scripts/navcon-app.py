#!/usr/bin/env python3
"""Install/remove the native NavCon launcher; preserve existing profiles."""
import argparse
import json
from pathlib import Path
import subprocess
import os
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
STATE = HOME / '.local/state/aroundos-navcon'
FILES = ['.local/share/applications/aroundos-navcon.desktop', '.config/autostart/aroundos-navcon.desktop']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['install','remove'])
    args=parser.parse_args()
    if not Path('/usr/bin/labwc').exists():raise SystemExit('Run this on the Pi.')
    STATE.mkdir(parents=True,exist_ok=True)
    backup=STATE/'launcher-backup.json'
    rc=HOME/'.config/labwc/rc.xml'
    ET.register_namespace('', 'http://openbox.org/3.4/rc')
    tree=ET.parse(rc);root=tree.getroot();ns=root.tag.split('}')[0]+'}' if '}' in root.tag else ''
    rules=root.find(ns+'windowRules')
    if rules is None:rules=ET.SubElement(root,ns+'windowRules')
    existing=rules.find(f"{ns}windowRule[@title='NavCon · AroundOS']")
    if args.action=='remove':
        if not backup.exists():raise SystemExit('No managed NavCon installation.')
        subprocess.run(['/usr/bin/python3',str(ROOT/'src/navcon/app.py'),'--quit'],check=True)
        for relative,content in json.loads(backup.read_text()).items():
            target=HOME/relative
            if content is None:target.unlink(missing_ok=True)
            else:target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content)
        backup.unlink()
        if (STATE/'managed-window-rule').exists():
            if existing is not None:rules.remove(existing)
            (STATE/'managed-window-rule').unlink()
        print('NavCon stopped and launchers restored. Profiles and source retained.')
    else:
        if not backup.exists():
            backup.write_text(json.dumps({p:(HOME/p).read_text() if (HOME/p).exists() else None for p in FILES}))
        target=HOME/FILES[0];target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text('\n'.join(['[Desktop Entry]','Type=Application','Name=NavCon',
            'Comment=Sony Navigation Controller · mouse, keyboard and profiles',
            f'Exec=/usr/bin/python3 "{ROOT / "src/navcon/app.py"}"','Icon=input-gaming',
            'Terminal=false','Categories=Utility;Settings;','StartupWMClass=aroundos-navcon','StartupNotify=false','']))
        print('NavCon installed in Apps. Start at login is optional in Profiles.')
        if existing is None:
            rule=ET.SubElement(rules,ns+'windowRule',title='NavCon · AroundOS',serverDecoration='no')
            (STATE/'managed-window-rule').touch()
        elif (STATE/'managed-window-rule').exists():
            for action in existing.findall(f"{ns}action[@name='Maximize']"):
                existing.remove(action)
    temp=rc.with_suffix('.navcon-tmp');tree.write(temp,encoding='unicode');temp.replace(rc)
    os.environ.setdefault('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}')
    os.environ.setdefault('WAYLAND_DISPLAY','wayland-0')
    if not os.environ.get('LABWC_PID'):
        pids=subprocess.check_output(['pgrep','-u',str(os.getuid()),'-x','labwc'],text=True).split()
        if len(pids)!=1:raise SystemExit('Expected one active labwc desktop.')
        os.environ['LABWC_PID']=pids[0]
    subprocess.run(['labwc','--reconfigure'],check=True)
    subprocess.run(['update-desktop-database',str(HOME/'.local/share/applications')],check=True)


if __name__=='__main__':main()
