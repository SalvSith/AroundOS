#!/usr/bin/env python3
"""Lightweight native NavCon app for AroundOS. Close hides; Quit releases input."""
from copy import deepcopy
import math
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, Gio, GLib, Pango
from core import CONTROLS, LABELS, KINDS, MODIFIERS, Profiles, Engine, Report, mapping, default_profile
from linux_input import Device, discover
from wayland_input import Output

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'src/round-desktop'))
from round_ui import SHELL_CSS, icon
from round_windows import activate


def text(value, style='body', align=0):
    label = Gtk.Label(label=value, xalign=align)
    label.get_style_context().add_class(style)
    label.set_line_wrap(True)
    label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    return label


def action_label(entry):
    return entry.get('label') or KINDS.get(entry['kind'], 'Unassigned')


class ControllerPicture(Gtk.Image):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.last_picture = None
        self.set_size_request(240, 370)
        self.render()

    def render(self):
        from gi.repository import GdkPixbuf
        from html import escape
        report = self.app.engine.report if self.app.engine else Report()
        state = (round(report.x / 12), round(report.y / 12), tuple(sorted(report.buttons)))
        if state == self.last_picture:return
        self.last_picture = state
        pieces = ['<svg xmlns="http://www.w3.org/2000/svg" width="240" height="370" viewBox="0 0 203 313">',
            '<defs><linearGradient id="body"><stop stop-color="#313134"/><stop offset="1" stop-color="#060608"/></linearGradient></defs>',
            '<path d="M94 6 C126 6 140 22 140 54 C140 93 131 126 127 157 C122 199 122 238 118 261 C115 281 107 286 94 286 C81 286 73 281 70 261 C66 238 66 199 61 157 C57 126 48 93 48 54 C48 22 62 6 94 6Z" fill="url(#body)" stroke="#6d6d75"/>']
        def button(name,x,y,radius,label):
            on = name in report.buttons
            ink = '#a3ed75' if on else '#a1a1aa'
            fill = '#30442c' if on else '#111114'
            pieces.append(f'<circle cx="{x}" cy="{y}" r="{radius}" fill="{fill}" stroke="{ink}" stroke-width="1.4"/>')
            size = 11 if len(label)>1 else 21
            pieces.append(f'<text x="{x}" y="{y+size*.35}" text-anchor="middle" font-family="sans-serif" font-size="{size}" fill="{ink}">{escape(label)}</text>')
        button('l3',94+(report.x-128)/128*5,53+(report.y-128)/128*5,29,'L3')
        for args in [('cross',71,105,15,'×'),('circle',117,105,15,'○'),('up',94,134,13,'↑'),
                     ('down',94,180,13,'↓'),('left',71,157,13,'←'),('right',117,157,13,'→'),
                     ('ps',94,221,15,'PS'),('l1',170,34,17,'L1'),('l2',170,84,17,'L2')]:button(*args)
        pieces.append('</svg>')
        loader=GdkPixbuf.PixbufLoader.new_with_type('svg')
        loader.write(''.join(pieces).encode());loader.close();self.set_from_pixbuf(loader.get_pixbuf())


