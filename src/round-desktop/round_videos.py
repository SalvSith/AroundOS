#!/usr/bin/env python3
"""Circle-safe local video playback with distro-maintained GStreamer codecs."""
from pathlib import Path
import math
import sys
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, Gdk, Gio, GLib, Gst, Pango
from round_ui import SHELL_CSS, icon
from round_shell import label, launch_custom
from round_dock import DockHover
from round_windows import activate

EXTENSIONS = set('.mp4 .m4v .mkv .webm .mov .avi .wmv .asf .mpg .mpeg .mpe .ts .mts .m2ts .vob .ogv .ogg .3gp .3g2 .flv .f4v .mxf .divx .rm .rmvb'.split())
MIME_TYPES = ('video/mp4', 'video/x-matroska', 'video/webm', 'video/quicktime',
              'video/x-msvideo', 'video/x-ms-wmv', 'video/x-ms-asf', 'video/mpeg',
              'video/mp2t', 'video/ogg', 'video/3gpp', 'video/3gpp2', 'video/x-flv',
              'application/mxf', 'application/vnd.rn-realmedia', 'video/x-m4v')


def clock_text(seconds):
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f'{hours}:{minutes:02}:{seconds:02}' if hours else f'{minutes}:{seconds:02}'


class Videos(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.aroundos.Videos', flags=Gio.ApplicationFlags.HANDLES_OPEN)
        Gst.init(None)
        self.window = self.player = self.bus = None
        self.path = None
        self.siblings = []
        self.ready = self.playing = self.ended = self.immersive = False
        self.updating = False
        self.duration = 0
        self.timer = None
        self.placed = []

    def put(self, widget, x, y, width, height):
        self.fixed.put(widget, x, y)
        widget.set_size_request(width, height)
        self.placed.append(widget)
        return widget

    def button(self, name, symbol, callback):
        button = Gtk.Button()
        button.add(icon(symbol, 26))
        button.get_accessible().set_name(name)
        button.set_tooltip_text(name)
        button.get_style_context().add_class('video-tool')
        button.connect('clicked', callback)
        return button

    def do_activate(self):
        if self.window:
            activate('aroundos-videos'); self.window.present(); return
        self.window = Gtk.ApplicationWindow(application=self, title='Videos · AroundOS')
        self.window.set_name('round-shell'); self.window.set_decorated(False)
        self.window.set_default_size(1080, 1080)
        self.window.connect('destroy', self.destroyed)
        self.window.connect('key-press-event', self.key)
        css = Gtk.CssProvider()
        css.load_from_data(SHELL_CSS + b' #round-shell .video-card {background:#202023;border-radius:24px;} #round-shell button.video-tool {background:transparent;border:0;border-radius:24px;padding:0;} #round-shell button.video-tool:hover {background:alpha(white,0.1);} #round-shell scale trough {min-height:8px;} #round-shell scale slider {min-width:24px;min-height:24px;}')
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, 900)
        self.fixed = Gtk.Fixed(); self.window.add(self.fixed)
        self.title = self.put(label('Videos', 'heading', 0.5), 340, 164, 400, 60)
        self.card = self.put(Gtk.EventBox(), 128, 296, 824, 548)
        self.card.get_style_context().add_class('video-card')
        self.surface = Gtk.Overlay(); self.card.add(self.surface)
        self.video_box = Gtk.Box(); self.video_box.set_border_width(18); self.surface.add(self.video_box)
        self.message = label('Choose a video from Files', 'body', 0.5)
        self.message.set_line_wrap(True); self.message.set_max_width_chars(35)
        self.message.set_halign(Gtk.Align.CENTER); self.message.set_valign(Gtk.Align.CENTER)
        self.surface.add_overlay(self.message)
        self.open_button = self.button('Open Files', 'system-file-manager-symbolic', lambda _: launch_custom('files'))
        self.put(self.open_button, 700, 240, 60, 50)
        self.caption = self.put(label('Open a video from Files', 'secondary', 0.5), 240, 850, 600, 36)
        self.caption.set_ellipsize(Pango.EllipsizeMode.MIDDLE); self.caption.set_max_width_chars(1)
        self.seek = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 1)
        self.seek.set_draw_value(False); self.seek.get_accessible().set_name('Video position')
        self.seek.connect('change-value', self.seek_changed)
        self.put(self.seek, 280, 886, 520, 40)
        self.time_label = self.put(label('0:00 / 0:00', 'secondary', 0.5), 400, 924, 280, 32)
        self.volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.05)
        self.volume.set_value(0.8); self.volume.set_draw_value(False)
        self.volume.get_accessible().set_name('Volume'); self.volume.set_tooltip_text('Volume')
        self.volume.connect('value-changed', self.volume_changed)
        self.put(self.volume, 420, 250, 240, 40)
        dock = Gtk.Image.new_from_file(str(Path(__file__).with_name('editor-dock.svg')))
        self.fixed.put(dock, 332, 936); dock.set_size_request(416, 120)
        self.previous = self.button('Previous video', 'go-previous-symbolic', lambda _: self.step(-1))
        self.play_button = self.button('Play or pause', 'media-playback-start-symbolic', lambda _: self.toggle())
        self.next = self.button('Next video', 'go-next-symbolic', lambda _: self.step(1))
        self.full_button = self.button('Full screen · tap video to return', 'view-fullscreen-symbolic', lambda _: self.fullscreen())
        self.close_button = self.button('Close', 'window-close-symbolic', lambda _: self.window.close())
        self.controls = [self.previous, self.play_button, self.next, self.full_button, self.close_button]
        for i, button in enumerate(self.controls):
            x = 404 + 68*i; y = round(540 + math.sqrt(476**2 - (x-540)**2))
            self.put(button, x-28, y-28, 56, 56)
        self.dock_hover = DockHover(self.fixed, self.controls)
        self.tap = Gtk.GestureMultiPress.new(self.card)
        self.tap.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.tap.connect('released', lambda *_: self.fullscreen() if self.immersive else None)
        self.window.show_all(); self.window.maximize()
        self.update_controls()
        self.timer = GLib.timeout_add(250, self.tick)

    def do_open(self, files, count, hint):
        self.do_activate()
        if files:
            path = files[0].get_path()
            if path: self.open_path(Path(path))
            else: self.fail('Open a local video from Files.')

    def stop(self):
        self.ready = self.playing = self.ended = False
        if self.bus:
            self.bus.disconnect(self.bus_handler); self.bus.remove_signal_watch(); self.bus = None
        if self.player:
            self.player.set_state(Gst.State.NULL); self.player = None
        for child in self.video_box.get_children(): child.destroy()
        self.duration = 0

    def open_path(self, path):
        if self.immersive: self.fullscreen()
        self.stop()
        self.path = path.absolute()
        self.caption.set_text(self.path.name); self.caption.set_tooltip_text(str(self.path))
        self.siblings = []
        self.update_controls()
        self.seek.set_value(0); self.time_label.set_text('0:00 / 0:00')
        if not self.path.is_file(): self.fail('This video could not be opened.\nChoose another file.'); return
        try:
            self.siblings = sorted((p for p in self.path.parent.iterdir() if p.is_file() and
                                    (p.suffix.lower() in EXTENSIONS or p == self.path)), key=lambda p: p.name.casefold())
        except OSError: self.siblings = [self.path]
        self.player = Gst.ElementFactory.make('playbin', None)
        sink = Gst.ElementFactory.make('gtksink', None)
        if self.player is None or sink is None:
            self.fail('Video playback needs the GStreamer GTK package.\nSee the Videos setup guide.'); return
        self.player.set_property('video-sink', sink)
        # Local files only; no network URLs, playlists, or automatic codec downloads.
        self.player.connect('source-setup', self.source_setup)
        self.player.set_property('uri', self.path.as_uri())
        self.player.set_property('volume', self.volume.get_value())
        widget = sink.get_property('widget')
        self.video_box.pack_start(widget, True, True, 0); widget.show()
        self.bus = self.player.get_bus(); self.bus.add_signal_watch()
        self.bus_handler = self.bus.connect('message', self.on_message)
        self.message.set_text('Loading…'); self.message.show()
        self.playing = True
        if self.player.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            self.fail('This video could not be played.\nIts codec may be unavailable or the file damaged.')

    def source_setup(self, player, source):
        factory = source.get_factory()
        if not factory or factory.get_name() != 'filesrc':
            # Schedule teardown on the GTK thread, not the streaming thread.
            GLib.idle_add(self.reject_source, player)

    def reject_source(self, player):
        if player == self.player: self.fail('Only local video files are supported.')
        return False

    def fail(self, message):
        self.stop(); self.message.set_text(message); self.message.show(); self.update_controls()

    def on_message(self, bus, message):
        if message.type == Gst.MessageType.ERROR:
            self.fail('This video could not be played.\nIts codec may be unavailable or the file damaged.')
        elif message.type == Gst.MessageType.EOS:
            self.playing = False; self.ended = True
            self.player.set_state(Gst.State.PAUSED); self.update_controls()
        elif message.type == Gst.MessageType.STATE_CHANGED and message.src == self.player:
            _, state, _ = message.parse_state_changed()
            if state in (Gst.State.PAUSED, Gst.State.PLAYING):
                self.ready = True; self.message.hide(); self.update_controls()

    def update_controls(self):
        index = self.siblings.index(self.path) if self.path in self.siblings else -1
        self.previous.set_sensitive(index > 0)
        self.next.set_sensitive(0 <= index < len(self.siblings)-1)
        self.play_button.set_sensitive(self.ready); self.full_button.set_sensitive(self.ready)
        self.seek.set_sensitive(self.ready and self.duration > 0)
        self.play_button.get_child().destroy()
        self.play_button.add(icon('media-playback-pause-symbolic' if self.playing else 'media-playback-start-symbolic', 26))
        self.play_button.get_child().show()

    def toggle(self):
        if not self.ready: return
        if self.ended:
            if not self.seek_to(0): return
            self.ended = False
        self.playing = not self.playing
        self.player.set_state(Gst.State.PLAYING if self.playing else Gst.State.PAUSED)
        self.update_controls()

    def seek_to(self, seconds):
        if not self.player or not self.ready: return False
        return self.player.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
                                       int(max(0, min(self.duration, seconds))*Gst.SECOND))

    def seek_changed(self, scale, scroll, value):
        if not self.updating and self.seek_to(value): self.ended = False
        return True

    def volume_changed(self, scale):
        if self.player: self.player.set_property('volume', scale.get_value())

    def tick(self):
        if self.player and self.ready:
            valid, duration = self.player.query_duration(Gst.Format.TIME)
            if valid and duration > 0: self.duration = duration/Gst.SECOND
            valid, position = self.player.query_position(Gst.Format.TIME)
            if valid:
                self.updating = True
                self.seek.set_range(0, max(1, self.duration)); self.seek.set_value(position/Gst.SECOND)
                self.updating = False
                self.time_label.set_text(f'{clock_text(position/Gst.SECOND)} / {clock_text(self.duration)}')
            self.seek.set_sensitive(self.duration > 0)
        return True

    def step(self, delta):
        if self.path not in self.siblings: return
        index = self.siblings.index(self.path)+delta
        if 0 <= index < len(self.siblings): self.open_path(self.siblings[index])

    def fullscreen(self):
        if not self.ready and not self.immersive: return
        self.immersive = not self.immersive
        # Fit the entire rectangle inside the physical circle, preserving all edges.
        for widget in self.fixed.get_children():
            if widget != self.card: widget.set_visible(not self.immersive)
        if self.immersive:
            self.fixed.move(self.card, 164, 164); self.card.set_size_request(752, 752)
            self.video_box.set_border_width(0); self.window.fullscreen()
        else:
            self.fixed.move(self.card, 128, 296); self.card.set_size_request(824, 548)
            self.video_box.set_border_width(18); self.window.unfullscreen(); self.window.maximize()
        self.card.set_tooltip_text('Tap to return to controls' if self.immersive else None)

    def key(self, window, event):
        if event.keyval == Gdk.KEY_Escape:
            if self.immersive: self.fullscreen()
            else: self.window.close()
        elif event.keyval == Gdk.KEY_space: self.toggle()
        elif event.keyval in (Gdk.KEY_f, Gdk.KEY_F): self.fullscreen()
        elif event.keyval in (Gdk.KEY_Left, Gdk.KEY_Right) and self.player:
            valid, position = self.player.query_position(Gst.Format.TIME)
            if valid: self.seek_to(position/Gst.SECOND + (-10 if event.keyval == Gdk.KEY_Left else 10))
        else: return False
        return True

    def destroyed(self, *_):
        if self.timer: GLib.source_remove(self.timer); self.timer = None
        self.stop(); self.window = None


if __name__ == '__main__':
    GLib.set_prgname('aroundos-videos')
    sys.exit(Videos().run(sys.argv))
