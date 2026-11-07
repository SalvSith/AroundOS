#!/usr/bin/env python3
"""Live bounded-bitmap, frame-coalescing and pixel checks for Photos on the Pi."""
import json
from pathlib import Path
import statistics
import sys
import time
import traceback

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/round-desktop'))
from round_photos import Photos, Gio, GLib, GdkPixbuf, fitted_size

checks=[];failed=False
timings={'normal':[],'fullscreen':[]}
frame_times={'normal':[],'fullscreen':[]}

def check(name,condition):
    if not condition:raise AssertionError(name)
    checks.append(name)

class MeasuredPhotos(Photos):
    def paint_latest(self):
        mode='fullscreen' if self.immersive else 'normal'
        start=time.perf_counter()
        result=super().paint_latest()
        timings[mode].append((time.perf_counter()-start)*1000)
        frame_times[mode].append(start)
        return result

app=MeasuredPhotos();app.set_application_id('org.aroundos.PhotoRenderCheck')
app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)

def pixels_match(actual,expected):
    a,b=actual.get_pixels(),expected.get_pixels()
    channels=actual.get_n_channels()
    for fy in (0.1,0.3,0.5,0.7,0.9):
        for fx in (0.1,0.3,0.5,0.7,0.9):
            x=int(fx*actual.get_width());y=int(fy*actual.get_height())
            ia=y*actual.get_rowstride()+x*channels
            ib=y*expected.get_rowstride()+x*channels
            if max(abs(a[ia+c]-b[ib+c]) for c in range(channels))>3:return False
    return True

def animate(fullscreen=False):
    start=time.monotonic()
    def update():
        phase=min(1,(time.monotonic()-start)/2)
        if fullscreen:
            app.full_zoom=1+3*phase;app.render_fullscreen()
        else:app.set_zoom(1+3*phase)
        return phase<1
    GLib.timeout_add(4,update)

def steps():
    app.open_path(Path('/usr/share/rpd-wallpaper/aurora.jpg'))
    yield lambda:app.image is not None and app.view_buffer is not None
    before=len(timings['normal'])
    for i in range(100):app.set_zoom(1+3*i/99)
    check('touch updates do not synchronously rescale',len(timings['normal'])==before)
    yield None
    check('touch burst coalesced',len(timings['normal'])-before<=3)
    # Fractional scroll offsets can expose one extra edge pixel.
    check('normal bitmap bounded by viewport',app.view_buffer.get_width()<=789 and app.view_buffer.get_height()<=513)
    app.scroll.get_hadjustment().set_value(300);app.scroll.get_vadjustment().set_value(200)
    yield None
    w,h=fitted_size(app.image.get_width(),app.image.get_height(),app.zoom)
    reference=app.image.scale_simple(w,h,GdkPixbuf.InterpType.BILINEAR)
    reference=reference.new_subpixbuf(300,200,app.view_buffer.get_width(),app.view_buffer.get_height())
    check('visible crop matches previous full bitmap',pixels_match(app.view_buffer,reference))
    before=len(timings['normal']);yield None
    check('no idle repaint loop',len(timings['normal'])==before and app.render_source is None)
    timings['normal'].clear();frame_times['normal'].clear()
    animate();deadline=time.monotonic()+2.4
    yield lambda:time.monotonic()>deadline
    app.enter_fullscreen();yield None
    app.full_zoom=2;app.pan_x=0.3;app.pan_y=0.6;app.render_fullscreen();yield None
    w,h=app.image.get_width(),app.image.get_height();side=round(min(w,h)/2)
    reference=app.image.new_subpixbuf(round((w-side)*0.3),round((h-side)*0.6),side,side)
    reference=reference.scale_simple(1080,1080,GdkPixbuf.InterpType.BILINEAR)
    check('fullscreen crop matches previous renderer',pixels_match(app.full_buffer,reference))
    buffer=app.full_buffer;app.pan(30,20);yield None
    check('fullscreen buffer reused',app.full_buffer is buffer)
    timings['fullscreen'].clear();frame_times['fullscreen'].clear()
    animate(True);deadline=time.monotonic()+2.4
    yield lambda:time.monotonic()>deadline
    app.exit_fullscreen();yield None
    check('return restores normal photo',app.photo.get_pixbuf() is app.view_buffer)

iterator=steps();pending=None;deadline=time.monotonic()+15
def tick():
    global pending,deadline,failed
    try:
        if pending is not None and not pending():
            if time.monotonic()>deadline:raise TimeoutError('Render check did not settle')
            return True
        pending=next(iterator);deadline=time.monotonic()+15;return True
    except StopIteration:pass
    except Exception:failed=True;traceback.print_exc()
    app.window.close();return False

app.connect('activate',lambda _:GLib.timeout_add(400,tick));app.run([])
stats={mode:{'frames':len(values),'median_render_ms':round(statistics.median(values),2),
             'fps_during_updates':round((len(values)-1)/(frame_times[mode][-1]-frame_times[mode][0]),1)}
       for mode,values in timings.items() if len(values)>1}
print(json.dumps({'passed':not failed,'checks':len(checks),'rendering':stats}))
raise SystemExit(1 if failed else 0)