class NavCon(Gtk.Application):
    def __init__(self, start_hardware=True, settings=None, application_id='org.aroundos.NavCon'):
        super().__init__(application_id=application_id, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.store = Profiles(settings or Path.home() / '.config/aroundos-navcon/profiles.json')
        self.start_hardware = start_hardware
        self.window = None
        self.output = None
        self.engine = None
        self.device = None
        self.watch = None
        self.ticker = None
        self.monitor = None
        self.ui_timer = None
        self.shutting_down = False
        self.page = 'Controller'
        self.status = 'Connect the Navigation Controller'
        self.notice_text = self.store.notice
        self.log = []
        self.placed = []
        self.building = False
        self.recording = False
        self.edit_control = None
        self.last_tick = time.monotonic()
        self.pair_process = None
        self.last_ui = None
        self.visible_buttons = {}

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()
        if self.start_hardware:
            self.monitor = GLib.timeout_add_seconds(1, self.scan)
            self.scan()
        self.ui_timer = GLib.timeout_add(200, self.refresh)

    def do_command_line(self, command_line):
        args = command_line.get_arguments()
        if '--quit' in args: self.quit()
        elif '--status' in args:
            report=self.engine.report if self.engine else Report()
            command_line.print_literal(json.dumps({'pid':os.getpid(),'status':self.status,
                'connected':bool(self.device),'transport':self.device.info['transport'] if self.device else None,
                'input_source':'raw HID' if self.device else None,
                'enabled':self.engine.enabled if self.engine else True,'armed':self.engine.armed if self.engine else False,
                'editing':bool(self.edit_control),'events':self.device.events if self.device else 0,
                'axes':[report.x,report.y,report.trigger],'buttons':sorted(report.buttons),
                'profile':self.store.current['name'],'window_visible':bool(self.window and self.window.get_visible())})+'\n')
        elif '--background' not in args: self.activate()
        return 0

    def do_activate(self):
        if self.window:
            self.window.fullscreen(); self.window.show_all(); self.window.present(); activate('aroundos-navcon'); self.refresh()
            return
        self.window = Gtk.ApplicationWindow(application=self, title='NavCon · AroundOS')
        self.window.set_name('round-shell'); self.window.set_decorated(False)
        self.window.set_default_size(1080,1080)
        self.window.connect('delete-event', lambda *_: self.hide_window())
        self.window.connect('key-press-event', self.key)
        css = Gtk.CssProvider()
        css.load_from_data(SHELL_CSS + b'''
        #round-shell .nav-tab {font:20px 'Rubik';background:#242426;border-radius:18px;}
        #round-shell .nav-tab:checked {background:#30442c;border-color:#a3ed75;}
        #round-shell .mapping {background:#202023;border-radius:18px;padding:10px 16px;}
        #round-shell .mapping.active {background:#30442c;border-color:#a3ed75;}
        #round-shell .nav-action {font:22px 'Rubik';background:#29292e;padding:10px 18px;min-height:38px;}
        #round-shell combobox button {font:22px 'Rubik';background:#29292e;padding:10px 16px;min-height:36px;}
        #round-shell .small {font:18px 'Rubik';color:#a1a1aa;}
        #round-shell viewport {background:transparent;}
        ''')
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, 900)
        overlay=Gtk.Overlay();overlay.add(Gtk.DrawingArea());self.window.add(overlay)
        self.fixed=Gtk.Fixed();overlay.add_overlay(self.fixed)
        self.put(text('NavCon','heading',.5),430,164,220,60)
        self.put(self.icon_button('Hide · keep controller running','window-close-symbolic',lambda:self.hide_window()),756,158,80,80)
        self.status_label=text(self.status,'secondary',.5);self.put(self.status_label,230,246,620,42)
        self.tabs={}
        for i,name in enumerate(['Controller','Buttons','Cursor','Profiles']):
            button=Gtk.ToggleButton(label=name);button.get_style_context().add_class('nav-tab')
            button.connect('clicked',lambda _,name=name:self.show_page(name))
            self.tabs[name]=button;self.put(button,190+i*176,306,164,60)
        self.content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14)
        self.put(self.content,190,390,700,448)
        self.setup=self.button('Bluetooth setup',self.pair);self.put(self.setup,315,864,244,64)
        self.reconnect=self.button('Reconnect',self.reconnect_device);self.put(self.reconnect,575,864,190,64)
        self.notice=text('Closing this window keeps controller control running.','small',.5)
        self.put(self.notice,260,940,560,42)
        self.show_page(self.page)
        self.window.fullscreen();self.window.show_all();self.refresh()

    def put(self,widget,x,y,w,h):
        self.fixed.put(widget,x,y);widget.set_size_request(w,h);self.placed.append(widget);return widget

    def button(self,label,callback):
        button=Gtk.Button(label=label);button.get_style_context().add_class('nav-action')
        button.connect('clicked',lambda _:callback());return button

    def icon_button(self,label,symbol,callback):
        button=Gtk.Button();button.get_style_context().add_class('control');button.add(icon(symbol,34))
        button.get_accessible().set_name(label);button.set_tooltip_text(label)
        button.connect('clicked',lambda _:callback());return button

    def hide_window(self):
        self.recording=False
        if self.edit_control: self.show_page('Buttons')
        if self.window:self.window.hide()
        return True

    def apps(self):
        subprocess.Popen(['/usr/bin/python3',str(ROOT/'src/round-desktop/round_shell.py'),'launchpad'],start_new_session=True)
        self.hide_window()

    def toggle_pause(self):
        if self.engine:self.engine.set_enabled(not self.engine.enabled)
        else:self.tell('Connect the controller first.')
        self.refresh()

    def tell(self,message):
        self.notice_text=message
        self.log.insert(0,message);self.log=self.log[:60]
        if self.window:self.notice.set_text(message)

    def show_page(self,name):
        if self.building:return
        self.building=True;self.recording=False;self.edit_control=None;self.page=name
        if self.engine:self.engine.set_editing(False)
        for widget in self.content.get_children():self.content.remove(widget);widget.destroy()
        self.visible_buttons={}
        for label,button in self.tabs.items():button.set_active(label==name)
        if name=='Controller':self.overview()
        elif name=='Buttons':self.buttons_page()
        elif name=='Cursor':self.cursor_page()
        else:self.profiles_page()
        self.building=False;self.content.show_all();self.last_ui=None

    def overview(self):
        row=Gtk.Box(spacing=25);self.content.pack_start(row,True,True,0)
        self.picture=ControllerPicture(self);row.pack_start(self.picture,False,False,0)
        body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16);row.pack_start(body,True,True,0)
        body.pack_start(text(self.store.current['name'],'body'),False,False,0)
        self.live=text('Waiting for live input…','secondary');body.pack_start(self.live,False,False,0)
        summary='\n'.join(f'{LABELS[c].split(" · ")[0]}  {action_label(self.store.current["mappings"][c])}' for c in ['l1','l2','circle','l3'])
        body.pack_start(text(summary,'secondary'),False,False,0)
        body.pack_start(self.button('Edit button mappings',lambda:self.show_page('Buttons')),False,False,0)
        body.pack_start(text('Bluetooth: press PS to reconnect.\nAll ten buttons are configurable.','small'),False,False,0)

    def buttons_page(self):
        grid=Gtk.Grid(column_spacing=16,row_spacing=12)
        self.content.pack_start(grid,False,False,0)
        for i,control in enumerate(CONTROLS):
            button=Gtk.Button();button.get_style_context().add_class('mapping');button.set_size_request(342,77)
            box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3)
            box.pack_start(text(LABELS[control],'small'),False,False,0)
            label=text(action_label(self.store.current['mappings'][control]),'secondary')
            label.set_ellipsize(Pango.EllipsizeMode.END);label.set_line_wrap(False);label.set_max_width_chars(22)
            box.pack_start(label,False,False,0);button.add(box)
            button.get_accessible().set_name('Edit '+LABELS[control]);button.connect('clicked',lambda _,c=control:self.editor(c))
            grid.attach(button,i%2,i//2,1,1);self.visible_buttons[control]=button

    def update(self,key,value):
        if self.building:return
        self.store.current[key]=value;self.store.save()
        if self.engine:self.engine.set_profile(self.store.current)

    def cursor_page(self):
        self.switch_row('Joystick cursor', 'cursorEnabled')
        for key,title,low,high,step in [('speed','Pointer speed',100,2200,50),('deadZone','Dead zone',.03,.4,.01)]:
            row=Gtk.Box(spacing=16);row.pack_start(text(title,'secondary'),False,False,0)
            value=text(f'{self.store.current[key]:.2f}' if key=='deadZone' else str(int(self.store.current[key])),'secondary',1)
            row.pack_end(value,False,False,0);self.content.pack_start(row,False,False,0)
            scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,low,high,step);scale.set_draw_value(False);scale.set_value(self.store.current[key]);scale.set_size_request(-1,46)
            def changed(widget,key=key,label=value):
                number=widget.get_value();label.set_text(f'{number:.2f}' if key=='deadZone' else str(int(number)));self.update(key,number)
            scale.connect('value-changed',changed);self.content.pack_start(scale,False,False,0)
        self.switch_row('Invert vertical movement','invertY')
        self.content.pack_start(self.button('Calibrate resting stick centre',self.calibrate),False,False,0)
        self.content.pack_start(text('Release the stick before calibrating. Settings save automatically.','small'),False,False,0)

    def switch_row(self,title,key):
        row=Gtk.Box(spacing=18);row.pack_start(text(title,'secondary'),True,True,0)
        switch=Gtk.Switch();switch.set_active(self.store.current[key]);switch.connect('notify::active',lambda s,_:self.update(key,s.get_active()))
        row.pack_end(switch,False,False,0);self.content.pack_start(row,False,False,0)

    def calibrate(self):
        if not self.engine or not self.engine.connected:return self.tell('Connect the controller first.')
        report=self.engine.report
        if report.buttons or abs(report.x-128)>=32 or abs(report.y-128)>=32:return self.tell('Release the stick and buttons, then calibrate again.')
        self.update('centerX',report.x);self.update('centerY',report.y);self.tell('Resting stick centre saved.')

    def profiles_page(self):
        combo=Gtk.ComboBoxText()
        for p in self.store.profiles:combo.append(p['id'],p['name'])
        combo.set_active_id(self.store.selected)
        def select(widget):
            if self.building:return
            self.store.selected=widget.get_active_id();self.store.save()
            if self.engine:self.engine.set_profile(self.store.current)
            self.show_page('Profiles')
        combo.connect('changed',select);self.content.pack_start(combo,False,False,0)
        entry=Gtk.Entry();entry.set_text(self.store.current['name']);entry.set_max_length(40);entry.set_size_request(-1,60)
        self.content.pack_start(entry,False,False,0)
        def rename():self.update('name',entry.get_text().strip() or 'Everyday');self.show_page('Profiles')
        row=Gtk.Box(spacing=12)
        row.pack_start(self.button('Rename',rename),True,True,0)
        row.pack_start(self.button('Duplicate',lambda:self.profile_action('duplicate')),True,True,0)
        delete=self.button('Delete',lambda:self.profile_action('delete'));delete.set_sensitive(len(self.store.profiles)>1);row.pack_start(delete,True,True,0)
        self.content.pack_start(row,False,False,0)
        self.content.pack_start(self.button('Restore initial Mac button mappings',self.reset_mappings),False,False,0)
        row=Gtk.Box(spacing=12);row.pack_start(text('Start at login','secondary'),True,True,0)
        switch=Gtk.Switch();switch.set_active(self.autostart_path().exists());switch.connect('notify::active',lambda w,_:self.set_autostart(w.get_active()))
        row.pack_end(switch,False,False,0);self.content.pack_start(row,False,False,0)
        self.content.pack_start(text('Closing NavCon keeps it running. Use Pause to stop input or Quit to exit completely.','small'),False,False,0)

    def profile_action(self,action):
        getattr(self.store,action)()
        if self.engine:self.engine.set_profile(self.store.current)
        self.show_page('Profiles')

    def reset_mappings(self):
        self.update('mappings',default_profile()['mappings']);self.tell('Mappings restored. Cross sends Escape and Circle sends Enter.')

    @staticmethod
    def autostart_path():return Path.home()/'.config/autostart/aroundos-navcon.desktop'

    def set_autostart(self,enabled):
        if self.building:return
        path=self.autostart_path()
        if enabled:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('[Desktop Entry]\nType=Application\nName=NavCon\nExec=/usr/bin/python3 "'+str(HERE/'app.py')+'" --background\nNoDisplay=true\n')
        else:path.unlink(missing_ok=True)

    def editor(self,control):
        self.building=True;self.recording=False;self.edit_control=control
        if self.engine:self.engine.set_editing(True)
        for child in self.content.get_children():self.content.remove(child);child.destroy()
        self.draft=deepcopy(self.store.current['mappings'][control])
        self.content.pack_start(text(LABELS[control],'body'),False,False,0)
        self.kind=Gtk.ComboBoxText()
        for kind,title in KINDS.items():self.kind.append(kind,title)
        self.kind.set_active_id(self.draft['kind']);self.content.pack_start(self.kind,False,False,0)
        self.shortcut=text(self.draft['label'] or 'Choose or record a shortcut','secondary');self.content.pack_start(self.shortcut,False,False,0)
        preset=Gtk.ComboBoxText();preset.append('','Common shortcuts…')
        presets={'Enter':(28,[]),'Escape':(1,[]),'Space':(57,[]),'Tab':(15,[]),'Backspace':(14,[]),
                 '↑':(103,[]),'↓':(108,[]),'←':(105,[]),'→':(106,[]),'Home':(102,[]),'End':(107,[]),
                 'Copy · Ctrl+C':(46,[29]),'Paste · Ctrl+V':(47,[29]),'Switch app · Alt+Tab':(15,[56]),
                 'Close window · Alt+F4':(62,[56]),'Hold Shift':(42,[]),'Hold Ctrl':(29,[]),'Hold Alt':(56,[]),'Hold Super':(125,[])}
        for title in presets:preset.append(title,title)
        preset.set_active(0)
        def selected(widget):
            title=widget.get_active_id()
            if title in presets:
                key,mods=presets[title];self.draft=mapping('modifier' if title.startswith('Hold ') else 'shortcut',key,mods,title)
                self.kind.set_active_id(self.draft['kind']);self.shortcut.set_text(title)
        preset.connect('changed',selected);self.content.pack_start(preset,False,False,0)
        self.record_button=self.button('Record keyboard shortcut',self.record);self.content.pack_start(self.record_button,False,False,0)
        self.content.pack_start(text('Controller output is paused while editing. Escape cancels recording.','small'),False,False,0)
        row=Gtk.Box(spacing=16)
        row.pack_start(self.button('Cancel',lambda:self.show_page('Buttons')),True,True,0)
        row.pack_start(self.button('Save mapping',self.save_mapping),True,True,0)
        self.content.pack_end(row,False,False,0);self.content.show_all();self.building=False

    def record(self):
        self.recording=True;self.shortcut.set_text('Press the keyboard shortcut…');self.record_button.grab_focus()

    def key(self,_,event):
        if not self.recording:return False
        if event.keyval==Gdk.KEY_Escape:
            self.recording=False;self.shortcut.set_text('Recording cancelled');return True
        code=event.hardware_keycode-8
        if code in MODIFIERS:return True
        if not 0<code<=255:return True
        mods=[];names=[]
        for mask,key,name in [(Gdk.ModifierType.CONTROL_MASK,29,'Ctrl'),(Gdk.ModifierType.MOD1_MASK,56,'Alt'),
                              (Gdk.ModifierType.SHIFT_MASK,42,'Shift'),(Gdk.ModifierType.SUPER_MASK,125,'Super')]:
            if event.state&mask:mods.append(key);names.append(name)
        label='+'.join(names+[Gdk.keyval_name(event.keyval) or str(code)])
        self.draft=mapping('shortcut',code,mods,label);self.kind.set_active_id('shortcut');self.shortcut.set_text(label);self.recording=False
        return True

    def save_mapping(self):
        kind=self.kind.get_active_id()
        if kind in ('shortcut','modifier') and not self.draft['key']:return self.tell('Choose or record a key first.')
        if kind=='modifier' and self.draft['key'] not in MODIFIERS:return self.tell('Choose Hold Shift, Ctrl, Alt or Super.')
        entry=deepcopy(self.draft) if kind in ('shortcut','modifier') else mapping(kind)
        entry['kind']=kind;self.store.current['mappings'][self.edit_control]=entry;self.store.save()
        if self.engine:self.engine.set_profile(self.store.current)
        self.show_page('Buttons');self.tell('Mapping saved. Release the stick and buttons to resume.')

    def pair(self):
        if self.pair_process and self.pair_process.poll() is None:return self.tell('Bluetooth setup is already running.')
        if not any(d['transport']=='USB' for d in discover()):return self.tell('For first-time pairing, connect the controller by USB, then tap Bluetooth setup.')
        if self.engine:self.engine.set_enabled(False)
        state=Path.home()/'.local/state/aroundos-navcon';state.mkdir(parents=True,exist_ok=True)
        with (state/'pairing.log').open('w') as log:
            self.pair_process=subprocess.Popen([sys.executable,str(HERE/'bluetooth_setup.py'),'--setup'],stdout=log,stderr=log,start_new_session=True)
        self.tell('Approve the Bluetooth setup prompt. Keep the USB cable connected.')

    def scan(self):
        if self.shutting_down:return False
        if self.pair_process and self.pair_process.poll() is not None:
            self.tell('Bluetooth registered. Unplug USB and press PS.' if self.pair_process.returncode==0 else 'Bluetooth setup did not finish. See ~/.local/state/aroundos-navcon/pairing.log.')
            self.pair_process=None
        try:
            devices=discover()
            if self.device:
                if not any(d['path']==self.device.info['path'] for d in devices):self.disconnect()
                elif self.engine and not self.engine.armed and self.device.snapshot() is not None:
                    self.engine.receive(self.device.snapshot())
            if not self.device and devices:
                if not self.output:self.output=Output()
                if not self.engine:self.engine=Engine(self.output,self.store.current,self.engine_action)
                self.device=Device(devices[0]);self.engine.connect(True)
                self.engine.set_editing(bool(self.edit_control))
                if self.device.report is not None:self.engine.receive(self.device.report)
                self.status='Connected · '+devices[0]['transport'];self.tell(self.status)
                self.watch=GLib.io_add_watch(self.device.fd,GLib.IO_IN|GLib.IO_HUP|GLib.IO_ERR|GLib.IO_NVAL,self.input_ready)
                self.last_tick=time.monotonic();self.ticker=GLib.timeout_add(8,self.tick)
        except (OSError,RuntimeError) as exc:
            self.disconnect();self.status=str(exc)
        return True

    def input_ready(self,_,condition):
        if condition&(GLib.IO_HUP|GLib.IO_ERR|GLib.IO_NVAL):
            self.watch=None;self.disconnect();return False
        try:
            for report in self.device.read():
                if report is None:self.engine.reset()
                else:self.engine.receive(report)
        except (OSError,RuntimeError) as exc:
            self.watch=None;self.disconnect();self.status=str(exc);return False
        return True

    def tick(self):
        try:
            now=time.monotonic();dt=now-self.last_tick;self.last_tick=now
            self.output.poll();self.engine.tick(dt,now)
        except (OSError,RuntimeError) as exc:
            self.ticker=None;self.disconnect();self.status=str(exc)
            if self.output:self.output.close();self.output=None
            self.engine=None;return False
        return True

    def engine_action(self,action):
        if action=='apps':GLib.idle_add(lambda:self.apps())

    def disconnect(self):
        if self.engine:
            try:self.engine.connect(False)
            except OSError:pass
        if self.watch:GLib.source_remove(self.watch);self.watch=None
        if self.ticker:GLib.source_remove(self.ticker);self.ticker=None
        if self.device:self.device.close();self.device=None
        self.status='Connect the Navigation Controller'

    def reconnect_device(self):self.disconnect();self.scan()

    def refresh(self):
        if self.shutting_down:return False
        if not self.window or not self.window.get_visible():return True
        status=self.status
        if self.engine and self.engine.connected:
            status+=' · '+('Paused' if not self.engine.enabled else 'Editing' if self.engine.editing else 'Ready' if self.engine.armed else 'Release all controls')
        self.status_label.set_text(status)
        self.notice.set_text(self.notice_text or 'Closing this window keeps controller control running.')
        report=self.engine.report if self.engine else Report()
        state=(report.x,report.y,report.trigger,tuple(sorted(report.buttons)),status)
        if state!=self.last_ui:
            self.last_ui=state
            if self.page=='Controller' and not self.edit_control:
                self.picture.render()
                self.live.set_text(f'Stick  {report.x:.0f}, {report.y:.0f}\nTrigger  {report.trigger:.0%}\n'+(' · '.join(LABELS[c] for c in sorted(report.buttons)) or 'No buttons held'))
            for control,button in self.visible_buttons.items():
                if not button.get_parent():continue
                context=button.get_style_context()
                context.add_class('active') if control in report.buttons else context.remove_class('active')
        return True

    def do_shutdown(self):
        self.shutting_down=True
        for source in (self.monitor,self.ui_timer):
            if source:GLib.source_remove(source)
        self.disconnect()
        if self.output:self.output.close()
        Gtk.Application.do_shutdown(self)


if __name__=='__main__':
    os.environ.setdefault('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}')
    os.environ.setdefault('WAYLAND_DISPLAY','wayland-0')
    os.environ.setdefault('DBUS_SESSION_BUS_ADDRESS',f"unix:path={os.environ['XDG_RUNTIME_DIR']}/bus")
    Gdk.set_program_class('aroundos-navcon')
    GLib.set_prgname('aroundos-navcon')
    app=NavCon()
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGTERM,lambda:app.quit())
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGINT,lambda:app.quit())
    sys.exit(app.run(sys.argv))
