"""Illustrated navigation plates for the 1080 px circular Settings overview."""
from functools import lru_cache

import math
import os
from xml.sax.saxutils import escape

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk


# The outer rows follow the shorter chords of the display.
TILES = (
    ('network', 'Wi-Fi & Network', 186, 264, 422, 176),
    ('bluetooth', 'Bluetooth', 622, 264, 272, 176),
    ('sound', 'Sound', 128, 454, 326, 184),
    ('display', 'Display & Touch', 468, 454, 484, 184),
    ('appearance', 'Appearance', 186, 652, 376, 176),
    ('about', 'About AroundOS', 576, 652, 318, 176),
)


def illustration(page, width, height):
    if page == 'network':
        # A point source and expanding wavefronts, clipped by the plate edge.
        paths = ''.join(f'<circle r="{r}" stroke-width="{weight}"/>'
                        for r, weight in ((22, 5), (49, 4), (78, 3), (108, 2), (140, 1)))
        return '#bcdf99', '#d8efb8', f'''
          <g transform="translate({width - 65},30)" fill="none" stroke="#578350">{paths}
          <circle r="7" fill="#345438" stroke="none"/></g>'''
    if page == 'bluetooth':
        return '#29343c', '#384b59', '''
          <g fill="none" stroke="#7699a9" stroke-dasharray="2 8">
            <path d="M-8 80 H125 Q150 80 166 62 L222 5 H290"/>
            <path d="M-8 59 H93 Q117 59 133 43 L190 -14"/>
          </g>
          <g transform="translate(181,49)" fill="none">
            <circle r="45" stroke="#596d77"/><circle r="36" stroke="#617a86"/>
            <path d="M-12 -13 L13 13 L0 25 V-25 L13 -12 L-12 13"
                  stroke="#d3e7ee" stroke-width="3.6" stroke-linejoin="round"/>
          </g>'''
    if page == 'sound':
        envelope = (3, 5, 10, 17, 8, 15, 25, 11, 5, 14, 31, 39, 23, 9, 17,
                    27, 11, 6, 3, 7, 13, 8, 4, 2)
        bars = ''.join(f'<path d="M{25+i*12} {58-h} v{2*h}" opacity="{0.55+0.45*h/39:.2f}"/>'
                       for i, h in enumerate(envelope))
        return '#352f29', '#493c30', f'''
          <path d="M0 58 H{width}" stroke="#685044"/>
          <g stroke="#f2bc85" stroke-width="5" stroke-linecap="round">{bars}</g>'''
    if page == 'display':
        return '#252e2b', '#35433d', '''
          <g fill="none" stroke="#647c6e">
            <path d="M0 87 H485 M0 48 H485" stroke-dasharray="2 8"/>
            <path d="M196 9 L456 110 M209 110 L440 3" stroke-dasharray="3 6"/>
          </g>
          <g transform="translate(324,53) rotate(-13)">
            <path d="M-88 0 A88 37 0 0 1 88 0 V13 A88 37 0 0 1 -88 13 Z"
                  fill="#19211e" stroke="#a5bdae" stroke-width="2"/>
            <ellipse rx="88" ry="37" fill="#495c50" stroke="#c1d6c3" stroke-width="2"/>
            <ellipse rx="78" ry="30" fill="#26352e" stroke="#899e8c"/>
            <path d="M-69 0 H69 M0 -24 V24" stroke="#66806d" stroke-dasharray="2 5"/>
            <circle r="3" fill="#b7d7aa"/>
          </g>'''
    if page == 'appearance':
        return '#322e38', '#463d48', '''
          <g transform="translate(240,52) rotate(-18)">
            <circle cx="-43" r="41" fill="#8e7798"/>
            <circle r="41" fill="#cfaba9"/>
            <circle cx="43" r="41" fill="#e3cea5"/>
            <path d="M-21.5 -34.9 A41 41 0 0 1 -21.5 34.9 A41 41 0 0 1 -21.5 -34.9" fill="#b694ac"/>
            <path d="M21.5 -34.9 A41 41 0 0 1 21.5 34.9 A41 41 0 0 1 21.5 -34.9" fill="#dbc0aa"/>
          </g>'''
    pins = ''.join(f'<path d="M{x} 16 v-9 M{x} 76 v9 M179 {y} h-9 M239 {y} h9"/>'
                   for x, y in zip(range(187, 234, 9), range(24, 71, 9)))
    return '#2a3032', '#374043', f'''
      <g fill="none" stroke="#78898b"><path d="M112 0 L145 33 H169 M110 86 L145 57 H169
        M249 30 H266 L299 -3 M249 60 H269 L300 91 H325"/>
        <g stroke-width="3">{pins}</g>
        <rect x="179" y="16" width="60" height="60" rx="9" fill="#222b2d" stroke="#b4c3c2"/>
        <rect x="188" y="25" width="42" height="42" rx="4"/>
        <circle cx="196" cy="33" r="2" fill="#b4c3c2"/></g>'''


