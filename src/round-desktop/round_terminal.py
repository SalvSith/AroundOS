#!/usr/bin/env python3
"""A circle-safe native terminal; VTE owns the PTY and terminal emulation."""
import os
import math
from pathlib import Path
import pwd
import signal
import sys

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
# The optional per-user typelib uses the distribution's installed VTE runtime.
gi.require_version('GIRepository', '2.0')
from gi.repository import GIRepository
GIRepository.Repository.prepend_search_path(str(Path.home() / '.local/lib/aroundos-round/girepository-1.0'))
gi.require_version('Vte', '2.91')
from gi.repository import Gtk, Gdk, Gio, GLib, Pango, Vte
from round_ui import SHELL_CSS, icon
from round_dock import DockHover
from round_shell import label
from round_windows import activate

# A conventional left-aligned terminal grid in the round display's central chord.
# The surrounding canvas is the same color, edge to edge: there is no card/frame.
TEXT_BOUNDS = (152, 210, 776, 640)
SCROLL_BOUNDS = (946, 352, 12, 376)
DOCK_BOUNDS = (332, 936, 416, 120)
CONTROL_SIZE = 56
# Home: radius 470 + 39 px rim; Terminal: radius 476 + 33 px rim.
# Both bottom edges sit 31 px inside the 1080 px display.
DOCK_RADIUS = 476
PALETTE = ('#202023', '#ed6a6a', '#a3ed75', '#e8c77b', '#78a9ef', '#c398eb', '#77d5d1', '#d7d7df',
           '#777782', '#ff9292', '#bcf79a', '#f4dba5', '#a2c6ff', '#dfb7ff', '#a3eee8', '#f5f5f7')


def control_position(index):
    """The simplified arc shares the home dock’s bottom clearance."""
    center_x = 404 + index*68
    center_y = 540 + math.sqrt(DOCK_RADIUS**2 - (center_x-540)**2)
    return center_x-CONTROL_SIZE//2, round(center_y-CONTROL_SIZE/2)


def color(value):
    result = Gdk.RGBA()
    result.parse(value)
    return result


def shell_command():
    shell = pwd.getpwuid(os.getuid()).pw_shell or '/bin/sh'
    if not os.path.isfile(shell) or not os.access(shell, os.X_OK):
        shell = '/bin/sh'
    return [shell, '-i']


