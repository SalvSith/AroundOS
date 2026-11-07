#!/usr/bin/env python3
"""Live Photos behavior and actual allocation checks, using temporary fixtures."""
from pathlib import Path
import sys, tempfile, time, math, hashlib, json, traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/round-desktop'))
from round_photos import Photos, Gtk, Gio, GLib, GdkPixbuf, fitted_size
checks=[]; failed=False

def check(name,value):
    if not value: raise AssertionError(name)
    checks.append(name)

def geometry(app):
    a=app.window.get_allocation();check('full-size client',(a.width,a.height)==(1080,1080))
    for w in app.placed:
        if not w.get_visible():continue
        a=w.get_allocation();x,y=w.translate_coordinates(app.window,0,0)
        check('circular bounds '+str(w.get_accessible().get_name()),max(math.hypot(px-540,py-540) for px in (x,x+a.width) for py in (y,y+a.height))<=515)

with tempfile.TemporaryDirectory(prefix='aroundos-photos-check-') as folder:
    paths=[Path(folder)/'01 landscape.png',Path(folder)/'02 portrait ü.png']
    for p,(w,h) in zip(paths,[(1600,900),(400,1000)]):
        pix=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,w,h);pix.fill(0x2977ccff);pix.savev(str(p),'png',[],[])
    hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    app=Photos();app.set_application_id('org.aroundos.PhotosCheck');app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    def steps():
        yield None;geometry(app)
        app.open_path(paths[0]);yield lambda:app.image is not None
        check('fit landscape',fitted_size(1600,900)==(788,443));geometry(app)
        check('next enabled',app.next.get_sensitive() and not app.previous.get_sensitive())
        app.next.emit('clicked');yield lambda:app.image is not None
        check('next loads unicode name',app.path==paths[1] and app.caption.get_text()==paths[1].name)
        check('portrait fit',fitted_size(400,1000)==(205,512))
        app.set_zoom(100);yield None;check('zoom upper limit',app.zoom==4);geometry(app)
        app.set_zoom(-5);check('zoom lower limit',app.zoom==1)
        app.rotate();yield None;check('rotate dimensions',(app.image.get_width(),app.image.get_height())==(1000,400))
        app.full_button.emit('clicked');yield None
        check('immersive mode',app.immersive and not app.fixed.get_visible())
        a=app.full_surface.get_allocation();check('full display image',(a.width,a.height)==(1080,1080))
        check('compositor fullscreen',bool(app.window.get_window().get_state() & __import__('round_photos').Gdk.WindowState.FULLSCREEN))
        app.contact('begin','one',500,500);app.contact('update','one',600,500)
        check('one finger pans',app.pan_x<0.5)
        app.contact('begin','two',700,500);app.contact('end','two',700,500);yield None;yield None;yield None
        check('short two finger touch does not exit',app.immersive)
        app.contact('begin','two',700,500);app.contact('update','two',740,500);yield None;yield None;yield None
        check('moving fingers cancels hold',app.immersive and app.hold_source is None)
        app.contact('end','two',740,500);app.contact('begin','two',700,500)
        yield lambda:not app.immersive
        check('two finger hold exits',app.fixed.get_visible() and not app.touches)
        yield None;geometry(app)
        check('fullscreen state restored',not bool(app.window.get_window().get_state() & __import__('round_photos').Gdk.WindowState.FULLSCREEN))
        app.confirm_delete();yield None
        check('delete confirmation',app.delete_sheet is not None and not app.fixed.get_sensitive())
        app.dismiss_delete();yield None
        check('cancel preserves photo',paths[1].exists() and app.fixed.get_sensitive())
        check('no file mutations',[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]==hashes)
        check('five icon tools',len(app.controls)==5 and all(isinstance(w.get_child(),__import__('round_photos').Gtk.Image) for w in app.controls))
        check('close is rightmost',app.controls[-1] is app.close_button)
        check('centered title',app.title.get_xalign()==0.5 and app.title.translate_coordinates(app.window,0,0)[0]+app.title.get_allocated_width()/2==540)
        check('caption below photo',app.caption.translate_coordinates(app.window,0,0)[1]>app.scroll.translate_coordinates(app.window,0,0)[1]+app.scroll.get_allocated_height())
        app.open_path(paths[0]);app.open_path(paths[1]);yield lambda:app.image is not None
        check('stale load ignored',app.image.get_width()==400)
        app.open_path(Path(folder)/'missing.png');yield lambda:'could not' in app.message.get_text()
        check('error state',not app.full_button.get_sensitive() and not app.next.get_sensitive() and not app.previous.get_sensitive() and app.open_button.get_visible())
        for mime in ['image/png','image/jpeg','image/webp']:
            check('default '+mime,Gio.AppInfo.get_default_for_type(mime,False).get_id()=='aroundos-photos.desktop')
        app.open_path(Path('/usr/share/rpd-wallpaper/aurora.jpg'));yield lambda:app.image is not None
        geometry(app)
        import subprocess
        subprocess.run(['grim','/tmp/aroundos-photos.png'],check=True)
    iterator=steps();pending=None;deadline=time.monotonic()+15
    def tick():
        global pending,deadline,failed
        try:
            if pending is not None and not pending():
                if time.monotonic()>deadline:raise TimeoutError('Photos did not settle')
                return True
            pending=next(iterator);deadline=time.monotonic()+15;return True
        except StopIteration:pass
        except Exception:failed=True;traceback.print_exc()
        app.window.close();return False
    GLib.set_prgname('aroundos-photos-check')
    app.connect('activate',lambda _:GLib.timeout_add(400,tick));app.run([])
print(json.dumps({'passed':not failed,'checks':len(checks),'last':checks[-1] if checks else None}))
raise SystemExit(1 if failed else 0)
