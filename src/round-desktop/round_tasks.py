#!/usr/bin/env python3
"""Touch-friendly Task Manager for the 1080 px AroundOS circular desktop."""
from concurrent.futures import ThreadPoolExecutor
import math
import sys

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, Gio, GLib, Gtk, Pango
from round_ui import SHELL_CSS, icon
from round_processes import Sampler, can_end, end_process, filter_processes, readable_memory

CSS = SHELL_CSS + b'''
#round-shell .metric {background:#202023;border-radius:26px;}
#round-shell .metric-value {font:600 32px 'Rubik';color:#a3ed75;}
#round-shell .process-name {font:24px 'Rubik';}
#round-shell .process-detail {font:17px 'Rubik';color:#a1a1aa;}
#round-shell .process-row {background:#202023;border-radius:22px;padding:0 20px;}
#round-shell .selected-sort {background:#30442c;color:#b1ef8e;border-color:#6a9455;}
#round-shell .danger {background:#48282b;color:#ffb1b5;}
#round-shell .action {font:23px 'Rubik';}
'''


def row_bounds(index):
    y, height = 456 + index * 74, 68
    dy = max(abs(y - 540), abs(y + height - 540))
    left = math.ceil(540 - math.sqrt(500 ** 2 - dy ** 2))
    return left, y, 1080 - 2 * left, height


