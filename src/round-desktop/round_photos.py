#!/usr/bin/env python3
"""Read-only, circle-safe Photos viewer using the installed GTK/GdkPixbuf stack."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import math
import sys
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, Gio, GLib, Pango
from round_ui import SHELL_CSS, icon
from round_dock import DockHover
from round_shell import label, launch_custom
from round_windows import activate

EXTENSIONS = {'.'+e.lower() for f in GdkPixbuf.Pixbuf.get_formats() for e in f.get_extensions()}
VIEW_WIDTH, VIEW_HEIGHT = 788, 512

def fitted_size(width, height, zoom=1):
    scale = min(VIEW_WIDTH / width, VIEW_HEIGHT / height) * zoom
    return max(1, round(width*scale)), max(1, round(height*scale))

def load_photo(path):
    info = GdkPixbuf.Pixbuf.get_file_info(str(path))
    if not info[0]: raise ValueError('Unsupported or unreadable image')
    limit = min(4096, max(info[1], info[2]))
    image = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), limit, limit, True)
    image = image.apply_embedded_orientation()
    try:
        siblings = sorted((p for p in path.parent.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS), key=lambda p:p.name.casefold())
    except OSError:
        siblings = []
    if path not in siblings: siblings.append(path)
    return image, siblings

class Photos(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.aroundos.Photos', flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.window = None
        self.image = None
        self.path = None
        self.siblings = []
        self.zoom = 1
        self.generation = 0
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.future = None
        self.placed = []
        self.closed = False
        self.immersive = False
        self.pan_x = self.pan_y = 0.5
        self.touches = {}
        self.hold_source = None
        self.hold_origins = {}
        self.mouse_point = None
        self.full_zoom = 1
        self.pinch = None
        self.zoom_anchor = None
        self.scroll_pan = None
        self.anchor_generation = 0
        self.render_source = None
        self.view_buffer = None
        self.full_buffer = None
        self.viewport_size = None
        self.delete_sheet = None

    def do_activate(self):
        if self.window:
            activate('aroundos-photos'); self.window.present(); return
        self.window = Gtk.ApplicationWindow(application=self, title='Photos · AroundOS')
        self.window.set_name('round-shell'); self.window.set_decorated(False)
        self.window.set_default_size(1080,1080)
        self.window.connect('destroy', self.destroyed)
        self.window.connect('key-press-event', self.key)
        css = Gtk.CssProvider(); css.load_from_data(SHELL_CSS + b'\n#round-shell .photo-card {background:#202023;border-radius:24px;} #round-shell viewport {background:transparent;} #round-shell button.photo-tool {background:transparent;border:1px solid transparent;border-radius:24px;padding:0;} #round-shell button.photo-tool:hover,#round-shell button.photo-tool:focus {background:alpha(white,0.10);} #round-shell button.photo-tool:active {background:#344d31;border-color:#a3ed75;}')
        css.load_from_data(SHELL_CSS + css.to_string().encode() + b' #round-shell .delete-tool {color:#ff6969;} #round-shell .save-sheet {background:#1c1c1f;border:1px solid #38383d;border-radius:32px;padding:28px;} #round-shell .save-sheet button {background:#29292e;border-radius:16px;min-height:64px;font:21px "Rubik";} #round-shell .save-sheet button.destructive {background:#b8323c;color:white;}')
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, 900)
        overlay = Gtk.Overlay(); overlay.add(Gtk.DrawingArea()); self.window.add(overlay); self.overlay = overlay
        self.fixed = Gtk.Fixed(); overlay.add_overlay(self.fixed)
        self.title = label('Photos','heading',0.5)
        self.put(self.title,340,164,400,60)
        self.caption = label('Open an image from Files','secondary',0.5)
        self.caption.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.caption.set_max_width_chars(1)
        self.put(self.caption,240,864,600,36)
        card = Gtk.EventBox(); card.get_style_context().add_class('photo-card'); self.put(card,128,296,824,548)
        self.scroll = Gtk.ScrolledWindow(); self.scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_kinetic_scrolling(False)
        self.put(self.scroll,146,314,VIEW_WIDTH,VIEW_HEIGHT)
        # A virtual canvas keeps scrollbars/panning, but the bitmap contains only
        # visible pixels. Zooming never allocates a viewport-sized image times 4².
        self.canvas = Gtk.Layout()
        self.photo = Gtk.Image(); self.canvas.put(self.photo,0,0)
        self.scroll.add(self.canvas)
        self.canvas.connect('size-allocate',self.viewport_allocated)
        for adjustment in self.adjustments():
            adjustment.connect('value-changed',lambda *_:self.queue_render())
        self.zoom_gesture = Gtk.GestureZoom.new(self.scroll)
        self.zoom_gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.zoom_gesture.connect('begin', self.zoom_begin)
        self.zoom_gesture.connect('scale-changed', self.zoom_changed)
        self.drag_gesture = Gtk.GestureDrag.new(self.scroll)
        self.drag_gesture.set_touch_only(True)
        self.drag_gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.drag_gesture.group(self.zoom_gesture)
        self.drag_gesture.connect('drag-begin', self.drag_begin)
        self.drag_gesture.connect('drag-update', self.drag_update)
        self.message = label('Choose a photo to begin','body',0.5); self.message.set_line_wrap(True)
        self.put(self.message,250,460,580,90)
        self.open_button = self.button('Open Files','system-file-manager-symbolic',lambda _:launch_custom('files'))
        self.put(self.open_button,500,570,80,80)
        self.previous = self.button('Previous photo','go-previous-symbolic',lambda _:self.step(-1),26)
        self.next = self.button('Next photo','go-next-symbolic',lambda _:self.step(1),26)
        self.full_button = self.button('Full screen · hold two fingers to exit','view-fullscreen-symbolic',lambda _:self.enter_fullscreen(),26)
        self.close_button = self.button('Close','window-close-symbolic',lambda _:self.window.close(),26)
        dock = Gtk.Image.new_from_file(str(Path(__file__).with_name('editor-dock.svg')))
        dock.get_accessible().set_name('Photos tools')
        # Transparent SVG corners extend beyond the circle; the painted arc stays inside.
        self.fixed.put(dock,332,936); dock.set_size_request(416,120)
        self.delete_button = self.button('Delete photo','user-trash-symbolic',lambda _:self.confirm_delete(),26)
        self.delete_button.get_child().destroy()
        trash = Gtk.Image.new_from_icon_name('user-trash-symbolic',Gtk.IconSize.BUTTON)
        trash.set_pixel_size(26); self.delete_button.add(trash)
        self.delete_button.get_style_context().add_class('delete-tool')
        self.controls = [self.previous,self.next,self.full_button,self.delete_button,self.close_button]
        for index,button in enumerate(self.controls):
            button.get_style_context().remove_class('control')
            button.get_style_context().add_class('photo-tool')
            x = 404 + 68 * index
            y = round(540 + math.sqrt(476**2 - (x - 540)**2))
            self.put(button,x-28,y-28,56,56)
        self.dock_hover = DockHover(self.fixed,self.controls)
        self.full_surface = Gtk.EventBox()
        self.full_surface.set_no_show_all(True)
        self.full_surface.add_events(Gdk.EventMask.TOUCH_MASK | Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.full_canvas = Gtk.Image(); self.full_surface.add(self.full_canvas); self.full_canvas.show()
        overlay.add_overlay(self.full_surface)
        self.full_surface.connect('touch-event', self.touch_event)
        self.full_surface.connect('button-press-event', self.mouse_press)
        self.full_surface.connect('button-release-event', self.mouse_release)
        self.full_surface.connect('motion-notify-event', self.mouse_move)
        self.window.show_all(); self.window.maximize(); self.update_controls()

    def do_open(self, files, count, hint):
        self.do_activate()
        if files:
            path = files[0].get_path()
            if path: self.open_path(Path(path))
            else: self.message.set_text('Open a local image from Files'); self.message.show()

    def put(self,w,x,y,width,height):
        self.fixed.put(w,x,y); w.set_size_request(width,height); self.placed.append(w); return w

    def button(self,name,symbol,callback,size=34):
        button = Gtk.Button(); button.get_style_context().add_class('control'); button.add(icon(symbol,size))
        button.get_accessible().set_name(name); button.set_tooltip_text(name); button.connect('clicked',callback); return button

    def open_path(self,path):
        if self.immersive: self.exit_fullscreen()
        self.anchor_generation += 1; self.zoom_anchor = None; self.scroll_pan = None
        self.generation += 1; generation = self.generation
        self.path = path.absolute(); self.image = None; self.zoom = 1
        self.photo.clear(); self.view_buffer = None; self.full_buffer = None
        self.canvas.set_size(1,1)
        self.caption.set_text(self.path.name); self.caption.set_tooltip_text(str(self.path))
        self.message.set_text('Loading…'); self.message.show(); self.open_button.hide(); self.update_controls()
        if self.future: self.future.cancel()
        self.future = self.pool.submit(load_photo,self.path)
        def loaded(f):
            if f.cancelled(): return
            try: result,error = f.result(),None
            except Exception as exc: result,error = None,str(exc)
            GLib.idle_add(self.finish_load,generation,result,error)
        self.future.add_done_callback(loaded)

    def finish_load(self,generation,result,error):
        if self.closed or generation != self.generation: return False
        if error:
            self.message.set_text('This image could not be opened.\nChoose another image from Files.')
            self.message.set_tooltip_text(error); self.message.show(); self.open_button.show()
        else:
            self.image,self.siblings = result; self.message.hide(); self.open_button.hide(); self.render()
        self.update_controls(); return False

    def render(self):
        if not self.image: return
        width,height = fitted_size(self.image.get_width(),self.image.get_height(),self.zoom)
        self.canvas.set_size(width,height)
        self.queue_render()

    def queue_render(self):
        # Touch devices can report several updates per display frame. Render the
        # most recent state once, rather than making input wait for every bitmap.
        if self.image is not None and not self.closed and self.render_source is None:
            self.render_source=self.window.add_tick_callback(lambda *_:self.paint_latest())

    def viewport_allocated(self,widget,allocation):
        size=(allocation.width,allocation.height)
        if size!=self.viewport_size:
            self.viewport_size=size; self.queue_render()

    def paint_latest(self):
        self.render_source=None
        if self.closed or self.image is None: return False
        if self.immersive:
            width,height=self.image.get_width(),self.image.get_height()
            side=max(1,round(min(width,height)/self.full_zoom))
            x=round((width-side)*self.pan_x); y=round((height-side)*self.pan_y)
            self.full_buffer=self.buffer(self.full_buffer,1080,1080)
            scale=1080/side
            # A subpixbuf shares source memory and preserves exact crop sampling.
            crop=self.image.new_subpixbuf(x,y,side,side)
            crop.scale(self.full_buffer,0,0,1080,1080,0,0,scale,scale,GdkPixbuf.InterpType.BILINEAR)
            self.full_canvas.set_from_pixbuf(self.full_buffer)
            self.full_canvas.queue_draw()
        else:
            width,height=fitted_size(self.image.get_width(),self.image.get_height(),self.zoom)
            horizontal,vertical=self.adjustments()
            vw,vh=horizontal.get_page_size(),vertical.get_page_size()
            if vw<=0 or vh<=0: return False
            mx,my=max(0,(vw-width)/2),max(0,(vh-height)/2)
            left,top=math.floor(max(mx,horizontal.get_value())),math.floor(max(my,vertical.get_value()))
            right=math.ceil(min(mx+width,horizontal.get_value()+vw))
            bottom=math.ceil(min(my+height,vertical.get_value()+vh))
            if right<=left or bottom<=top: return False
            self.view_buffer=self.buffer(self.view_buffer,right-left,bottom-top)
            self.image.scale(self.view_buffer,0,0,right-left,bottom-top,mx-left,my-top,
                             width/self.image.get_width(),height/self.image.get_height(),
                             GdkPixbuf.InterpType.BILINEAR)
            self.canvas.move(self.photo,left,top)
            self.photo.set_from_pixbuf(self.view_buffer)
            self.photo.queue_draw()
        return False

    def buffer(self,current,width,height):
        if current is None or current.get_width()!=width or current.get_height()!=height or current.get_has_alpha()!=self.image.get_has_alpha():
            return GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,self.image.get_has_alpha(),8,width,height)
        return current

    def image_anchor(self,x,y):
        width,height = fitted_size(self.image.get_width(),self.image.get_height(),self.zoom)
        coordinates=[]
        for point,size,adjustment in zip((x,y),(width,height),self.adjustments()):
            margin=max(0,(adjustment.get_page_size()-size)/2)
            coordinates.append((point+adjustment.get_value()-margin)/size)
        return tuple(coordinates)

    def adjustments(self):
        return self.scroll.get_hadjustment(),self.scroll.get_vadjustment()

    def set_zoom(self,value,anchor=None,point=None):
        if not self.image: return
        point = point or tuple(a.get_page_size()/2 for a in self.adjustments())
        anchor = anchor or self.image_anchor(*point)
        self.zoom = max(1,min(4,value)); self.render(); self.update_controls()
        self.anchor_generation += 1; generation = self.anchor_generation
        def position():
            if self.closed or generation != self.anchor_generation: return False
            size=fitted_size(self.image.get_width(),self.image.get_height(),self.zoom)
            for fraction,pixels,target,adjustment in zip(anchor,size,point,self.adjustments()):
                adjustment.set_value(max(0,min(adjustment.get_upper()-adjustment.get_page_size(),fraction*pixels-target)))
            return False
        # GTK must allocate the scaled image before its scroll range can be restored.
        GLib.idle_add(position,priority=GLib.PRIORITY_LOW)

    def zoom_begin(self,gesture,sequence):
        if not self.image: return
        valid,x,y=gesture.get_bounding_box_center()
        if not valid: return
        self.zoom_start=self.zoom; self.zoom_anchor=self.image_anchor(x,y)
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def zoom_changed(self,gesture,scale):
        if not self.image or self.zoom_anchor is None: return
        valid,x,y=gesture.get_bounding_box_center()
        if valid: self.set_zoom(self.zoom_start*scale,self.zoom_anchor,(x,y))

    def drag_begin(self,gesture,x,y):
        self.scroll_pan=tuple(a.get_value() for a in self.adjustments())

    def drag_update(self,gesture,dx,dy):
        if not self.image or self.zoom_gesture.is_recognized() or self.scroll_pan is None: return
        if max(abs(dx),abs(dy))<8: return
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        for start,delta,adjustment in zip(self.scroll_pan,(dx,dy),self.adjustments()):
            adjustment.set_value(max(0,min(adjustment.get_upper()-adjustment.get_page_size(),start-delta)))

    def rotate(self):
        if self.image:
            self.anchor_generation += 1; self.zoom_anchor = None
            self.image = self.image.rotate_simple(GdkPixbuf.PixbufRotation.CLOCKWISE)
            self.zoom = 1; self.render(); self.update_controls()

    def step(self,delta):
        if self.path not in self.siblings: return
        index = self.siblings.index(self.path)+delta
        if 0 <= index < len(self.siblings): self.open_path(self.siblings[index])

    def update_controls(self):
        index = self.siblings.index(self.path) if self.path in self.siblings else -1
        ready = self.image is not None
        self.previous.set_sensitive(ready and index>0)
        self.next.set_sensitive(ready and 0 <= index < len(self.siblings)-1)
        self.full_button.set_sensitive(ready)
        self.delete_button.set_sensitive(ready)

    def dismiss_delete(self):
        if self.delete_sheet:
            self.delete_sheet.destroy(); self.delete_sheet = None
        self.fixed.set_sensitive(True)
        self.delete_button.grab_focus()

    def confirm_delete(self):
        if self.image is None or self.delete_sheet: return
        target = self.path
        self.fixed.set_sensitive(False)
        sheet = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=20)
        sheet.get_style_context().add_class('save-sheet')
        sheet.set_halign(Gtk.Align.CENTER); sheet.set_valign(Gtk.Align.CENTER)
        sheet.set_size_request(580,-1)
        sheet.pack_start(label('Delete photo?','heading',0.5),False,False,0)
        note = label('Move “'+target.name+'” to Trash?','secondary',0.5)
        note.set_line_wrap(True); note.set_max_width_chars(36)
        note.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        sheet.pack_start(note,False,False,0)
        actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,homogeneous=True)
        cancel = Gtk.Button(label='Cancel'); cancel.connect('clicked',lambda _:self.dismiss_delete())
        delete = Gtk.Button(label='Delete'); delete.get_style_context().add_class('destructive')
        def confirmed(_):
            try: Gio.File.new_for_path(str(target)).trash(None)
            except GLib.Error as exc:
                note.set_text('Could not delete this photo.\n'+exc.message); delete.set_sensitive(False); return
            remaining = [p for p in self.siblings if p != target]
            index = self.siblings.index(target) if target in self.siblings else 0
            self.dismiss_delete()
            if remaining: self.open_path(remaining[min(index,len(remaining)-1)])
            else:
                self.image = None; self.path = None; self.siblings = []
                self.photo.clear(); self.view_buffer = self.full_buffer = None
                self.caption.set_text('Open an image from Files')
                self.message.set_text('Choose a photo to begin'); self.message.show(); self.open_button.show()
                self.update_controls()
        delete.connect('clicked',confirmed)
        actions.add(cancel); actions.add(delete); sheet.add(actions)
        self.delete_sheet = sheet; self.overlay.add_overlay(sheet); sheet.show_all(); cancel.grab_focus()

    def enter_fullscreen(self):
        if not self.image or self.immersive: return
        self.immersive = True
        self.full_zoom = 1; self.pinch = None
        self.pan_x = self.pan_y = 0.5
        self.fixed.hide(); self.full_surface.show()
        self.window.fullscreen()
        self.render_fullscreen()

    def exit_fullscreen(self):
        self.cancel_hold(); self.touches.clear(); self.mouse_point = None; self.pinch = None
        self.immersive = False
        self.full_surface.hide(); self.fixed.show()
        self.window.unfullscreen(); self.window.maximize()

    def render_fullscreen(self):
        self.queue_render()

    def pan(self,dx,dy):
        if not self.immersive or not self.image: return
        width,height = self.image.get_width(),self.image.get_height()
        side = max(1,round(min(width,height)/self.full_zoom))
        if width>side: self.pan_x = max(0,min(1,self.pan_x-dx*side/(1080*(width-side))))
        if height>side: self.pan_y = max(0,min(1,self.pan_y-dy*side/(1080*(height-side))))
        self.render_fullscreen()

    def cancel_hold(self):
        if self.hold_source:
            GLib.source_remove(self.hold_source); self.hold_source = None
        self.hold_origins = {}

    def finish_hold(self):
        self.hold_source = None
        if self.immersive and len(self.touches)==2: self.exit_fullscreen()
        return False

    def contact(self,kind,sequence,x,y):
        if not self.immersive: return
        if kind=='begin':
            self.touches[sequence]=(x,y)
            self.cancel_hold(); self.pinch = None; self.mouse_point = None
            if len(self.touches)==2:
                a,b=self.touches.values()
                distance=math.hypot(b[0]-a[0],b[1]-a[1])
                side=max(1,round(min(self.image.get_width(),self.image.get_height())/self.full_zoom))
                center=((a[0]+b[0])/2,(a[1]+b[1])/2)
                source=tuple((size-side)*pan+point*side/1080 for size,pan,point in zip(
                    (self.image.get_width(),self.image.get_height()),(self.pan_x,self.pan_y),center))
                self.pinch=(max(1,distance),self.full_zoom,source)
                self.hold_origins=self.touches.copy()
                self.hold_source=GLib.timeout_add(900,self.finish_hold)
        elif kind=='update' and sequence in self.touches:
            old=self.touches[sequence]; self.touches[sequence]=(x,y)
            if len(self.touches)==1: self.pan(x-old[0],y-old[1])
            elif len(self.touches)==2 and self.pinch:
                if self.hold_source:
                    origin=self.hold_origins.get(sequence,(x,y))
                    if math.hypot(x-origin[0],y-origin[1])<=12: return
                    self.cancel_hold()
                a,b=self.touches.values(); distance,zoom,source=self.pinch
                self.full_zoom=max(1,min(4,zoom*math.hypot(b[0]-a[0],b[1]-a[1])/distance))
                side=max(1,round(min(self.image.get_width(),self.image.get_height())/self.full_zoom))
                center=((a[0]+b[0])/2,(a[1]+b[1])/2)
                self.pan_x,self.pan_y=tuple(max(0,min(1,(pixel-point*side/1080)/(size-side))) if size>side else 0.5
                    for pixel,point,size in zip(source,center,(self.image.get_width(),self.image.get_height())))
                self.render_fullscreen()
        elif kind in ('end','cancel'):
            self.touches.pop(sequence,None); self.cancel_hold(); self.pinch = None

    def touch_event(self,widget,event):
        kinds={Gdk.EventType.TOUCH_BEGIN:'begin',Gdk.EventType.TOUCH_UPDATE:'update',Gdk.EventType.TOUCH_END:'end',Gdk.EventType.TOUCH_CANCEL:'cancel'}
        self.contact(kinds[event.type],event.get_event_sequence(),event.x,event.y)
        return True

    def mouse_press(self,widget,event):
        if event.button==1 and not self.touches: self.mouse_point=(event.x,event.y)
        return True

    def mouse_release(self,*_):
        self.mouse_point=None; return True

    def mouse_move(self,widget,event):
        if self.mouse_point and not self.touches:
            x,y=self.mouse_point; self.pan(event.x-x,event.y-y); self.mouse_point=(event.x,event.y)
        return True

    def key(self,window,event):
        if self.delete_sheet:
            if event.keyval == Gdk.KEY_Escape: self.dismiss_delete(); return True
            if event.keyval in (Gdk.KEY_Left,Gdk.KEY_Right): return True
        if event.keyval == Gdk.KEY_Escape:
            if self.immersive: self.exit_fullscreen()
            else: self.window.close()
            return True
        if event.keyval in (Gdk.KEY_Left,Gdk.KEY_Right): self.step(-1 if event.keyval==Gdk.KEY_Left else 1); return True
        return False

    def destroyed(self,*_):
        self.cancel_hold()
        if self.render_source is not None:
            self.window.remove_tick_callback(self.render_source); self.render_source=None
        self.closed=True; self.generation+=1; self.pool.shutdown(wait=False,cancel_futures=True); self.window=None

if __name__=='__main__':
    GLib.set_prgname('aroundos-photos')
    sys.exit(Photos().run(sys.argv))
