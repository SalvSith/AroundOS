#!/usr/bin/env python3
"""Live circle-layout checks and native Wayland input into a disposable test window."""
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/navcon'))
from app import NavCon,Gtk,Gdk,GLib
from core import mapping
from wayland_input import Output,uint

os.environ.setdefault('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}')
os.environ.setdefault('WAYLAND_DISPLAY','wayland-0')
os.environ.setdefault('DBUS_SESSION_BUS_ADDRESS',f"unix:path={os.environ['XDG_RUNTIME_DIR']}/bus")
Gdk.set_program_class('aroundos-navcon-check')
temp=tempfile.TemporaryDirectory(prefix='navcon-check-')
app=NavCon(False,Path(temp.name)/'profiles.json','org.aroundos.NavConCheck')
failed=False
output=None
events=[]


def check(name,result):
    if not result:raise AssertionError(name)
    print('PASS',name,flush=True)


def geometry(name):
    allocation=app.window.get_allocation()
    check(name+' 1080 × 1080',(allocation.width,allocation.height)==(1080,1080))
    for widget in app.placed:
        if not widget.get_visible():continue
        a=widget.get_allocation();x,y=widget.translate_coordinates(app.window,0,0)
        distance=max(math.hypot(px-540,py-540) for px in (x,x+a.width) for py in (y,y+a.height))
        check(name+' bounds '+widget.__class__.__name__,distance<530)
    path=os.environ.get('NAVCON_SCREENSHOTS')
    if path:
        directory=Path(path);directory.mkdir(parents=True,exist_ok=True)
        subprocess.run(['grim',str(directory/(name+'.png'))],check=True)


def steps():
    global output
    yield
    check('Opens fullscreen',app.window.get_window().get_state() & Gdk.WindowState.FULLSCREEN)
    for name in ['Controller','Buttons','Cursor','Profiles']:
        app.show_page(name);yield
        geometry(name.lower())
    app.editor('circle');yield
    geometry('mapping-editor')
    app.draft=mapping('shortcut',46,[29],'Ctrl+C');app.kind.set_active_id('shortcut');app.save_mapping();yield
    check('Mapping editor saves shortcut',app.store.current['mappings']['circle']['key']==46)
    app.profile_action('duplicate');yield
    check('Duplicate profile',len(app.store.profiles)==2)
    app.profile_action('delete');yield
    check('Delete profile',len(app.store.profiles)==1)
    app.hide_window();yield
    check('Close hides window',not app.window.get_visible())
    app.activate();yield
    check('Activate restores window',app.window.get_visible())
    check('Reopens fullscreen',app.window.get_window().get_state() & Gdk.WindowState.FULLSCREEN)
    # Use only a dedicated entry and event area inside this disposable window.
    for child in app.content.get_children():app.content.remove(child);child.destroy()
    entry=Gtk.Entry();entry.set_size_request(650,70)
    entry.connect('key-press-event',lambda _,e:events.append(('key-down',e.keyval,int(e.state))) or False)
    entry.connect('key-release-event',lambda _,e:events.append(('key-up',e.keyval,int(e.state))) or False)
    app.content.pack_start(entry,False,False,0)
    area=Gtk.EventBox();area.set_size_request(650,240);area.add(Gtk.Label(label='NavCon input test'))
    area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.BUTTON_RELEASE_MASK|Gdk.EventMask.POINTER_MOTION_MASK|Gdk.EventMask.SCROLL_MASK|Gdk.EventMask.SMOOTH_SCROLL_MASK)
    area.connect('button-press-event',lambda _,e:events.append(('button-down',e.button)) or True)
    area.connect('button-release-event',lambda _,e:events.append(('button-up',e.button)) or True)
    area.connect('motion-notify-event',lambda _,e:events.append(('motion',int(e.state))) or True)
    area.connect('scroll-event',lambda _,e:events.append(('scroll',int(e.direction))) or True)
    app.content.pack_start(area,False,False,0);app.content.show_all();entry.grab_focus();yield
    output=Output();output.key(30,True);output.key(30,False);yield
    check('Native key reaches GTK entry',entry.get_text()=='a')
    output.key(42,True);output.key(30,True);output.key(30,False);output.key(42,False);yield
    check('Native modifier reaches GTK entry',entry.get_text()=='aA')
    output.key(105,True);yield;yield;output.key(105,False);yield
    check('Held key reaches native repeat handling',any(e[:2]==('key-down',Gdk.KEY_Left) for e in events))
    x,y=area.translate_coordinates(app.window,0,0)
    output.send(output.pointer,1,uint(output.timestamp(),x+200,y+100,1080,1080));output.send(output.pointer,4);yield
    output.button(272,True);yield;output.move(25,0);yield;output.button(272,False);yield
    check('Native held mouse drag',('button-down',1) in events and ('button-up',1) in events and any(e[0]=='motion' and e[1]&int(Gdk.ModifierType.BUTTON1_MASK) for e in events))
    output.button(273,True);yield;output.button(273,False);output.scroll(2);yield
    check('Native right click',('button-down',3) in events and ('button-up',3) in events)
    check('Native scrolling',any(e[0]=='scroll' for e in events))
    output.close();output=None
    check('Native output closes cleanly',True)


generator=None
def advance():
    global generator,failed,output
    try:
        if generator is None:generator=steps()
        next(generator);return True
    except StopIteration:app.quit();return False
    except Exception:
        failed=True;traceback.print_exc();print('Captured events:',events[-30:],flush=True)
        if output:output.close();output=None
        app.quit();return False


app.connect('activate',lambda *_:GLib.timeout_add(700,advance))
app.run([sys.argv[0]])
temp.cleanup()
raise SystemExit(1 if failed else 0)
