"""Authoring poses for the original 256 px home dock rocket and folder."""

import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter


def _ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _pose(t, keys):
    for (start, a), (end, b) in zip(keys, keys[1:]):
        if t <= end:
            return a + (b - a) * _ease((t - start) / (end - start))
    return keys[-1][1]


def _rocket(original, t):
    # Anticipate by contracting the exhaust, then lift along the window/nozzle axis.
    lift = _pose(t, [(0, 0), (.12, -.9), (.46, 8), (.60, 8.2), (.96, 0)])
    thrust = _pose(t, [(0, 0), (.12, -.23), (.31, .15), (.41, .025),
                        (.52, .20), (.62, .03), (.70, .12), (.82, -.08), (1, 0)])
    # A pulse of incandescent yellow travels through the painted flame. Keep
    # its contour and alpha exact so there is no glow around the whole icon.
    pulse = _ease((t - .08) / .16) * _ease((.90 - t) / .18)
    center = 31 + 10 * math.sin((t - .27) * 5 * math.pi)
    hot = Image.new('L', original.size)
    pixels = hot.load()
    for y in range(181, 250):
        for x in range(26, 96):
            along = -.60 * (x - 76) + .80 * (y - 192)
            across = .80 * (x - 76) + .60 * (y - 192)
            beam = math.exp(-((along - center) / 23) ** 2 - (across / 11) ** 2)
            pixels[x, y] = round(170 * pulse * beam * _ease(along / 9))
    painted = Image.composite(Image.new('RGBA', original.size, '#ffface'), original, hot)
    painted.putalpha(original.getchannel('A'))

    def sample(x, y):
        x -= .60 * lift
        y += .80 * lift
        # The metallic lip is the zero-displacement anchor. Only the original
        # painted exhaust tapers and bends. Both side fins stay rigid.
        along = -.60 * (x - 76) + .80 * (y - 192)
        across = .80 * (x - 76) + .60 * (y - 192)
        reach = max(0.0, along) * _ease((39 - abs(across)) / 13)
        stretch = reach * thrust / (1 + thrust)
        curl = (reach / 70) ** 2 * math.sin(4 * math.pi * t) * 1.9
        return x + .60 * stretch - .80 * curl, y - .80 * stretch - .60 * curl

    # Pillow's quad mesh inverse-maps once, preserving the original antialiased
    # paint and continuous contact between the flame and the nozzle.
    mesh = []
    for y in range(0, 256, 8):
        for x in range(0, 256, 8):
            corners = ((x, y), (x, y + 8), (x + 8, y + 8), (x + 8, y))
            mesh.append(((x, y, x + 8, y + 8),
                         tuple(v for corner in corners for v in sample(*corner))))
    return painted.transform(original.size, Image.Transform.MESH, mesh, Image.Resampling.BICUBIC)


# Upper edge of the original blue cover. The pixels below this contour are
# the actual front plate, including its bevel, outer alpha and bottom hinge.
_COVER_EDGE = [(6, 112), (8, 105), (10, 99), (13, 95), (16, 92),
               (20, 89), (25, 87.5), (31, 86.5), (224, 86.5),
               (228, 87), (232, 88.2), (236, 90.2), (240, 93.5),
               (243, 97.5), (246, 102), (249, 110), (251, 116)]


def _cover(original):
    mask = Image.new('L', (512, 512))
    outline = _COVER_EDGE + [(256, 256), (0, 256)]
    ImageDraw.Draw(mask).polygon([(round(x * 2), round(y * 2)) for x, y in outline], fill=255)
    front = original.copy()
    front.putalpha(ImageChops.multiply(original.getchannel('A'),
                                       mask.resize(original.size, Image.Resampling.LANCZOS)))
    return front


def _folder_back(original):
    back = Image.new('RGBA', original.size)
    back.paste(original.crop((0, 0, 256, 87)))
    # Continue the original cream divider and blue backing down into the pocket.
    # Their exposed top and side bevels keep the light direction of the still.
    row = original.crop((10, 86, 243, 87))
    inside = row.resize((233, 68))
    shade = Image.new('L', inside.size)
    draw = ImageDraw.Draw(shade)
    for y in range(68):
        draw.line((0, y, 232, y), fill=round(65 * _ease(y / 56)))
    shaded = Image.composite(Image.new('RGBA', inside.size, (16, 52, 87, 255)),
                             inside, shade)
    shaded.putalpha(inside.getchannel('A'))
    back.paste(shaded, (10, 87))
    return back


def _document():
    # Warm ivory picks up the existing divider. The folded corner and two short
    # baselines are drawn large enough to read at the dock's resting size.
    page = Image.new('RGBA', (256, 256))
    draw = ImageDraw.Draw(page)
    draw.rounded_rectangle((82, 100, 183, 211), radius=6, fill='#fbf5e7')
    draw.polygon([(163, 100), (184, 120), (184, 98)], fill=(0, 0, 0, 0))
    draw.polygon([(163, 101), (182, 120), (164, 120)], fill='#c2cbd3')
    draw.line((165, 121, 180, 121), fill='#e1e4df', width=2)
    draw.rounded_rectangle((96, 118, 144, 123), radius=2, fill='#758ea2')
    draw.rounded_rectangle((96, 133, 165, 136), radius=1, fill='#a9b7bc')
    draw.rounded_rectangle((96, 145, 153, 148), radius=1, fill='#a9b7bc')
    return page


def _folder(original, t):
    opening = _pose(t, [(0, 0), (.28, .94), (.43, 1), (.64, 1),
                         (.76, .89), (.98, 0)])
    reveal = _pose(t, [(0, 0), (.14, 0), (.47, 1), (.55, .96),
                        (.63, .96), (.89, 0), (1, 0)])
    back = _folder_back(original)
    page = _document().rotate(4.5 * reveal, Image.Resampling.BICUBIC, center=(135, 198),
                              translate=(3 * reveal, -65 * reveal))
    page_shadow = ImageChops.offset(page.getchannel('A'), 2, 3).filter(ImageFilter.GaussianBlur(3))
    shadow = Image.new('RGBA', back.size, (4, 35, 69))
    shadow.putalpha(ImageChops.multiply(back.getchannel('A'), page_shadow.point(lambda v: v // 4)))
    back.alpha_composite(shadow)
    back.alpha_composite(page)

    # Project the front onto a shorter plane around its fixed bottom edge.
    # Slight widening toward the viewer distinguishes opening from translation.
    sy, sx = 1 - .235 * opening, 1 + .020 * opening
    inverse = (1 / sx, 0, 128 * (1 - 1 / sx), 0, 1 / sy, 222 * (1 - 1 / sy))
    front = _cover(original).transform(original.size, Image.Transform.AFFINE,
                                       inverse, Image.Resampling.BICUBIC)
    back.alpha_composite(front)
    # At rest use the exact original, including fractional edge coverage that
    # cannot be separated into two independent plates from a flattened image.
    mix = min(_ease(t / .11), _ease((1 - t) / .11))
    return Image.blend(original, back, mix) if mix < 1 else back


def render(name, original, t):
    """One interaction cycle, with matching original-art endpoints."""
    if not 0 < t < 1:
        return original.copy()
    if original.size != (256, 256):
        raise ValueError('Launchpad and Files are authored for the original 256 px cutouts.')
    if name == 'launchpad':
        return _rocket(original, t)
    if name == 'files':
        return _folder(original, t)
    raise ValueError(f'Unknown icon: {name}')
