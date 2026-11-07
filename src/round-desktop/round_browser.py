#!/usr/bin/env python3
"""Native browser chrome for AroundOS's 1080px circular display."""
import json
import math
import os
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlsplit


def address_uri(text):
    text = text.strip()
    if not text:
        return None
    try:
        parsed = urlsplit(text)
    except ValueError:
        return 'https://duckduckgo.com/?q=' + quote(text, safe='')
    if parsed.scheme.lower() in ('http', 'https') and parsed.netloc:
        return text
    # A host:port is not a URI scheme. Keep local development hosts useful.
    if not re.search(r'\s', text) and re.match(r'^(localhost|\[[0-9a-fA-F:]+\]|[^/:]+\.[^/:]+)(:\d+)?([/?#]|$)', text):
        return ('http://' if text.startswith(('localhost', '127.', '[::1]')) else 'https://') + text
    return 'https://duckduckgo.com/?q=' + quote(text, safe='')


# Page content continues behind the floating toolbar to the physical bottom.
# The circular panel naturally masks the lower corners while scrolling brings
# content back into the wider, readable middle of the display.
PAGE_BOUNDS = (90, 260, 900, 820)
BACKGROUND_SCRIPT = r"""(() => {
    // Sites often paint a full-height app wrapper rather than body/html.
    // Sample the visible page edges and composite the ancestors at each point.
    // Canvas normalises modern CSS colours (including oklch/color()) for us.
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 1;
    const context = canvas.getContext('2d', {willReadFrequently: true});
    const color = value => {
        context.clearRect(0, 0, 1, 1);
        context.fillStyle = value;
        context.fillRect(0, 0, 1, 1);
        return Array.from(context.getImageData(0, 0, 1, 1).data);
    };
    const blend = (base, rgba) => base.map((v,i) =>
        Math.round(rgba[i]*rgba[3]/255 + v*(1-rgba[3]/255)));
    const rootStyle = getComputedStyle(document.documentElement);
    const rootColor = color(rootStyle.backgroundColor);
    const propagatedBody = rootColor[3] === 0 && rootStyle.backgroundImage === 'none';
    let canvasColor = blend([255,255,255], rootColor);
    if (propagatedBody && document.body)
        canvasColor = blend(canvasColor, color(getComputedStyle(document.body).backgroundColor));
    const sample = (x, y) => {
        const layers = [];
        let element = document.elementFromPoint(x, y);
        while (element) {
            layers.unshift(element);
            element = element.parentElement;
        }
        let out = canvasColor.slice();
        for (const node of layers) {
            if (node === document.documentElement || (propagatedBody && node === document.body)) continue;
            const rgba = color(getComputedStyle(node).backgroundColor);
            const alpha = rgba[3] / 255;
            out = out.map((base, i) => Math.round(rgba[i]*alpha + base*(1-alpha)));
        }
        return out;
    };
    const samples = [];
    // Ignore the scrollbar and any small header/footer; favour the side canvas
    // of the document instead of an unrelated theme-colour metadata tag.
    for (const y of [.18, .32, .5, .68, .82]) {
        for (const x of [12, innerWidth-24]) samples.push(sample(x, innerHeight*y));
    }
    const counts = new Map();
    for (const rgb of samples) {
        const key = rgb.join(',');
        counts.set(key, (counts.get(key) || 0) + 1);
    }
    const winner = [...counts].sort((a,b) => b[1]-a[1])[0][0];
    return JSON.stringify(winner.split(',').map(Number));
})()"""


def control_position(index):
    x = 404 + index * 68
    return x - 28, round(540 + math.sqrt(476**2 - (x-540)**2) - 28)