class Terminal(Gtk.Application):
    def __init__(self, argv=None, directory=None):
        super().__init__(application_id='org.aroundos.Terminal')
        self.argv = argv if argv is not None else shell_command()
        self.directory = str(directory or Path.home())
        self.window = None
        self.placed = []
        self.pid = None
        self.starting = False
        self.closed = False
        self.font_size = 13
        self.prompt = None
        self.cancel = None
        self.last_exit = None

    def do_activate(self):
        if self.window:
            activate('aroundos-terminal')
            self.window.present()
            self.terminal.grab_focus()
            return
        self.window = Gtk.ApplicationWindow(application=self, title='Terminal · AroundOS')
        self.window.set_name('round-shell')
        self.window.set_decorated(False)
        self.window.set_default_size(1080, 1080)
        self.window.connect('delete-event', self.request_close)
        self.window.connect('destroy', self.destroyed)
        self.window.connect('key-press-event', self.key)
        css = Gtk.CssProvider()
        css.load_from_data(SHELL_CSS + b'''
#round-shell {background:#101012;}
#round-shell vte-terminal {padding:0;background:#101012;}
#round-shell button.terminal-tool {background:transparent;border:1px solid transparent;border-radius:24px;}
#round-shell button.terminal-tool:hover,#round-shell button.terminal-tool:focus {background:alpha(white,0.10);}
#round-shell button.terminal-tool:active {background:#344d31;border-color:#a3ed75;}
#round-shell .terminal-status {font:18px 'Rubik';color:#a1a1aa;}
#round-shell .terminal-prompt {background:#202023;border:1px solid #414148;border-radius:28px;padding:28px;}
#round-shell .prompt-title {font:600 28px "Rubik";color:#f5f5f7;}
#round-shell .terminal-prompt button.control {font:500 21px "Rubik";}
#round-shell .terminal-prompt button.control:not(.destructive-action) {background:#303034;}
''')
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, 900)
        self.overlay = Gtk.Overlay()
        self.overlay.add(Gtk.DrawingArea())
        self.fixed = Gtk.Fixed()
        self.overlay.add_overlay(self.fixed)
        self.window.add(self.overlay)
        self.status = label('Starting shell…', 'terminal-status', 0.5)
        self.status.set_no_show_all(True)
        self.put(self.status, 300, 868, 480, 30)
        self.terminal = Vte.Terminal()
        self.terminal.set_font(Pango.FontDescription('Monospace 13'))
        self.terminal.set_colors(color('#f5f5f7'), color('#101012'), [color(c) for c in PALETTE])
        self.terminal.set_color_cursor(color('#a3ed75'))
        self.terminal.set_cursor_blink_mode(Vte.CursorBlinkMode.OFF)
        self.terminal.set_scrollback_lines(10000)
        self.terminal.set_scroll_on_output(False)
        self.terminal.set_scroll_on_keystroke(True)
        self.terminal.set_mouse_autohide(True)
        self.terminal.connect('child-exited', self.child_exited)
        self.terminal.connect('char-size-changed', self.sync_grid)
        self.terminal.connect('selection-changed', lambda _: self.copy.set_sensitive(self.terminal.get_has_selection()))
        self.terminal.connect('window-title-changed', self.title_changed)
        # A frameless box allocates the fixed text region to VTE and propagates
        # font metric changes, keeping the shell's grid in sync with its pixels.
        self.viewport = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.viewport.pack_start(self.terminal, True, True, 0)
        self.put(self.viewport, *TEXT_BOUNDS)
        self.scrollbar = Gtk.Scrollbar(orientation=Gtk.Orientation.VERTICAL, adjustment=self.terminal.get_vadjustment())
        self.scrollbar.set_opacity(0)
        self.scrollbar.set_sensitive(False)
        adjustment = self.terminal.get_vadjustment()
        adjustment.connect('changed', self.update_scrollbar)
        self.put(self.scrollbar, *SCROLL_BOUNDS)
        self.dock = Gtk.Image.new_from_file(str(Path(__file__).with_name('editor-dock.svg')))
        self.dock.get_accessible().set_name('Terminal tools')
        self.put(self.dock, *DOCK_BOUNDS)
        self.copy = self.button('Copy selection', 'edit-copy-symbolic', lambda _: self.copy_selection())
        self.paste = self.button('Paste clipboard', 'edit-paste-symbolic', lambda _: self.paste_clipboard())
        self.restart = self.button('Start a new shell', 'view-refresh-symbolic', lambda _: self.start_shell())
        self.options_button = self.button('Text size', 'font-select-symbolic', lambda _: self.options())
        self.close_button = self.button('Close Terminal', 'window-close-symbolic', lambda _: self.window.close())
        self.controls = [self.copy, self.paste, self.restart, self.options_button, self.close_button]
        for index, button in enumerate(self.controls):
            self.put(button, *control_position(index), CONTROL_SIZE, CONTROL_SIZE)
        DockHover(self.fixed, self.controls)
        self.copy.set_sensitive(False)
        self.window.show_all()
        self.window.maximize()
        # Let VTE receive its actual allocation before creating the PTY.
        GLib.idle_add(self.start_shell)

    def update_scrollbar(self, adjustment):
        # Keep its allocation stable across shell resets; an unallocated hidden
        # GTK overlay child can otherwise reappear before receiving its bounds.
        scrollable = adjustment.get_upper() > adjustment.get_page_size()+1
        self.scrollbar.set_opacity(1 if scrollable else 0)
        self.scrollbar.set_sensitive(scrollable)

    def put(self, widget, x, y, width, height):
        self.fixed.put(widget, x, y)
        widget.set_size_request(width, height)
        self.placed.append(widget)
        return widget

    def button(self, name, symbol, callback):
        button = Gtk.Button()
        button.get_style_context().add_class('terminal-tool')
        button.add(icon(symbol, 26))
        button.get_accessible().set_name(name)
        button.set_tooltip_text(name)
        button.connect('clicked', callback)
        return button

    def text_button(self, name, callback):
        button = Gtk.Button(label=name)
        button.get_style_context().add_class('control')
        button.get_style_context().add_class('body')
        button.connect('clicked', callback)
        return button

    def start_shell(self):
        if self.closed or self.starting or self.pid is not None:
            return False
        self.last_exit = None
        self.starting = True
        self.restart.set_sensitive(False)
        self.paste.set_sensitive(False)
        self.status.set_text('Starting shell…')
        self.status.show()
        self.terminal.reset(True, True)
        self.cancel = Gio.Cancellable()
        self.terminal.spawn_async(Vte.PtyFlags.DEFAULT, self.directory, self.argv,
                                 ['TERM=xterm-256color', 'COLORTERM=truecolor'],
                                 GLib.SpawnFlags.DEFAULT, None, None, -1, self.cancel,
                                 self.spawned, None)
        return False

    def spawned(self, terminal, pid, error, data=None):
        self.starting = False
        if self.closed:
            if pid > 0:
                try: os.kill(pid, signal.SIGHUP)
                except ProcessLookupError: pass
            return
        if error:
            self.pid = None
            self.status.set_text('Shell could not start · use ↻ to retry')
            self.status.show()
            self.status.set_tooltip_text(str(error))
            self.restart.set_sensitive(True)
            return
        # A very short command can exit before the async spawn callback arrives.
        if self.last_exit is not None:
            return
        self.pid = pid
        self.status.hide()
        self.paste.set_sensitive(True)
        self.title_changed(terminal)
        terminal.grab_focus()

    def title_changed(self, terminal):
        if self.pid is not None:
            title = terminal.get_window_title() or f'{Path(self.argv[0]).name} · {self.directory}'
            self.status.set_text(title)

    def child_exited(self, terminal, status):
        self.last_exit = status
        self.pid = None
        if self.closed:
            return
        code = os.waitstatus_to_exitcode(status)
        self.status.set_text(f'Shell finished ({code}) · use ↻ to start again')
        self.status.show()
        self.restart.set_sensitive(True)
        self.paste.set_sensitive(False)

    def copy_selection(self):
        self.terminal.copy_clipboard_format(Vte.Format.TEXT)
        self.terminal.grab_focus()

    def paste_clipboard(self):
        if self.pid is not None:
            self.terminal.paste_clipboard()
        self.terminal.grab_focus()

    def sync_grid(self, terminal, char_width, char_height):
        # VTE can change font metrics without GTK reallocating a fixed-size
        # region. Update its grid explicitly so the PTY receives SIGWINCH too.
        width, height = terminal.get_allocated_width(), terminal.get_allocated_height()
        if width > 1 and height > 1 and char_width > 0 and char_height > 0:
            terminal.set_size(max(2, width // char_width), max(1, height // char_height))

    def set_font_size(self, size):
        self.font_size = max(10, min(20, size))
        self.terminal.set_font(Pango.FontDescription(f'Monospace {self.font_size}'))
        self.sync_grid(self.terminal, self.terminal.get_char_width(), self.terminal.get_char_height())
        self.terminal.grab_focus()

    def dismiss_prompt(self):
        if self.prompt:
            self.overlay.remove(self.prompt)
            self.prompt = None
        self.fixed.set_sensitive(True)
        self.terminal.grab_focus()

    def show_prompt(self, title, actions, destructive=None, detail=None):
        self.dismiss_prompt()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.get_style_context().add_class('terminal-prompt')
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_size_request(560, -1)
        heading = Gtk.Label(label=title, xalign=0)
        heading.get_style_context().add_class('prompt-title')
        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        copy.pack_start(heading, False, False, 0)
        if detail:
            explanation = Gtk.Label(label=detail, xalign=0)
            explanation.get_style_context().add_class('secondary')
            copy.pack_start(explanation, False, False, 0)
        box.pack_start(copy, False, False, 0)
        buttons = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        buttons.set_homogeneous(True)
        box.pack_start(buttons, False, False, 0)
        for name, callback in actions:
            button = self.text_button(name, lambda _, action=callback: action())
            if name == destructive:
                button.get_style_context().add_class("destructive-action")
            button.set_size_request(-1, 62)
            buttons.pack_start(button, True, True, 0)
        self.prompt = box
        self.fixed.set_sensitive(False)
        self.overlay.add_overlay(box)
        box.show_all()
        buttons.get_children()[0].grab_focus()

    def options(self):
        def resize(delta):
            self.set_font_size(self.font_size + delta)
            self.dismiss_prompt()
        self.show_prompt('Terminal text size', [('Larger', lambda: resize(1)),
                         ('Smaller', lambda: resize(-1)), ('Done', self.dismiss_prompt)])

    def request_close(self, *_):
        if self.pid is None and not self.starting:
            return False
        self.show_prompt('Close this shell?',
                         [('Keep open', self.dismiss_prompt), ('Close shell', self.window.destroy)], destructive='Close shell',
                         detail='Running commands will stop.')
        return True

    def key(self, window, event):
        if self.prompt:
            if event.keyval == Gdk.KEY_Escape:
                self.dismiss_prompt()
                return True
            # Modal overlay: typing must not reach the shell underneath it.
            if event.keyval not in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab, Gdk.KEY_Return, Gdk.KEY_space,
                                    Gdk.KEY_Up, Gdk.KEY_Down):
                return True
            return False
        mods = event.state & Gtk.accelerator_get_default_mod_mask()
        if mods == (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK):
            key = Gdk.keyval_to_lower(event.keyval)
            if key == Gdk.KEY_c: self.copy_selection(); return True
            if key == Gdk.KEY_v: self.paste_clipboard(); return True
            if key in (Gdk.KEY_plus, Gdk.KEY_equal): self.set_font_size(self.font_size+1); return True
            if key in (Gdk.KEY_minus, Gdk.KEY_underscore): self.set_font_size(self.font_size-1); return True
            if key in (Gdk.KEY_0, Gdk.KEY_parenright): self.set_font_size(13); return True
        return False

    def destroyed(self, *_):
        self.closed = True
        if self.cancel:
            self.cancel.cancel()
        if self.pid is not None:
            try: os.kill(self.pid, signal.SIGHUP)
            except ProcessLookupError: pass
        self.pid = None
        self.window = None


if __name__ == '__main__':
    GLib.set_prgname('aroundos-terminal')
    sys.exit(Terminal().run(sys.argv))
