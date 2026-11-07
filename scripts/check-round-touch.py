#!/usr/bin/env python3
"""Dispatch native GDK touch sequences through GTK on the Pi's desktop.

App launches are intercepted. These checks exercise event capture and claiming,
not just gesture callbacks; physical touchscreen feel still needs a hand test.
"""
import ctypes
import json
import math
from pathlib import Path
import sys
import time
import traceback
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/round-desktop'))
from round_photos import Photos, Gtk, Gdk, Gio, GLib, GdkPixbuf
from round_shell import Shell

# PyGObject cannot construct the opaque GdkEventSequence pointer. Only that
# field is filled through the public GdkEventTouch C layout; GDK owns the event.
class TouchLayout(ctypes.Structure):
    _fields_=[('type',ctypes.c_int),('window',ctypes.c_void_p),
              ('send_event',ctypes.c_int8),('time',ctypes.c_uint32),
              ('x',ctypes.c_double),('y',ctypes.c_double),
              ('axes',ctypes.c_void_p),('state',ctypes.c_uint),
              ('sequence',ctypes.c_void_p)]

display=Gdk.Display.get_default()
touch_device=next(d for d in display.get_device_manager().list_devices(Gdk.DeviceType.SLAVE)
                  if d.get_source()==Gdk.InputSource.TOUCHSCREEN)
sequences={i:ctypes.c_int(i) for i in range(1,4)}
checks=[]
failed=False

def check(name,value):
    if not value: raise AssertionError(name)
    checks.append(name)

# Synthetic app events bypass the compositor. Catch the real-device blocker
# before claiming that those tests demonstrate working touchscreen gestures.
config=ET.parse(Path.home()/'.config/labwc/rc.xml').getroot()
touch_rules=[node for node in config.iter() if node.tag.split('}')[-1]=='touch'
             and ('waveshare' in node.get('deviceName','').casefold() or not node.get('deviceName'))]
check('WaveShare native touch configured',bool(touch_rules) and all(
    node.get('mouseEmulation','no').casefold() not in ('yes','true','on','1') for node in touch_rules))

def touch(window,kind,sequence,x,y):
    event=Gdk.Event.new(getattr(Gdk.EventType,'TOUCH_'+kind))
    event.touch.window=window
    event.touch.send_event=True
    event.touch.time=int(time.monotonic()*1000) & 0xffffffff
    event.touch.x=x;event.touch.y=y
    event.touch.x_root=x;event.touch.y_root=y
    event.touch.emulating_pointer=sequence==1
    event.set_device(display.get_default_seat().get_pointer())
    event.set_source_device(touch_device)
    TouchLayout.from_address(hash(event)).sequence=ctypes.addressof(sequences[sequence])
    Gtk.main_do_event(event)

def stroke(window,x,y,dx,dy=0,end='END'):
    touch(window,'BEGIN',1,x,y)
    for fraction in (0.15,0.4,0.7,1):
        touch(window,'UPDATE',1,x+dx*fraction,y+dy*fraction)
    touch(window,end,1,x+dx,y+dy)

def mouse_click(window,x,y):
    for kind in (Gdk.EventType.BUTTON_PRESS,Gdk.EventType.BUTTON_RELEASE):
        event=Gdk.Event.new(kind);event.button.window=window
        event.button.x=x;event.button.y=y;event.button.button=1
        event.button.time=Gdk.CURRENT_TIME
        event.set_device(display.get_default_seat().get_pointer())
        Gtk.main_do_event(event)