# Keep URL parsing importable without the target's native libraries.
def main():
    # Pi 4's DMA-BUF path corrupts the GTK surface on this display.
    os.environ.setdefault('WEBKIT_DISABLE_DMABUF_RENDERER', '1')
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('Gdk', '3.0')
    try:
        gi.require_version('WebKit2', '4.1')
    except ValueError:
        sys.exit('Browser requires gir1.2-webkit2-4.1. Install it with: sudo apt install gir1.2-webkit2-4.1')
    from gi.repository import Gtk, Gdk, Gio, GLib, WebKit2
    from round_ui import SHELL_CSS, icon
    from round_shell import label
    from round_windows import activate

    class Browser(Gtk.Application):
        def __init__(self):
            super().__init__(application_id='org.aroundos.Browser', flags=Gio.ApplicationFlags.HANDLES_OPEN)
            self.window = None
            self.placed = []
            self.appearance_generation = 0
            self.appearance_pending = False
            self.appearance_timer = None
            self.page_rgb = None

        def put(self, widget, x, y, width, height):
            self.fixed.put(widget, x, y)
            widget.set_size_request(width, height)
            self.placed.append(widget)
            return widget

        def button(self, name, symbol, callback):
            button = Gtk.Button()
            button.add(icon(symbol, 28))
            button.get_style_context().add_class('browser-tool')
            button.set_tooltip_text(name)
            button.get_accessible().set_name(name)
            button.connect('clicked', callback)
            return button

        def do_activate(self):
            if self.window:
                activate('aroundos-browser')
                self.window.present()
                return
            self.window = Gtk.ApplicationWindow(application=self, title='Browser · AroundOS')
            self.window.set_name('round-shell')
            self.window.set_decorated(False)
            self.window.set_default_size(1080, 1080)
            self.window.connect('key-press-event', self.key)
            self.window.connect('destroy', self.destroyed)
            css = Gtk.CssProvider()
            css.load_from_data(SHELL_CSS + b'''
#round-shell .browser-tool {background:transparent;border-radius:50%;}
#round-shell .browser-tool:hover {background:alpha(white,0.10);}
#round-shell .browser-address {font:20px 'Rubik';}
#round-shell progressbar trough {min-height:3px;background:#242426;}
#round-shell progressbar progress {min-height:3px;background:#a3ed75;}
''')
            Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, 900)
            self.page_css = Gtk.CssProvider()
            # Scope the page colour to this window, never to other AroundOS apps.
            self.window.get_style_context().add_provider(self.page_css, 1000)
            overlay = Gtk.Overlay()
            overlay.add(Gtk.DrawingArea())
            self.fixed = Gtk.Fixed()
            overlay.add_overlay(self.fixed)
            self.window.add(overlay)
            self.address = Gtk.Entry()
            self.address.get_style_context().add_class('browser-address')
            self.address.set_placeholder_text('Search or enter address')
            self.address.get_accessible().set_name('Search or enter address')
            self.address.connect('activate', lambda entry: self.navigate(entry.get_text()))
            self.put(self.address, 278, 182, 524, 56)
            self.progress = Gtk.ProgressBar()
            self.put(self.progress, 300, 247, 480, 4)
            data = Path(GLib.get_user_data_dir()) / 'aroundos-browser'
            cache = Path(GLib.get_user_cache_dir()) / 'aroundos-browser'
            data.mkdir(parents=True, exist_ok=True)
            cache.mkdir(parents=True, exist_ok=True)
            manager = WebKit2.WebsiteDataManager(base_data_directory=str(data), base_cache_directory=str(cache))
            context = WebKit2.WebContext.new_with_website_data_manager(manager)
            context.set_sandbox_enabled(True)
            context.get_cookie_manager().set_persistent_storage(str(data / 'cookies.sqlite'), WebKit2.CookiePersistentStorage.SQLITE)
            context.connect('download-started', self.download)
            self.web = WebKit2.WebView.new_with_context(context)
            self.web.get_settings().set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
            self.web.get_settings().set_enable_fullscreen(False)
            self.web.get_settings().set_javascript_can_open_windows_automatically(False)
            self.web.connect('notify::uri', self.changed)
            self.web.connect('notify::is-loading', self.changed)
            self.web.connect('notify::estimated-load-progress', self.changed)
            self.web.connect('load-changed', self.changed)
            self.web.connect('load-changed', self.page_loaded)
            self.web.connect('load-failed', self.failed)
            self.web.connect('web-process-terminated', lambda *_: self.status.set_text('Page stopped. Press reload to try again.'))
            self.web.connect('decide-policy', self.policy)
            self.web.connect('permission-request', lambda view, request: (request.deny(), True)[1])
            # Keep website layout intact inside a wide, circle-safe viewport.
            # Its canvas colour continues across the surrounding native surface.
            self.put(self.web, *PAGE_BOUNDS)
            self.status_css = Gtk.CssProvider()
            self.status = label('', 'secondary', 0.5)
            self.status.get_style_context().add_provider(self.status_css, 1000)
            self.put(self.status, 280, 256, 520, 30)
            from gi.repository import GdkPixbuf
            svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="348" height="120"><path d="M38 60.157867 A476 476 0 0 0 310 60.157867" fill="none" stroke="#343d38" stroke-width="66" stroke-linecap="round"/><path d="M38 60.157867 A476 476 0 0 0 310 60.157867" fill="none" stroke="#1b2022" stroke-width="64" stroke-linecap="round"/></svg>'
            loader = GdkPixbuf.PixbufLoader.new_with_type('svg')
            loader.write(svg)
            loader.close()
            dock = Gtk.Image.new_from_pixbuf(loader.get_pixbuf())
            self.put(dock, 366, 936, 348, 120)
            self.back = self.button('Back', 'go-previous-symbolic', lambda _: self.web.go_back())
            self.forward = self.button('Forward', 'go-next-symbolic', lambda _: self.web.go_forward())
            self.reload = self.button('Reload or stop', 'view-refresh-symbolic', lambda _: self.web.stop_loading() if self.web.is_loading() else self.web.reload())
            controls = [self.back, self.forward, self.reload,
                        self.button('Home', 'user-home-symbolic', lambda _: self.home()),
                        self.button('Close Browser', 'window-close-symbolic', lambda _: self.window.close())]
            for index, button in enumerate(controls):
                self.put(button, *control_position(index), 56, 56)
            self.window.show_all()
            self.window.maximize()
            self.apply_page_color((16, 16, 18))
            self.appearance_timer = GLib.timeout_add_seconds(1, self.sample_page_color)
            self.home()

        def apply_page_color(self, rgb):
            if self.page_rgb == tuple(rgb):
                return
            self.page_rgb = tuple(rgb)
            red, green, blue = rgb
            self.page_css.load_from_data(
                f'#round-shell {{background:rgb({red},{green},{blue});}}'.encode())
            foreground = '#55555e' if sum(rgb) > 420 else '#b6b6bf'
            self.status_css.load_from_data(f'label {{color:{foreground};}}'.encode())

        def page_loaded(self, view, event):
            if event == WebKit2.LoadEvent.STARTED:
                # A callback from the previous document must never repaint this one.
                self.appearance_generation += 1
            elif event in (WebKit2.LoadEvent.COMMITTED, WebKit2.LoadEvent.FINISHED):
                self.sample_page_color()

        def sample_page_color(self):
            if not self.window:
                return False
            if self.appearance_pending or not self.web.get_uri():
                return True
            self.appearance_pending = True
            generation = self.appearance_generation
            def sampled(view, result, *_):
                self.appearance_pending = False
                try:
                    value = view.evaluate_javascript_finish(result)
                    rgb = json.loads(value.to_string())
                    if (self.window and generation == self.appearance_generation
                            and isinstance(rgb, list) and len(rgb) == 3
                            and all(type(c) is int and 0 <= c <= 255 for c in rgb)):
                        self.apply_page_color(rgb)
                except (GLib.Error, ValueError, TypeError):
                    pass  # Error/unsupported documents keep the last good canvas.
            # A private JS world avoids page-defined globals altering this read.
            self.web.evaluate_javascript(BACKGROUND_SCRIPT, -1, 'aroundos-appearance',
                                         None, None, sampled, None)
            return True

        def home(self):
            self.web.load_html('''<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{background:#101012;color:#f5f5f7;font:22px 'Rubik',sans-serif;text-align:center;margin:0}main{position:absolute;left:0;right:0;top:280px;transform:translateY(-50%);padding:0 40px}h1{font-size:42px}p{color:#a1a1aa}a{display:inline-block;padding:20px;margin:8px;background:#242426;color:#a3ed75;border-radius:22px;text-decoration:none}</style>
<main><h1>Browse the web</h1><p>Search or enter an address above.</p><a href="https://www.wikipedia.org">Wikipedia</a><a href="https://duckduckgo.com">Search</a></main>''', 'about:blank')
            self.address.set_text('')
            self.address.grab_focus()

        def navigate(self, text):
            uri = address_uri(text)
            if uri:
                self.status.set_text('')
                self.web.load_uri(uri)
                self.web.grab_focus()

        def changed(self, *_):
            uri = self.web.get_uri() or ''
            if not self.address.has_focus():
                self.address.set_text('' if uri == 'about:blank' else uri)
            self.back.set_sensitive(self.web.can_go_back())
            self.forward.set_sensitive(self.web.can_go_forward())
            self.progress.set_fraction(self.web.get_estimated_load_progress() if self.web.is_loading() else 0)
            self.progress.set_opacity(1 if self.web.is_loading() else 0)

        def failed(self, view, event, uri, error):
            if not error.matches(WebKit2.network_error_quark(), WebKit2.NetworkError.CANCELLED):
                self.status.set_text('Could not load this page. Check the address or reload.')
            return False  # Keep WebKit's error page and certificate protection.

        def policy(self, view, decision, kind):
            if kind in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION, WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):
                action = decision.get_navigation_action()
                uri = action.get_request().get_uri()
                if urlsplit(uri).scheme.lower() not in ('https', 'http', 'about'):
                    decision.ignore()
                    self.status.set_text('This link requires another application.')
                    return True
                if kind == WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION:
                    decision.ignore()
                    if action.is_user_gesture():
                        self.web.load_uri(uri)
                    return True
            return False

        def download(self, context, download):
            # Downloads are explicit rather than silently writing to disk.
            download.cancel()
            self.status.set_text('Downloads are not supported in this first version.')

        def key(self, window, event):
            ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
            if ctrl and event.keyval == Gdk.KEY_l:
                self.address.grab_focus(); self.address.select_region(0, -1)
            elif event.keyval == Gdk.KEY_F5 or ctrl and event.keyval == Gdk.KEY_r:
                self.web.reload()
            elif event.keyval == Gdk.KEY_Escape:
                self.web.stop_loading(); self.web.grab_focus()
            elif ctrl and event.keyval in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_minus, Gdk.KEY_0):
                zoom = 1 if event.keyval == Gdk.KEY_0 else self.web.get_zoom_level() * (1/1.1 if event.keyval == Gdk.KEY_minus else 1.1)
                self.web.set_zoom_level(max(.5, min(3, zoom)))
            else:
                return False
            return True

        def do_open(self, files, count, hint):
            self.do_activate()
            if files:
                uri = files[0].get_uri()
                if urlsplit(uri).scheme in ('https', 'http'):
                    self.navigate(uri)

        def destroyed(self, *_):
            self.appearance_generation += 1
            if self.appearance_timer:
                GLib.source_remove(self.appearance_timer)
                self.appearance_timer = None
            self.web.stop_loading()
            self.window = None

    GLib.set_prgname('aroundos-browser')
    return Browser().run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
