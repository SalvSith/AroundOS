"""Home dock hover motion and label for the compact editor and terminal arcs."""
import math

from gi.repository import GdkPixbuf, GLib, Gtk


class DockHover:
    def __init__(self, page, buttons):
        self.page = page
        self.buttons = buttons
        self.scale = 1.0
        self.centers = []
        self.art = []
        self.zoom = [0.] * len(buttons)
        self.tip = None
        self.timer = None
        for button in buttons:
            x = page.child_get_property(button, 'x') + 28
            y = page.child_get_property(button, 'y') + 28
            self.centers.append((x, y))
            image = button.get_child()
            self.art.append((image.get_pixbuf(), image.get_pixel_size()))
            button.set_has_tooltip(False)
        self.bubble = Gtk.Overlay()
        self.bubble.set_no_show_all(True)
        self.background = Gtk.Image()
        self.caption = Gtk.Label()
        self.caption.set_margin_bottom(9)
        self.bubble.add(self.background)
        self.bubble.add_overlay(self.caption)
        self.bubble.set_overlay_pass_through(self.caption, True)
        page.put(self.bubble, 0, 0)
        page.connect('map', self.start)
        page.connect('unmap', self.stop)

    def start(self, *_):
        self.timer = GLib.timeout_add(33, self.tick)

    def stop(self, *_):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None
        self.update(None, None, reset=True)

    def tick(self):
        window = self.page.get_window()
        pointer = window.get_display().get_default_seat().get_pointer()
        under, _, _ = pointer.get_window_at_position()
        if (under and under.get_toplevel() == window.get_toplevel()
                and self.page.is_sensitive() and any(b.is_sensitive() for b in self.buttons)):
            _, x, y, _ = window.get_device_position(pointer)
            self.update(x, y)
        else:
            self.update(None, None)
        return True

    def update(self, px, py, reset=False):
        scale = self.scale
        nearest = None
        old_tip = self.tip
        self.tip = None
        for i, (button, (cx, cy)) in enumerate(zip(self.buttons, self.centers)):
            near = px is not None and abs(px - cx) <= 102 * scale and cy - 68 * scale <= py <= cy + 35 * scale
            target = math.exp(-1.6 * ((px - cx) / (85 * scale))**2) if near else 0.
            z = self.zoom[i] + (target - self.zoom[i]) * .26
            if reset or abs(target - z) < .005:
                z = target
            size = round((56 + 12 * z) * scale)
            top = round(cy - size / 2 - 20 * z * scale)
            if reset or z != self.zoom[i]:
                self.zoom[i] = z
                button.set_size_request(size, size)
                self.page.move(button, cx - size // 2, top)
                original, base = self.art[i]
                pixels = max(1, round(base * (1 + 32 / 52 * z) * scale))
                image = button.get_child()
                if pixels != image.get_pixel_size():
                    if original:
                        image.set_from_pixbuf(original.scale_simple(pixels, pixels, GdkPixbuf.InterpType.BILINEAR))
                    image.set_pixel_size(pixels)
            if near and abs(px - cx) <= 34 * scale and top - 12 * scale <= py <= top + size + 14 * scale:
                distance = abs(px - cx)
                if nearest is None or distance < nearest:
                    nearest = distance
                    self.tip = (button.get_accessible().get_name(), cx, top)
        if old_tip != self.tip:
            self.show_tip(old_tip)

    def show_tip(self, previous):
        if not self.tip:
            self.bubble.hide()
            return
        name, cx, top = self.tip
        if previous is None or previous[0] != name:
            self.caption.set_markup('<span font_desc="Rubik 17" foreground="#f5f7fc">'
                                    + GLib.markup_escape_text(name) + '</span>')
            tw, _ = self.caption.get_layout().get_pixel_size()
            width = tw + 34
            middle = width / 2
            svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="53">
              <path fill="#0e1014" fill-opacity=".97" stroke="#a6b0c2" stroke-opacity=".30"
                d="M22 .5 H{width-22} a21.5 21.5 0 0 1 0 43 H{middle+10}
                   c-5 0 -6 9 -10 9 s-5 -9 -10 -9 H22 a21.5 21.5 0 0 1 0 -43 Z"/>
            </svg>'''
            loader = GdkPixbuf.PixbufLoader.new_with_type('svg')
            loader.write(svg.encode())
            loader.close()
            self.background.set_from_pixbuf(loader.get_pixbuf())
        width = self.background.get_pixbuf().get_width()
        self.page.move(self.bubble, cx - width // 2, top - 57)
        self.background.show()
        self.caption.show()
        self.bubble.show()