def launcher_steps(app):
    yield None
    launched=[];app.open_app=lambda item:launched.append(item['name'])
    # Opening finger can still contact the dock/top bar after Apps maps.
    for name,x,y in [('top launcher',480,70),('dock launcher',360,980)]:
        app.fixed.start()
        touch(app.window.get_window(),'BEGIN',1,x,y)
        check(name+' contact preserves opening motion',app.fixed.tick_id is not None)
        touch(app.window.get_window(),'END',1,x,y)
        check(name+' release does not launch an app',not launched)
        mouse_click(app.window.get_window(),x,y)
        check(name+' emulated mouse press preserves opening motion',app.fixed.tick_id is not None)
        app.fixed.finish()
    app.fixed.start()
    stroke(app.window.get_window(),540,690,-160);yield None
    check('touch interrupts launchpad reveal',app.fixed.tick_id is None)
    check('left swipe between icons advances',app.page==1 and not launched)
    stroke(app.window.get_window(),540,690,160);yield None
    check('right swipe between icons returns',app.page==0 and not launched)
    def swipe(dx,dy=0,end='END'):
        stroke(app.dynamic[min(1,len(app.dynamic)-1)].get_event_window(),90,80,dx,dy,end)
    swipe(0);yield None
    check('tap on icon still launches',len(launched)==1)
    launched.clear()
    swipe(-160);yield None
    check('left swipe over icon advances',app.page==1 and not launched)
    swipe(160);yield None
    check('right swipe returns',app.page==0 and not launched)
    mouse_click(app.dynamic[1].get_event_window(),90,80);yield None
    check('mouse still launches after swipe',len(launched)==1)
    launched.clear()
    swipe(160);yield None
    check('first page does not wrap',app.page==0 and not launched)
    swipe(-12);yield None
    check('small tap jitter still launches',len(launched)==1 and app.page==0)
    launched.clear()
    swipe(-45);yield None
    check('short drag neither launches nor paginates',app.page==0 and not launched)
    swipe(-90,160);yield None
    check('vertical drag neither launches nor paginates',app.page==0 and not launched)
    swipe(-160,end='CANCEL');yield None
    check('cancelled swipe does not paginate',app.page==0 and not launched)
    window=app.dynamic[1].get_event_window()
    touch(window,'BEGIN',1,90,80);touch(window,'UPDATE',1,-40,80)
    touch(window,'BEGIN',2,100,100)
    touch(window,'END',2,100,100);touch(window,'END',1,-40,80);yield None
    check('second finger cancels swipe',app.page==0 and not launched)
    window=app.dynamic[1].get_event_window()
    touch(window,'BEGIN',1,90,80);touch(window,'BEGIN',2,100,100)
    touch(window,'END',2,100,100);touch(window,'END',1,90,80);yield None
    check('two finger tap does not launch',app.page==0 and not launched)
    app.change_page(999);yield None
    last=app.page;swipe(-160);yield None
    check('last page does not wrap',app.page==last and not launched)
    app.search.set_text('Photos');yield None
    check('filtered page count',len(app.filtered_apps)==1)
    stroke(app.dynamic[0].get_event_window(),90,80,-160);yield None
    check('swipe respects filtered pages',app.page==0 and not launched)
    app.search.set_text('');yield None
    stroke(app.search.get_window(),300,270,-160);yield None
    check('search area does not paginate',app.page==0)

def photo_steps(app):
    yield None
    app.image=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,1600,900)
    app.image.fill(0x3977bbff);app.message.hide();app.open_button.hide()
    app.render();app.update_controls();yield None
    window=app.scroll.get_child().get_bin_window()
    touch(window,'BEGIN',1,280,220);touch(window,'BEGIN',2,480,220)
    touch(window,'UPDATE',2,680,220);yield None
    check('native pinch zooms normal viewer',math.isclose(app.zoom,2))
    check('zoom keeps touched image point',abs(app.scroll.get_hadjustment().get_value()-280)<4)
    touch(window,'UPDATE',2,1800,220);yield None
    check('normal pinch upper limit',app.zoom==4)
    touch(window,'END',2,1800,220);touch(window,'END',1,280,220)
    app.set_zoom(2);yield None
    before=app.scroll.get_hadjustment().get_value()
    stroke(window,400,200,-100);yield None
    check('one finger pans normal viewer',app.scroll.get_hadjustment().get_value()>before)
    touch(window,'BEGIN',1,280,220);touch(window,'BEGIN',2,680,220)
    touch(window,'UPDATE',2,300,220);yield None
    check('pinch returns to fit',app.zoom==1)
    touch(window,'CANCEL',2,300,220);touch(window,'CANCEL',1,280,220)
    app.enter_fullscreen();yield None
    window=app.full_surface.get_window()
    touch(window,'BEGIN',1,400,500);touch(window,'BEGIN',2,600,500)
    touch(window,'UPDATE',2,800,500);yield None
    check('native fullscreen pinch zooms',math.isclose(app.full_zoom,2))
    check('pinch cancels exit timer',app.hold_source is None)
    yield None;yield None;yield None
    check('pinch does not exit fullscreen',app.immersive)
    touch(window,'UPDATE',2,1500,500);yield None
    check('fullscreen upper limit',app.full_zoom==4)
    touch(window,'END',2,1500,500);touch(window,'END',1,400,500)
    before=app.pan_y;stroke(window,500,500,0,-100);yield None
    check('zoomed fullscreen pans vertically',app.pan_y>before)
    touch(window,'BEGIN',1,400,500);touch(window,'BEGIN',2,800,500)
    touch(window,'UPDATE',2,420,500);yield None
    check('fullscreen lower limit',app.full_zoom==1)
    touch(window,'CANCEL',2,420,500);touch(window,'CANCEL',1,400,500)
    check('cancel clears contacts and hold',not app.touches and app.hold_source is None)
    touch(window,'BEGIN',1,400,500);touch(window,'BEGIN',2,600,500)
    yield None;yield None;yield None
    check('stationary two finger hold still exits',not app.immersive)

for app,procedure in [(Shell('launchpad'),launcher_steps),(Photos(),photo_steps)]:
    app.set_application_id('org.aroundos.TouchCheck'+type(app).__name__)
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    iterator=procedure(app)
    def tick():
        global failed
        try:
            next(iterator);return True
        except StopIteration:pass
        except Exception:
            failed=True;traceback.print_exc()
        app.window.close();return False
    app.connect('activate',lambda _:GLib.timeout_add(400,tick))
    app.run([])
    if failed:break
print(json.dumps({'passed':not failed,'checks':len(checks),'last':checks[-1] if checks else None}))
raise SystemExit(1 if failed else 0)