class Tasks(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.aroundos.Tasks')
        self.window = None
        self.closed = False
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.sampler = Sampler()
        self.snapshot = None
        self.busy = False
        self.timer = None
        self.page = 0
        self.sort = 'cpu'
        self.query = ''
        self.paused = False
        self.selected = None
        self.confirming = None
        self.action_message = None
        self.placed = []
        self.list_widgets = []
        self.detail_widgets = []
        self.touching = False
        self.deferred = False

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        self.window = Gtk.ApplicationWindow(application=self, title='Task Manager · AroundOS')
        self.window.set_name('round-shell')
        self.window.set_decorated(False)
        self.window.set_default_size(1080, 1080)
        self.window.connect('destroy', self.destroyed)
        self.window.connect('key-press-event', self.key)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, 900)
        overlay = Gtk.Overlay()
        overlay.add(Gtk.DrawingArea())
        self.fixed = Gtk.Fixed()
        overlay.add_overlay(self.fixed)
        self.window.add(overlay)
        self.put(self.label('Task Manager', 'heading'), 290, 148, 440, 68)
        self.put(self.button('Close Task Manager', lambda _: self.window.close(), 'window-close-symbolic'), 752, 148, 76, 76)
        self.cpu_value = self.metric('CPU', 'Across all cores', 240)
        self.memory_value = self.metric('Memory', 'Used / total RAM', 548)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text('Search name, PID or user')
        self.search.get_accessible().set_name('Search processes')
        self.search.connect('search-changed', self.search_changed)
        self.put(self.search, 202, 330, 590, 64, self.list_widgets)
        self.pause = self.button('Pause updates', lambda _: self.toggle_pause(), 'media-playback-pause-symbolic')
        self.put(self.pause, 808, 330, 70, 64, self.list_widgets)
        self.sort_buttons = {}
        for index, (mode, title) in enumerate((('cpu', 'CPU ↓'), ('memory', 'Memory ↓'), ('name', 'Name A–Z'))):
            button = self.button('Sort by ' + mode, lambda _, m=mode: self.set_sort(m), text=title)
            self.sort_buttons[mode] = button
            self.put(button, 238 + index * 206, 406, 192, 40, self.list_widgets)
        self.rows = []
        for index in range(5):
            button = Gtk.Button()
            button.get_style_context().add_class('process-row')
            box = Gtk.Box(spacing=14)
            names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            names.set_valign(Gtk.Align.CENTER)
            name = self.label('', 'process-name')
            detail = self.label('', 'process-detail')
            names.pack_start(name, False, False, 0)
            names.pack_start(detail, False, False, 0)
            box.pack_start(names, True, True, 0)
            cpu = self.label('', 'process-name', 1)
            cpu.set_size_request(112, -1)
            memory = self.label('', 'secondary', 1)
            memory.set_size_request(128, -1)
            box.pack_start(cpu, False, False, 0)
            box.pack_start(memory, False, False, 0)
            button.add(box)
            button.process = None
            button.connect('clicked', self.row_clicked)
            self.put(button, *row_bounds(index), self.list_widgets)
            self.rows.append((button, name, detail, cpu, memory))
        self.previous = self.button('Previous processes', lambda _: self.change_page(-1), 'go-previous-symbolic')
        self.next = self.button('More processes', lambda _: self.change_page(1), 'go-next-symbolic')
        self.put(self.previous, 380, 850, 72, 64, self.list_widgets)
        self.page_label = self.label('', 'secondary', .5)
        self.put(self.page_label, 462, 860, 156, 44, self.list_widgets)
        self.put(self.next, 628, 850, 72, 64, self.list_widgets)
        self.status = self.label('Reading processes…', 'secondary', .5)
        self.put(self.status, 260, 926, 560, 40)
        self.empty = self.label('No matching processes', 'body', .5)
        self.put(self.empty, 240, 570, 600, 80, self.list_widgets)
        self.build_details()
        # Freeze row identities from press through release, including mouse input.
        self.press = Gtk.GestureMultiPress.new(self.window)
        self.press.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.press.connect('pressed', lambda *_: setattr(self, 'touching', True))
        self.press.connect('released', self.released)
        self.press.connect('cancel', self.released)
        self.window.show_all()
        self.window.maximize()
        self.render()
        self.window.set_focus(None)
        self.refresh()
        self.timer = GLib.timeout_add_seconds(2, self.refresh)

    def label(self, text, style='body', align=0):
        label = Gtk.Label(label=text, xalign=align)
        label.get_style_context().add_class(style)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(1)
        return label

    def put(self, widget, x, y, width, height, group=None):
        self.fixed.put(widget, x, y)
        widget.set_size_request(width, height)
        self.placed.append(widget)
        if group is not None:
            group.append(widget)
        return widget

    def button(self, name, callback, symbol=None, text=None):
        button = Gtk.Button()
        button.get_style_context().add_class('control')
        if symbol is None:
            button.get_style_context().add_class('text-control')
        button.get_style_context().add_class('action')
        button.get_accessible().set_name(name)
        button.set_tooltip_text(name)
        button.add(icon(symbol, 30) if symbol else Gtk.Label(label=text or name))
        button.connect('clicked', callback)
        return button

    def metric(self, title, subtitle, x):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        box.get_style_context().add_class('metric')
        for text, style in ((title, 'secondary'), ('—', 'metric-value'), (subtitle, 'process-detail')):
            child = self.label(text, style, .5)
            box.pack_start(child, True, True, 0)
        self.put(box, x, 226, 292, 94)
        return box.get_children()[1]

    def build_details(self):
        group = self.detail_widgets
        self.put(self.button('Back to processes', lambda _: self.back(), 'go-previous-symbolic'), 214, 348, 72, 64, group)
        self.detail_name = self.label('', 'heading')
        self.put(self.detail_name, 310, 344, 550, 64, group)
        self.detail_meta = self.label('', 'secondary', .5)
        self.put(self.detail_meta, 210, 428, 660, 48, group)
        self.detail_usage = self.label('', 'body', .5)
        self.put(self.detail_usage, 210, 496, 660, 58, group)
        self.detail_note = self.label('', 'body', .5)
        self.detail_note.set_line_wrap(True)
        self.detail_note.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.detail_note.set_justify(Gtk.Justification.CENTER)
        self.detail_note.set_lines(4)
        self.put(self.detail_note, 242, 568, 596, 140, group)
        self.end_button = self.button('End process', lambda _: self.confirm(False))
        self.force_button = self.button('Force quit', lambda _: self.confirm(True))
        self.force_button.get_style_context().add_class('danger')
        self.put(self.end_button, 280, 742, 250, 72, group)
        self.put(self.force_button, 550, 742, 250, 72, group)
        self.cancel_button = self.button('Cancel', lambda _: self.cancel_confirm())
        self.confirm_button = self.button('Confirm end', lambda _: self.perform_end())
        self.confirm_button.get_style_context().add_class('danger')
        self.put(self.cancel_button, 280, 742, 250, 72, group)
        self.put(self.confirm_button, 550, 742, 250, 72, group)

    def refresh(self):
        if self.closed:
            return False
        if self.busy or self.paused:
            return True
        self.busy = True
        future = self.pool.submit(self.sampler.sample)
        def done(future):
            try:
                result, error = future.result(), None
            except Exception as exc:
                result, error = None, str(exc)
            GLib.idle_add(self.received, result, error)
        future.add_done_callback(done)
        return True

    def received(self, snapshot, error):
        self.busy = False
        if self.closed or self.paused:
            return False
        if error:
            self.status.set_text('Unable to refresh processes')
            self.status.set_tooltip_text(error)
            return False
        self.snapshot = snapshot
        if self.touching:
            self.deferred = True
        else:
            self.render()
        return False

    def released(self, *_):
        self.touching = False
        GLib.idle_add(self.flush_render)

    def flush_render(self):
        if not self.closed and self.deferred:
            self.deferred = False
            self.render()
        return False

    def render(self):
        details = self.selected is not None
        for widget in self.list_widgets:
            widget.set_visible(not details)
        for widget in self.detail_widgets:
            widget.set_visible(details)
        if self.snapshot:
            cpu = self.snapshot.cpu
            self.cpu_value.set_text('—' if cpu is None else f'{cpu:.0f}%')
            self.memory_value.set_text(f'{readable_memory(self.snapshot.used)} / {self.snapshot.total / 1024 ** 3:.1f} GB')
            self.status.set_text(('Paused · ' if self.paused else 'Live · ') + f'{len(self.snapshot.processes)} processes')
        self.pause.get_child().set_opacity(.4 if self.paused else 1)
        self.pause.set_tooltip_text('Resume updates' if self.paused else 'Pause updates')
        self.pause.get_accessible().set_name('Resume updates' if self.paused else 'Pause updates')
        if details:
            self.render_details()
            return
        for mode, button in self.sort_buttons.items():
            style = button.get_style_context()
            (style.add_class if mode == self.sort else style.remove_class)('selected-sort')
        items = filter_processes(self.snapshot.processes if self.snapshot else (), self.query, self.sort)
        pages = max(1, math.ceil(len(items) / 5))
        self.page = max(0, min(self.page, pages - 1))
        self.previous.set_sensitive(self.page > 0)
        self.next.set_sensitive(self.page + 1 < pages)
        self.page_label.set_text(f'{self.page + 1} / {pages}')
        self.empty.set_visible(not items)
        self.empty.set_text('No matching processes' if self.snapshot else 'Reading processes…')
        shown = items[self.page * 5:(self.page + 1) * 5]
        for index, (button, name, detail, cpu, memory) in enumerate(self.rows):
            button.set_visible(index < len(shown))
            button.process = shown[index] if index < len(shown) else None
            if button.process:
                process = button.process
                name.set_text(process.name)
                detail.set_text(f'{process.user} · PID {process.pid}')
                cpu.set_text('—' if process.cpu is None else f'{process.cpu:.1f}%')
                memory.set_text(readable_memory(process.memory))
                button.get_accessible().set_name(f'{process.name}, PID {process.pid}, CPU {cpu.get_text()}, memory {memory.get_text()}')

    def current_process(self):
        return next((p for p in self.snapshot.processes if p.identity == self.selected.identity), None) if self.snapshot and self.selected else None

    def row_clicked(self, button):
        if button.process:
            self.selected = button.process
            self.confirming = None
            self.action_message = None
            self.render()

    def render_details(self):
        process = self.current_process()
        self.detail_name.set_text(self.selected.name)
        states = {'R': 'Running', 'S': 'Sleeping', 'D': 'Waiting', 'T': 'Stopped', 't': 'Stopped', 'Z': 'Zombie', 'I': 'Idle'}
        self.detail_meta.set_text(f'PID {self.selected.pid} · {self.selected.user} · ' + (states.get(process.state, process.state) if process else 'Exited'))
        self.detail_usage.set_text((f'CPU {process.cpu:.1f}%' if process and process.cpu is not None else 'CPU —') + '     Memory ' + (readable_memory(process.memory) if process else '—'))
        confirming = self.confirming is not None
        allowed = process is not None and can_end(process)
        self.end_button.set_visible(not confirming)
        self.force_button.set_visible(not confirming)
        self.cancel_button.set_visible(confirming)
        self.confirm_button.set_visible(confirming)
        for button in (self.end_button, self.force_button, self.confirm_button):
            button.set_sensitive(allowed)
        if not process:
            note = 'This process has exited.'
        elif confirming:
            note = ('Force quit immediately? Unsaved work may be lost.' if self.confirming else 'Ask this process to end? Save any work first.')
        elif self.action_message:
            note = self.action_message
        elif not allowed:
            note = 'This process is read-only. You can end your own running processes.'
        else:
            note = 'End asks the process to stop. Force quit stops it immediately. CPU: 100% equals one core.'
        self.detail_note.set_text(note)

    def confirm(self, force):
        self.action_message = None
        self.confirming = force
        self.confirm_button.get_child().set_text('Force quit' if force else 'End process')
        self.confirm_button.get_accessible().set_name('Confirm force quit' if force else 'Confirm end process')
        self.render_details()

    def cancel_confirm(self):
        self.confirming = None
        self.render_details()

    def perform_end(self):
        if self.confirming is None:
            return
        force = self.confirming
        self.confirming = None
        try:
            end_process(self.selected, force)
            message = 'Force quit sent.' if force else 'End requested. Some processes may take time to stop.'
        except ProcessLookupError:
            message = 'This process has already exited.'
        except (OSError, ValueError) as exc:
            message = f'Could not end process: {exc}'
        self.action_message = message
        self.render_details()
        self.refresh()

    def back(self):
        self.selected = None
        self.confirming = None
        self.action_message = None
        self.render()

    def search_changed(self, entry):
        self.query = entry.get_text()
        self.page = 0
        self.render()

    def set_sort(self, sort):
        self.sort = sort
        self.page = 0
        self.render()

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause.get_child().set_from_icon_name('media-playback-start-symbolic' if self.paused else 'media-playback-pause-symbolic', Gtk.IconSize.DIALOG)
        self.render()
        if not self.paused:
            self.refresh()

    def change_page(self, delta):
        self.page += delta
        self.render()

    def key(self, window, event):
        if event.keyval == Gdk.KEY_Escape:
            if self.confirming is not None:
                self.cancel_confirm()
            elif self.selected:
                self.back()
            elif self.query:
                self.search.set_text('')
            else:
                self.window.close()
            return True
        return False

    def destroyed(self, *_):
        self.closed = True
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.window = None


if __name__ == '__main__':
    # Match the overridden desktop ID so the native panel resolves its icon.
    GLib.set_prgname('lxtask')
    sys.exit(Tasks().run(sys.argv))
