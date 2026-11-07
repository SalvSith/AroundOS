#!/usr/bin/env python3
"""Circular Launchpad and Settings, built with the installed GTK/GIO stack."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import gi
gi.require_version('Gtk','3.0')
gi.require_version('Gdk','3.0')
from gi.repository import Gtk,Gdk,Gio,GLib,Pango,GdkPixbuf
from round_ui import SHELL_CSS,icon
from round_windows import activate,show_home
from round_motion import LaunchpadReveal
from settings_grid import TILES, settings_tile

HERE=Path(__file__).resolve().parent
POOL=ThreadPoolExecutor(max_workers=3)
GRID_TILES={
    'aroundos-files.desktop':'files',
    'aroundos-editor.desktop':'editor',
    'aroundos-settings.desktop':'settings',
    'aroundos-terminal.desktop':'terminal',
    'x-terminal-emulator.desktop':'terminal',
    'aroundos-browser.desktop':'browser',
    'x-www-browser.desktop':'browser',
    'aroundos-dial.desktop':'dial',
    'aroundos-photos.desktop':'photos',
    'aroundos-videos.desktop':'videos',
    'aroundos-navcon.desktop':'navcon',
    'pishutdown.desktop':'shutdown',
    'lxtask.desktop':'task-manager',
    'vlc.desktop':'vlc',
}

GRID_ORDER=('browser','files','terminal','settings','photos','editor',
            'task-manager','dial','vlc','navcon','utilities','shutdown')

def order_grid(items):
    first={}
    extras=[]
    for item in items:
        key=item.get('grid_key')
        if key in GRID_ORDER and key not in first:
            first[key]=item
        else:
            extras.append(item)
    return [first[key] for key in GRID_ORDER if key in first]+extras

UTILITY_NAMES={
    'classic task manager','archiver','file manager','document viewer','run command',
    'add/remove software','add / remove software','htop','chromium web browser','chromium','chrome',
    'mousepad','pcman file manager','pcmanfm','qt5 settings','qt6 settings',
    'gt6 settings','raspberry pi diagnostics',
    'recommended software','run','sd card copier','text editor settings',
    'vnc server','xarchiver',
}

def is_utility(item):
    return item.get('original_name',item['name']).casefold() in UTILITY_NAMES


def command(argv):
    result=subprocess.run(argv,text=True,capture_output=True,timeout=12)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'This setting could not be changed.')
    return result.stdout.strip()

def run_async(argv,callback):
    future=POOL.submit(command,argv)
    def completed(f):
        try: value,error=f.result(),None
        except Exception as exc: value,error=None,str(exc)
        GLib.idle_add(callback,value,error)
    future.add_done_callback(completed)

def launch_custom(mode):
    app_id='aroundos-round-files' if mode=='files' else 'aroundos-'+mode
    if activate(app_id): return
    script={'files':'round_files.py','photos':'round_photos.py'}.get(mode,'round_shell.py')
    args=[sys.executable,str(HERE/script)] + ([] if mode in ('files','photos') else [mode])
    subprocess.Popen(args,start_new_session=True,stdin=subprocess.DEVNULL)

def label(text,style='body',align=0):
    w=Gtk.Label(label=text,xalign=align)
    w.get_style_context().add_class(style)
    w.set_ellipsize(Pango.EllipsizeMode.END)
    w.set_max_width_chars(1)
    return w

def launcher_bounds(index):
    return 144+(index%4)*208,294+(index//4)*190,168,174

def use_round_grid_icons():
    preference=Path(GLib.get_user_config_dir())/'aroundos-round'/'grid-icon-shape'
    try:
        return preference.read_bytes().strip().lower()!=b'square'
    except OSError:
        return True

def launcher_image(item,size):
    if 'custom' in item and 'tile' not in item:
        return icon(item['icon'],size)
    gicon=item.get('tile') or item['icon'] or Gio.ThemedIcon.new('application-x-executable')
    image=Gtk.Image.new_from_gicon(gicon,Gtk.IconSize.DIALOG)
    image.set_pixel_size(size)
    return image

@lru_cache(maxsize=1)
def orb_glint():
    # A single soft elliptical reflection, shared by every round badge.
    svg=b'''<svg xmlns="http://www.w3.org/2000/svg" width="62" height="28">
      <defs><radialGradient id="shine"><stop stop-color="white" stop-opacity=".44"/>
      <stop offset=".48" stop-color="white" stop-opacity=".20"/>
      <stop offset="1" stop-color="white" stop-opacity="0"/></radialGradient></defs>
      <ellipse cx="31" cy="14" rx="30" ry="9" transform="rotate(-14 31 14)" fill="url(#shine)"/>
    </svg>'''
    return svg_pixbuf(svg)


@lru_cache(maxsize=1)
def orb_glow():
    return svg_pixbuf(b'''<svg xmlns="http://www.w3.org/2000/svg" width="116" height="116">
      <defs><radialGradient id="light">
        <stop stop-color="#edfcff" stop-opacity=".06"/>
        <stop offset=".68" stop-color="#edfcff" stop-opacity=".12"/>
        <stop offset=".88" stop-color="#d2f4ff" stop-opacity=".24"/>
        <stop offset=".96" stop-color="#e8fbff" stop-opacity=".55"/>
        <stop offset="1" stop-color="#dcf8ff" stop-opacity=".03"/>
      </radialGradient></defs>
      <circle cx="58" cy="58" r="55" fill="url(#light)"/>
    </svg>''')


def svg_pixbuf(svg):
    loader=GdkPixbuf.PixbufLoader.new_with_type('svg')
    loader.write(svg)
    loader.close()
    return loader.get_pixbuf()


class OrbFace(Gtk.Overlay):
    def __init__(self,art,button,reduced_motion,column,row):
        super().__init__()
        self.add(art)
        self.surface=Gtk.Fixed()
        self.surface.set_name('orb-surface')
        css=Gtk.CssProvider()
        css.load_from_data(b'#orb-surface {border-radius:50%; background-image:linear-gradient(155deg,rgba(255,255,255,.09),transparent 45%,rgba(0,0,0,.16)); box-shadow:inset 0 1px 1px rgba(255,255,255,.24),inset 0 -2px 3px rgba(0,0,0,.18);}')
        self.surface.get_style_context().add_provider(css,1000)
        self.glint=Gtk.Image.new_from_pixbuf(orb_glint())
        self.base=(22-3*column,12-2*row)
        self.pose=(*self.base,0.38)
        self.target=self.pose
        self.tick=0
        self.surface.put(self.glint,*self.base)
        self.glint.set_opacity(self.pose[2])
        self.glow=Gtk.Image.new_from_pixbuf(orb_glow())
        self.glow.set_opacity(0)
        self.add_overlay(self.glow)
        self.set_overlay_pass_through(self.glow,True)
        self.add_overlay(self.surface)
        self.set_overlay_pass_through(self.surface,True)
        if not reduced_motion:
            button.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
            button.connect('motion-notify-event',self.track_pointer)
            button.connect('leave-notify-event',self.reset_pose)

    def aim(self,x,y,opacity):
        self.target=(x,y,opacity)
        if not self.tick:
            self.last=None
            self.tick=self.add_tick_callback(self.advance)

    def advance(self,widget,clock):
        now=clock.get_frame_time()
        elapsed=0 if self.last is None else max(0,now-self.last)
        self.last=now
        weight=math.exp(-elapsed/65000)
        self.pose=tuple(t+(v-t)*weight for v,t in zip(self.pose,self.target))
        done=all(abs(v-t)<0.005 for v,t in zip(self.pose,self.target))
        if done:
            self.pose=self.target
            self.tick=0
        x,y,opacity=self.pose
        self.surface.move(self.glint,round(x),round(y))
        self.glint.set_opacity(opacity)
        return not done

    def track_pointer(self,button,event):
        device=event.get_source_device()
        if device and device.get_source()==Gdk.InputSource.TOUCHSCREEN:
            return False
        x,y=button.get_pointer()
        dx=max(-1,min(1,2*x/max(1,button.get_allocated_width())-1))
        dy=max(-1,min(1,2*y/max(1,button.get_allocated_height())-1))
        self.aim(self.base[0]+4*dx,self.base[1]+2*dy,0.88)
        return False

    def reset_pose(self,*_):
        self.aim(*self.base,0.38)
        return False


class HoverSlot(Gtk.Fixed):
    """Move the badge inside a stationary button, leaving its label and hit area fixed."""
    def __init__(self,button,badge,size,reduced_motion):
        super().__init__()
        self.set_halign(Gtk.Align.CENTER)
        self.set_size_request(size,size+4)
        self.put(badge,0,4)
        self.badge=badge
        self.offset=0.0
        self.tick_id=0
        self.target=0
        self.reduced_motion=reduced_motion
        button.connect('state-flags-changed',self.state_changed)

    def state_changed(self,button,previous):
        flags=button.get_state_flags()
        target=4 if flags & Gtk.StateFlags.PRELIGHT and not flags & Gtk.StateFlags.ACTIVE else 0
        if target==self.target or self.reduced_motion:
            return
        self.target=target
        self.start_offset=self.offset
        clock=self.get_frame_clock()
        if not clock:
            self.offset=target
            self.move(self.badge,0,4-target)
            face=self.badge.get_child()
            if isinstance(face,OrbFace):
                face.glow.set_opacity(target/4)
            return
        self.started=clock.get_frame_time()
        if not self.tick_id:
            self.tick_id=self.add_tick_callback(self.animate)

    def animate(self,widget,clock):
        t=min(1.0,max(0.0,(clock.get_frame_time()-self.started)/150000))
        self.offset=self.target+(self.start_offset-self.target)*(1-t)**3
        self.move(self.badge,0,4-round(self.offset))
        face=self.badge.get_child()
        if isinstance(face,OrbFace):
            face.glow.set_opacity(self.offset/4)
        if t>=1:
            self.tick_id=0
            return False
        return True


class Shell(Gtk.Application):
    def __init__(self,mode,audit=None):
        super().__init__(application_id='org.aroundos.'+mode.title())
        self.mode=mode
        self.round_grid_icons=mode=='launchpad' and use_round_grid_icons()
        self.audit_path=audit
        self.window=None
        self.placed=[]
        self.dynamic=[]
        self.page=0
        self.query=''
        self.folder=None
        self.root_page=0
        self.apps=[]
        self.page_name='overview'
        self.generation=0
        self.pending_volume=None
        self.syncing=False
        self.volume_handler=None
        self.closing=False
        self.apps_reload_source=None

    def do_activate(self):
        if self.window:
            if self.mode=='launchpad':self.reload_apps()
            activate('aroundos-'+self.mode)
            self.window.present()
            if self.mode=='launchpad':self.window.set_focus(None)
            return
        self.window=Gtk.ApplicationWindow(application=self,title=('Apps' if self.mode=='launchpad' else 'Settings')+' · AroundOS')
        self.window.set_name('round-shell')
        self.window.set_decorated(False)
        self.window.set_default_size(1080,1080)
        self.window.connect('key-press-event',self.key)
        self.window.connect('destroy',self.destroyed)
        self.window.connect('delete-event',self.before_close)
        provider=Gtk.CssProvider();provider.load_from_data(SHELL_CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),provider,900)
        overlay=Gtk.Overlay();overlay.add(Gtk.DrawingArea());self.window.add(overlay)
        self.fixed=LaunchpadReveal() if self.mode=='launchpad' else Gtk.Fixed()
        overlay.add_overlay(self.fixed)
        if self.mode=='launchpad':self.fixed.attach(self.window)
        if self.mode=='settings':
            self.header=label('Settings','heading',0.5)
            self.put(self.header,344,164,392,60)
            self.back=self.button('Back','go-previous-symbolic',lambda _:self.back_action())
            self.back.get_child().show()
            self.back.set_no_show_all(True)
            self.put(self.back,198,158,80,80)
        self.put(self.button('Close','window-close-symbolic',lambda _:self.window.close()),802 if self.mode=='settings' else 756,158,80,80)
        if self.mode=='launchpad': self.build_launcher()
        else:
            self.content=Gtk.ScrolledWindow()
            self.content.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
            self.content.set_overlay_scrolling(False)
            self.put(self.content,190,276,700,570)
            self.notice=label('','secondary',0.5)
            self.notice.set_line_wrap(True);self.notice.set_lines(3)
            self.put(self.notice,260,864,560,90)
            self.settings_tiles={}
            for page,title,x,y,width,height in TILES:
                tile=settings_tile(page,title,width,height,self.show_settings)
                self.put(tile,x,y,width,height)
                tile.get_child().show_all()
                tile.set_no_show_all(True)
                self.settings_tiles[page]=tile
            self.show_settings('overview')
        self.window.show_all();self.window.maximize()
        if self.mode=='launchpad':
            self.render_apps()
            # Search starts only when selected, including on subsequent opens.
            self.window.set_focus(None)
            self.fixed.start()
        if self.audit_path: GLib.timeout_add_seconds(3,self.audit)

    def put(self,w,x,y,width,height,dynamic=False):
        self.fixed.put(w,x,y);w.set_size_request(width,height)
        self.placed.append(w)
        if dynamic: self.dynamic.append(w)
        return w

    def button(self,name,symbol,callback):
        button=Gtk.Button();button.get_style_context().add_class('control')
        button.add(icon(symbol,34));button.get_accessible().set_name(name)
        button.connect('clicked',callback)
        return button

    def back_action(self):
        if self.mode=='launchpad': show_home()
        elif self.page_name!='overview': self.show_settings('overview')
        else: launch_custom('launchpad')

    def build_launcher(self):
        # The window also receives touches in the gaps between app buttons.
        # Gtk.Fixed is windowless, so a controller on it misses background input.
        self.window.add_events(Gdk.EventMask.TOUCH_MASK)
        self.page_drag=Gtk.GestureDrag.new(self.window)
        self.page_drag.set_touch_only(True)
        self.page_drag.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.page_drag.connect('drag-begin',self.page_drag_begin)
        self.page_drag.connect('drag-update',self.page_drag_update)
        self.page_drag.connect('drag-end',self.page_drag_end)
        self.page_drag_active=False
        self.page_drag_moved=False
        self.search=Gtk.Entry();self.search.set_placeholder_text('Search')
        self.search.get_style_context().add_class('launcher-search')
        self.search.set_alignment(0.0)
        self.search.get_accessible().set_name('Search')
        self.search.connect('changed',self.search_apps)
        self.search.connect('focus-in-event',lambda *_:self.fixed.finish())
        self.put(self.search,244,158,480,80)
        self.previous=self.button('Previous apps','go-previous-symbolic',lambda _:self.change_page(-1))
        self.next=self.button('More apps','go-next-symbolic',lambda _:self.change_page(1))
        self.put(self.previous,388,928,72,72);self.put(self.next,620,928,72,72)
        self.page_label=label('','secondary',0.5);self.put(self.page_label,470,940,140,44)
        self.empty=label('No matching apps','body',0.5);self.put(self.empty,290,470,500,90)
        self.folder_title=label('Utilities','heading',0.5)
        self.put(self.folder_title,330,250,420,60)
        self.folder_back=self.button('Close Utilities','go-previous-symbolic',lambda _:self.close_folder())
        self.put(self.folder_back,244,250,72,60)
        self.collect_apps()
        self.app_monitor=Gio.AppInfoMonitor.get()
        self.app_monitor.connect('changed',lambda _:self.reload_apps())
        self.render_apps()

    def collect_apps(self):
        self.apps=[{'name':'Files','custom':'files','icon':'system-file-manager-symbolic','color':'#286bd9'},
                   {'name':'Settings','custom':'settings','icon':'preferences-system-symbolic','color':'#5c5c65'}]
        self.apps.append({'name':'Photos','custom':'photos','icon':'folder-pictures-symbolic','color':'#7649ad'})
        skip={'aroundos-photos.desktop','eom.desktop','aroundos-files.desktop','aroundos-settings.desktop','aroundos-launchpad.desktop','rpcc.desktop'}
        for app in Gio.AppInfo.get_all():
            if not app.should_show() or app.get_id() in skip: continue
            self.apps.append({'name':app.get_display_name(),'app':app,'icon':app.get_icon(),'color':'#29292e'})
        tile_dir=HERE/'dock-icons'
        if self.round_grid_icons:tile_dir=tile_dir/'round'
        for item in self.apps:
            desktop_id=item['app'].get_id() if 'app' in item else 'aroundos-'+item['custom']+'.desktop'
            tile=GRID_TILES.get(desktop_id)
            item['grid_key']=tile
            if tile:
                path=tile_dir/(('photos' if tile=='videos' else tile)+'.png')
                if path.is_file():
                    item['tile']=Gio.FileIcon.new(Gio.File.new_for_path(str(path)))
                    item['color']='transparent'
            item['original_name']=item['name']
            if tile=='shutdown':
                item['name']='Shutdown'
            elif item['name'].casefold() in ('chromium web browser','chromium'):
                item['name']='Chrome'
            elif item['name'].casefold()=='vlc media player':
                item['name']='VLC'
        self.apps[2:]=sorted(self.apps[2:],key=lambda item:item['name'].casefold())

    def reload_apps(self):
        if not self.window:return
        # AppInfoMonitor can notify during the first map (as captured on a
        # real touch launch). Rebuilding then calls finish() and presents an
        # opaque frame before focus restarts the reveal. Coalesce background
        # inventory refreshes until the opening has settled.
        if self.fixed.tick_id is not None:
            if self.apps_reload_source is None:
                self.apps_reload_source=GLib.timeout_add(80,self.flush_app_reload)
            return
        self.collect_apps()
        self.render_apps()

    def flush_app_reload(self):
        if self.window and self.fixed.tick_id is not None:return True
        self.apps_reload_source=None
        if self.window:self.reload_apps()
        return False

    def search_apps(self,entry):
        self.query=entry.get_text().casefold().strip();self.page=0;self.render_apps()

    def change_page(self,delta):
        self.page+=delta;self.render_apps()

    def page_drag_begin(self,gesture,x,y):
        self.page_drag_moved=False
        self.page_drag_active=100<=x<=980 and 314<=y<=904
        if self.page_drag_active:self.fixed.finish()
        if not self.page_drag_active:gesture.set_state(Gtk.EventSequenceState.DENIED)

    def page_drag_update(self,gesture,dx,dy):
        if self.page_drag_active and max(abs(dx),abs(dy))>=24:
            self.page_drag_moved=True
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def page_drag_end(self,gesture,dx,dy):
        active=self.page_drag_active;self.page_drag_active=False
        event=gesture.get_last_event(gesture.get_current_sequence())
        # A second finger or a cancelled sequence can also end recognition.
        if not active:return
        if event is None or event.type!=Gdk.EventType.TOUCH_END:
            self.page_drag_moved=True
            return
        if abs(dx)>=80 and abs(dx)>1.5*abs(dy):
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            # Rebuild buttons after GTK finishes dispatching the release.
            GLib.idle_add(self.finish_page_swipe,-1 if dx>0 else 1,self.page,self.query)

    def finish_page_swipe(self,delta,page,query):
        if self.window and self.page==page and self.query==query:self.change_page(delta)
        return False

    def app_clicked(self,button,item):
        # GtkButton may emit clicked while its emulated pointer press is cancelled.
        # Keep keyboard/programmatic activation available after a touch drag.
        event=Gtk.get_current_event()
        source=event.get_source_device() if event is not None else None
        if self.page_drag_moved and event is not None and (event.type in (
                Gdk.EventType.TOUCH_BEGIN,Gdk.EventType.TOUCH_UPDATE,Gdk.EventType.TOUCH_END,
                Gdk.EventType.TOUCH_CANCEL) or (source is not None and source.get_source()==Gdk.InputSource.TOUCHSCREEN)):return
        self.fixed.finish()
        self.open_app(item)

    def render_apps(self):
        # Search, paging and folder navigation stay immediate, even mid-reveal.
        self.fixed.finish()
        for w in self.dynamic:
            self.fixed.remove(w);self.placed.remove(w)
        self.dynamic=[]
        utilities=[a for a in self.apps if is_utility(a)]
        if self.query:
            items=[a for a in self.apps if self.query in (a['name']+' '+a.get('original_name','')).casefold()]
        elif self.folder:
            items=utilities
        else:
            items=[a for a in self.apps if not is_utility(a)]
            if utilities:items.append({'name':'Utilities','grid_key':'utilities','folder':True,'icon':None,'color':'rgba(170,180,200,0.28)'})
            items=order_grid(items)
        in_folder=bool(self.folder and not self.query)
        self.folder_title.set_visible(in_folder);self.folder_back.set_visible(bool(self.folder))
        if in_folder:
            panel=Gtk.EventBox()
            css=Gtk.CssProvider();css.load_from_data(b'* {background:rgba(110,120,145,0.22);border:1px solid rgba(255,255,255,0.14);border-radius:42px;}')
            panel.get_style_context().add_provider(css,1000)
            self.put(panel,210,320,660,580,dynamic=True);panel.show()
        per_page=9 if in_folder else 12
        pages=max(1,math.ceil(len(items)/per_page));self.page=max(0,min(self.page,pages-1))
        self.filtered_apps=items
        self.previous.set_sensitive(self.page>0);self.next.set_sensitive(self.page+1<pages)
        self.page_label.set_text(f'{self.page+1} / {pages}')
        self.empty.set_visible(not items)
        badge_size=116 if self.round_grid_icons else 104
        badge_radius=badge_size//2 if self.round_grid_icons else 24
        for i,item in enumerate(items[self.page*per_page:(self.page+1)*per_page]):
            button=Gtk.Button();button.get_accessible().set_name(item['name'])
            box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=2 if self.round_grid_icons else 10);box.set_valign(Gtk.Align.CENTER)
            badge=Gtk.EventBox();badge.set_size_request(badge_size,badge_size);badge.set_halign(Gtk.Align.CENTER)
            if self.round_grid_icons:
                button.get_style_context().add_class('round-app-button')
                badge.get_style_context().add_class('round-app-badge')
            css=Gtk.CssProvider()
            css.load_from_data((f'* {{background:{item["color"]};border-radius:{badge_radius}px;}}'
                                'button:hover .round-app-badge {box-shadow:none;}'
                                'button:active .round-app-badge {box-shadow:inset 0 0 0 2px #a3ed75;}').encode())
            badge.get_style_context().add_provider(css,1000)
            if item.get('folder'):
                preview=Gtk.Grid();preview.set_row_spacing(5);preview.set_column_spacing(5)
                preview.set_halign(Gtk.Align.CENTER);preview.set_valign(Gtk.Align.CENTER)
                for n,child in enumerate(utilities[:9]):
                    preview.attach(launcher_image(child,22 if self.round_grid_icons else 24),n%3,n//3,1,1)
                art=preview
            else:
                size=badge_size if 'tile' in item else (78 if 'app' in item else 66)
                art=launcher_image(item,size)
            badge.add(OrbFace(art,button,self.fixed.reduced_motion,i%(3 if in_folder else 4),i//(3 if in_folder else 4)) if self.round_grid_icons else art)
            box.pack_start(HoverSlot(button,badge,badge_size,self.fixed.reduced_motion),False,False,0)
            text=label(item['name'],'app-name',0.5);text.set_line_wrap(True);text.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR);text.set_lines(2);text.set_justify(Gtk.Justification.CENTER);text.set_size_request(-1,50 if self.round_grid_icons else 52)
            box.pack_start(text,False,False,0);button.add(box)
            button.connect('clicked',self.app_clicked,item)
            self.put(button,*( (246+(i%3)*210,338+(i//3)*184,168,174) if in_folder else launcher_bounds(i)),dynamic=True);button.show_all()

    def close_folder(self):
        self.folder=None;self.page=self.root_page;self.render_apps()

    def open_app(self,item):
        if item.get('folder'):
            self.root_page=self.page;self.folder='Utilities';self.page=0
            self.hide_keyboard();self.render_apps();return
        try:
            if 'custom' in item: launch_custom(item['custom'])
            else: item['app'].launch([],self.window.get_display().get_app_launch_context())
            self.hide_keyboard();self.window.iconify()
        except GLib.Error as exc:
            self.empty.set_text('Could not open this app');self.empty.show()

    @staticmethod
    def hide_keyboard():
        try:
            Gio.bus_get_sync(Gio.BusType.SESSION,None).call('sm.puri.OSK0','/sm/puri/OSK0','sm.puri.OSK0','SetVisible',GLib.Variant('(b)',(False,)),None,Gio.DBusCallFlags.NONE,1000,None,None,None)
        except GLib.Error:pass

    def show_settings(self,page):
        self.disconnect_volume()
        self.page_name=page;self.generation+=1;self.notice.set_text('')
        titles={'overview':'Settings', **{key:title for key,title,*_ in TILES}}
        self.header.set_text(titles[page]);self.header.get_style_context().add_class('heading')
        old=self.content.get_child()
        if old:self.content.remove(old)
        overview=page=='overview'
        self.back.set_visible(not overview)
        self.content.set_no_show_all(overview)
        self.content.set_visible(not overview)
        for tile in self.settings_tiles.values():
            tile.set_visible(overview)
        if overview:return
        self.body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=20)
        self.body.set_margin_start(8);self.body.set_margin_end(8);self.body.set_margin_top(8);self.body.set_margin_bottom(8)
        self.content.add(self.body)
        if page=='network':self.network_page()
        elif page=='bluetooth':self.bluetooth_page()
        elif page=='sound':self.sound_page()
        elif page=='display':self.display_page()
        elif page=='appearance':self.appearance_page()
        elif page=='about':self.about_page()
        self.content.show_all();self.content.get_vadjustment().set_value(0)

    def group(self,title=None):
        if title:self.body.pack_start(label(title.upper(),'section'),False,False,0)
        group=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0);group.get_style_context().add_class('group')
        self.body.pack_start(group,False,False,0);return group

    def row(self,group,title,symbol=None,value=None,action=None,widget=None):
        if group.get_children():group.pack_start(Gtk.Separator(),False,False,0)
        row=Gtk.Button() if action else Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        row.get_style_context().add_class('setting-row')
        if action:row.connect('clicked',lambda _:action());row.get_accessible().set_name(title)
        box=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=16)
        if symbol:box.pack_start(icon(symbol,30),False,False,0)
        box.pack_start(label(title),True,True,0)
        if widget:box.pack_end(widget,False,False,0)
        elif value is not None:
            value_label=label(str(value),'secondary',1);value_label.set_max_width_chars(22);box.pack_end(value_label,False,False,0)
        elif action:box.pack_end(icon('go-next-symbolic',22),False,False,0)
        if action:row.add(box)
        else:row.pack_start(box,True,True,0)
        group.pack_start(row,False,False,0);return row

    def footnote(self,text):
        note=label(text,'secondary');note.set_line_wrap(True);note.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR);note.set_lines(4)
        self.body.pack_start(note,False,False,0)

    def async_value(self,argv,callback):
        generation=self.generation
        def done(value,error):
            if self.window and generation==self.generation:
                if error:self.notice.set_text(error[:220])
                else:callback(value);self.body.show_all()
            return False
        run_async(argv,done)

    def set_command(self,argv,success=None):
        self.notice.set_text('Applying…')
        def done(value,error):
            if self.window:
                self.notice.set_text(error[:220] if error else 'Updated')
                if success:success(not error)
            return False
        run_async(argv,done)

    def network_page(self):
        group=self.group('Connections')
        self.row(group,'Checking connections…','wifi')
        def loaded(value):
            for child in group.get_children():group.remove(child)
            for line in value.splitlines():
                parts=line.split(':',2)
                if len(parts)==3 and parts[1] in ('wifi','ethernet'):
                    self.row(group,'Wi-Fi' if parts[1]=='wifi' else 'USB' if parts[0]=='usb0' else 'Ethernet','wifi' if parts[1]=='wifi' else 'network',parts[2].title())
        self.async_value(['nmcli','-t','-f','DEVICE,TYPE,STATE','device'],loaded)
        details=self.group('Wi-Fi')
        self.async_value(['nmcli','-g','GENERAL.CONNECTION,IP4.ADDRESS','device','show','wlan0'],lambda value:[self.row(details,'Network' if i==0 else 'Address','wifi' if i==0 else None,line) for i,line in enumerate(value.splitlines()) if line])
        self.row(self.group(),'Manage connections','network',action=lambda:self.external(['lp-connection-editor']))
        self.footnote('Saved connections and passwords are managed by the existing network manager.')

    def bluetooth_page(self):
        group=self.group()
        self.bluetooth_switch=Gtk.Switch();self.bluetooth_switch.set_valign(Gtk.Align.CENTER);self.bluetooth_switch.set_sensitive(False)
        self.row(group,'Bluetooth','bluetooth',widget=self.bluetooth_switch)
        def loaded(value):
            powered='Powered: yes' in value
            self.bluetooth_switch.set_active(powered);self.bluetooth_switch.set_sensitive(True)
            self.bluetooth_switch.connect('state-set',self.bluetooth_set)
            if 'off-blocked' in value:self.footnote('Bluetooth is blocked by the system. Enable it in the advanced controls before pairing a device.')
        self.async_value(['bluetoothctl','show'],loaded)
        devices=self.group('Paired devices')
        self.async_value(['bluetoothctl','devices','Paired'],lambda value:[self.row(devices,line.split(' ',2)[-1],'bluetooth') for line in value.splitlines()] if value else self.row(devices,'No paired devices'))
        self.row(self.group(),'Advanced controls','classic',action=lambda:self.external(['rpcc']))

    def bluetooth_set(self,switch,state):
        if self.page_name!='bluetooth' or self.closing:return True
        if self.syncing:return False
        switch.set_sensitive(False)
        def done(ok):
            if self.window and self.page_name=='bluetooth':
                self.syncing=True
                switch.set_state(state if ok else not state);switch.set_active(state if ok else not state);switch.set_sensitive(True)
                self.syncing=False
        self.set_command(['bluetoothctl','power','on' if state else 'off'],done)
        return True

    def sound_page(self):
        group=self.group('Output')
        self.volume=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,100,1)
        self.volume.set_draw_value(False);self.volume.set_hexpand(True);self.volume.set_sensitive(False)
        self.volume.set_margin_start(24);self.volume.set_margin_end(24);self.volume.set_size_request(-1,68)
        self.volume_label=label('Loading…','secondary')
        self.volume_label.set_width_chars(6);self.volume_label.set_max_width_chars(6)
        self.row(group,'Volume','sound',widget=self.volume_label);group.pack_start(self.volume,False,False,0)
        self.mute=Gtk.Switch();self.mute.set_valign(Gtk.Align.CENTER);self.mute.set_sensitive(False)
        self.row(group,'Mute',widget=self.mute)
        def loaded(value):
            match=re.search(r'Volume: ([0-9.]+)',value)
            level=round(float(match.group(1))*100) if match else 0
            self.volume.set_value(level);self.volume_label.set_text(f'{level}%');self.volume.set_sensitive(True)
            self.mute.set_active('[MUTED]' in value);self.mute.set_sensitive(True)
            self.volume_handler=self.volume.connect('value-changed',self.volume_changed)
            self.mute.connect('state-set',self.mute_set)
        self.async_value(['wpctl','get-volume','@DEFAULT_AUDIO_SINK@'],loaded)
        self.footnote('Adjusts the current audio output. Your volume and mute state are preserved when opening this page.')

    def volume_changed(self,scale):
        if self.page_name!='sound' or self.closing:return
        level=round(scale.get_value());self.volume_label.set_text(f'{level}%')
        if self.pending_volume:GLib.source_remove(self.pending_volume)
        def apply():
            self.pending_volume=None;self.set_command(['wpctl','set-volume','@DEFAULT_AUDIO_SINK@',f'{level}%']);return False
        self.pending_volume=GLib.timeout_add(180,apply)

    def mute_set(self,switch,state):
        if self.page_name!='sound' or self.closing:return True
        if self.syncing:return False
        switch.set_sensitive(False)
        def done(ok):
            if self.window and self.page_name=='sound':
                self.syncing=True
                switch.set_state(state if ok else not state);switch.set_active(state if ok else not state);switch.set_sensitive(True)
                self.syncing=False
        self.set_command(['wpctl','set-mute','@DEFAULT_AUDIO_SINK@','1' if state else '0'],done);return True

    def display_page(self):
        group=self.group('Round display')
        self.row(group,'Resolution','display','1080 × 1080')
        self.row(group,'Layout',None,'Full screen')
        self.row(group,'Touchscreen',None,'WaveShare')
        self.row(group,'Touch keyboard','keyboard','Off')
        self.footnote('Brightness is controlled on the display hardware. The touch calibration and display mode are unchanged.')
        self.row(self.group(),'Advanced display settings','classic',action=lambda:self.external(['rpcc']))

    def keyboard_show(self):
        self.set_command(['gdbus','call','--session','--dest','sm.puri.OSK0','--object-path','/sm/puri/OSK0','--method','sm.puri.OSK0.SetVisible','true'])

    def appearance_page(self):
        group=self.group('Interface')
        self.row(group,'Appearance','appearance','Dark')
        self.row(group,'Accent',None,'Soft green')
        self.row(group,'Typeface',None,'Rubik')
        self.row(group,'Animations',None,'Dock & Apps reveal')
        self.footnote('Files, Apps and Settings share the same large controls and circular layout.')
        self.row(self.group(),'Desktop preferences','classic',action=lambda:self.external(['rpcc']))

    def about_page(self):
        group=self.group('This Raspberry Pi')
        self.row(group,'Name','about',os.uname().nodename)
        model=Path('/proc/device-tree/model')
        self.row(group,'Model',None,model.read_text().strip('\0').replace('Raspberry Pi ','') if model.exists() else 'Raspberry Pi')
        self.row(group,'System',None,'Raspberry Pi OS')
        space=shutil.disk_usage(Path.home())
        self.row(group,'Available storage',None,f'{space.free/1024**3:.1f} GB')
        self.row(self.group(),'Advanced settings','classic',action=lambda:self.external(['rpcc']))

    def external(self,argv):
        if not shutil.which(argv[0]):
            self.notice.set_text('This control is not installed. Use the network icon on the home screen.');return
        subprocess.Popen(argv,start_new_session=True,stdin=subprocess.DEVNULL)

    def key(self,_,event):
        if event.keyval==Gdk.KEY_Escape:
            if self.mode=='settings' and self.page_name!='overview':self.show_settings('overview')
            elif self.mode=='launchpad' and self.query:self.search.set_text('')
            elif self.mode=='launchpad' and self.folder:self.close_folder()
            else:self.window.close()
            return True
        if self.mode=='launchpad' and event.keyval in (Gdk.KEY_Page_Down,Gdk.KEY_Page_Up):
            self.change_page(1 if event.keyval==Gdk.KEY_Page_Down else -1);return True
        return False

    def audit(self):
        a=self.window.get_allocation();records=[]
        for widget in self.placed:
            if not widget.get_visible():continue
            b=widget.get_allocation();x,y=widget.translate_coordinates(self.window,0,0)
            radius=max(math.hypot(px-540,py-540) for px in (x,x+b.width) for py in (y,y+b.height))
            records.append({'name':widget.get_accessible().get_name(),'bounds':[x,y,b.width,b.height],'radius':round(radius,2)})
        result={'window':[a.width,a.height],'mode':self.mode,'page':self.page_name,'outside_circle':[r for r in records if r['radius']>515],'widgets':records}
        if self.audit_path:Path(self.audit_path).write_text(json.dumps(result,indent=2))
        return False

    def disconnect_volume(self):
        if self.volume_handler:
            self.volume.disconnect(self.volume_handler)
            self.volume_handler=None

    def before_close(self,*_):
        self.closing=True
        self.disconnect_volume()
        return False

    def destroyed(self,*_):
        if self.apps_reload_source:
            GLib.source_remove(self.apps_reload_source);self.apps_reload_source=None
        self.hide_keyboard();self.window=None;self.generation+=1
        if self.pending_volume:GLib.source_remove(self.pending_volume);self.pending_volume=None

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['launchpad','settings']);parser.add_argument('--audit');args=parser.parse_args()
    GLib.set_prgname('aroundos-'+args.mode)
    if not args.audit and activate('aroundos-'+args.mode):raise SystemExit(0)
    Shell(args.mode,args.audit).run([])