@lru_cache(maxsize=2 * len(TILES))
def plate_image(page, title, width, height, highlighted):
    base, light, art = illustration(page, width, height)
    ink = '#283c28' if page == 'network' else '#dde3df'
    caption = '#203420' if page == 'network' else '#f2f4f0'
    ring = (f'<rect x="1.5" y="1.5" width="{width-3}" height="{height-3}" rx="29" '
            'fill="none" stroke="#a3ed75" stroke-width="3"/>') if highlighted else ''
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">
      <defs>
        <linearGradient id="surface" x1="0" y1="1" x2="1" y2="0" gradientUnits="objectBoundingBox">
          <stop stop-color="{base}"/><stop offset="1" stop-color="{light}"/>
        </linearGradient>
        <clipPath id="plate"><rect width="{width}" height="{height}" rx="30"/></clipPath>
      </defs>
      <g clip-path="url(#plate)">
        <rect width="{width}" height="{height}" fill="url(#surface)"/>
        {art}
      </g>
      <rect x="0.5" y="0.5" width="{width-1}" height="{height-1}" rx="30"
            fill="none" stroke="{ink}" stroke-opacity=".17"/>
      <path d="M{width-38} {height-27} l8 -8 m-8 0 h8 v8" fill="none"
            stroke="{ink}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      <text x="26" y="{height-24}" font-family="Rubik, sans-serif"
            font-size="30" font-weight="600" fill="{caption}">{escape(title)}</text>
      {ring}
    </svg>'''
    loader = GdkPixbuf.PixbufLoader.new_with_type('svg')
    loader.write(svg.encode())
    loader.close()
    return loader.get_pixbuf()


def raised_face(texture, pose):
    """Project the card plane into its original footprint, including its lower edge."""
    from PIL import Image
    width, height = texture.size
    x, y, lift = pose
    cx, cy = width / 2, height / 2
    # Inverse pinhole projection. The side nearest the pointer appears taller.
    g, h = 0.067 * x / cx, 0.035 * y / cy
    scale = 1 - 0.025 * lift - 0.063 * abs(x) - 0.034 * abs(y)
    ox, oy = cx, cy - 2 * lift
    k = 1 - g * ox - h * oy
    coefficients = ((1 / scale + cx*g)/k, cx*h/k, cx - ox/(scale*k),
                    cy*g/k, (1 / scale + cy*h)/k, cy - oy/(scale*k), g/k, h/k)
    plane = texture.transform(texture.size, Image.Transform.PERSPECTIVE, coefficients,
                              resample=Image.Resampling.BILINEAR)
    base = Image.new('RGBA', plane.size)
    depth = round(4 * lift)
    if depth:
        base.paste((52, 68, 48, 255), (0, depth, width, height + depth), plane.getchannel('A'))
    base.alpha_composite(plane)
    return base


class SettingsCard(Gtk.Button):
    def __init__(self, page, title, width, height, navigate):
        super().__init__()
        self.get_style_context().add_class('settings-tile')
        self.get_accessible().set_name(title)
        self.normal = plate_image(page, title, width, height, False)
        self.ring = plate_image(page, title, width, height, True)
        self.image = Gtk.Image.new_from_pixbuf(self.normal)
        self.add(self.image)
        self.texture = None
        self.pose = self.target = (0., 0., 0.)
        self.tick = 0
        self.steady = os.environ.get('AROUNDOS_REDUCE_MOTION', '').lower() in ('1', 'true', 'yes')
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.ENTER_NOTIFY_MASK |
                        Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect('motion-notify-event', self.track)
        self.connect('enter-notify-event', self.track)
        self.connect('leave-notify-event', lambda *_: self.aim((0., 0., 0.)))
        self.connect('state-flags-changed', self.state_changed)
        self.connect('unmap', self.reset)
        self.connect('clicked', lambda _: navigate(page))

    def track(self, _, event):
        device = event.get_source_device()
        if device and device.get_source() == Gdk.InputSource.TOUCHSCREEN:
            return False
        if not self.steady:
            x, y = self.get_pointer()
            nx = max(-1., min(1., 2*x/self.get_allocated_width()-1))
            ny = max(-1., min(1., 2*y/self.get_allocated_height()-1))
            self.aim((nx * 0.55, ny * 0.55, 0.8))
        return False

    def aim(self, target):
        self.target = target
        if not self.tick and self.pose != target:
            self.last = None
            self.tick = self.add_tick_callback(self.advance)
        return False

    def advance(self, _, clock):
        now = clock.get_frame_time()
        dt = 16000 if self.last is None else now - self.last
        self.last = now
        weight = math.exp(-dt/48000)
        self.pose = tuple(t + (p-t)*weight for p,t in zip(self.pose,self.target))
        if max(abs(p-t) for p,t in zip(self.pose,self.target)) < 0.009:
            self.pose = self.target
            self.tick = 0
        self.render()
        return bool(self.tick)

    def render(self):
        if self.pose == (0., 0., 0.):
            flags = Gtk.StateFlags.PRELIGHT | Gtk.StateFlags.FOCUSED | Gtk.StateFlags.ACTIVE
            self.image.set_from_pixbuf(self.ring if self.get_state_flags() & flags else self.normal)
            return
        if self.texture is None:
            from PIL import Image
            size = self.ring.get_width(), self.ring.get_height()
            self.texture = Image.frombytes('RGBA', size, self.ring.get_pixels(),
                                           'raw', 'RGBA', self.ring.get_rowstride())
        frame = raised_face(self.texture, self.pose)
        pixels = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(frame.tobytes()), GdkPixbuf.Colorspace.RGB,
                                                 True, 8, frame.width, frame.height, frame.width * 4)
        self.image.set_from_pixbuf(pixels)

    def state_changed(self, *_):
        if not self.pose[2]:
            self.render()

    def reset(self, *_):
        if self.tick:
            self.remove_tick_callback(self.tick)
            self.tick = 0
        self.pose = self.target = (0., 0., 0.)
        self.render()


def settings_tile(page, title, width, height, navigate):
    return SettingsCard(page, title, width, height, navigate)
