"""The original pencil writes a small graphite flourish on its own sheet."""
from functools import lru_cache
import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter


# The graphite tip, yellow facets, silver ferrule and eraser form one piece.
# Trace both edges of the actual painting rather than redrawing the pencil.
_EDGES = [(75.6, 216, 221), (77, 212, 228), (80, 208, 232), (88, 200, 238),
          (94, 193.5, 238.5), (100, 188, 238), (108, 180, 232), (111, 178, 230),
          (114, 175, 228), (125, 164, 217), (133, 156, 208), (186, 103.5, 155),
          (190, 101, 151), (210, 91.5, 130), (217, 88, 116), (224, 84, 102),
          (231.5, 80, 88), (233.7, 80, 84), (234.5, 81, 82)]
_TIP = (81.0, 233.5)
_PATH = [
    ((53, 207), (58, 205), (62, 194), (65, 195)),
    ((65, 195), (69, 196), (59, 210), (65, 210)),
    ((65, 210), (69, 210), (75, 199), (78, 200)),
    ((78, 200), (80, 201), (74, 208), (78, 208)),
    ((78, 208), (86, 208), (94, 201), (104, 200)),
]


def _ease(value):
    v = min(1., max(0., value))
    return v * v * (3 - 2 * v)


@lru_cache(maxsize=1)
def _plates(source):
    original = Image.frombytes('RGBA', (256, 256), source)
    edge = [(left, y) for y, left, right in _EDGES]
    edge += [(right, y) for y, left, right in reversed(_EDGES)]
    mask = Image.new('L', (1024, 1024))
    ImageDraw.Draw(mask).polygon([(round(x * 4), round(y * 4)) for x, y in edge], fill=255)
    mask = mask.resize(original.size, Image.Resampling.LANCZOS)
    pencil = original.copy()
    pencil.putalpha(ImageChops.multiply(mask, original.getchannel('A')))

    # Reconstruct only the patch hidden by the pencil and its shadow. Sample
    # clear paper from the same scanline and preserve the sheet's bevel at right.
    repair = Image.new('RGBA', original.size)
    pixels = original.load()
    restored = repair.load()
    for y in range(256):
        left = max(42, min(164, 252 - y))
        paper_l = pixels[left, y]
        fade = _ease((y - 74) / 77)
        paper_r = tuple(round(a + (b-a)*fade)
                        for a, b in zip(pixels[196, 74], pixels[178, 209]))
        if y > 195:
            paper_r = pixels[175, y]
        for x in range(256):
            f = max(0., min(1., (x - left) / (175 - left)))
            tone = tuple(round(a + (b - a) * f) for a, b in zip(paper_l, paper_r))
            if x >= 215:
                tone = (0, 0, 0, 0)
            elif x >= 207:
                tone = tuple(round(a + (b-a)*fade)
                             for a, b in zip(pixels[x, 74], pixels[x, 185]))
            restored[x, y] = tone
    patch = Image.new('L', original.size)
    draw = ImageDraw.Draw(patch)
    halo = [(209, 74), (230, 70), (246, 78), (248, 107), (230, 140),
            (148, 221), (118, 239), (84, 244), (74, 240), (73, 230),
            (97, 185), (177, 103)]
    draw.polygon(halo, fill=255)
    patch = patch.filter(ImageFilter.GaussianBlur(5))
    # Cover the opaque pencil completely at the upper edge of the repair.
    patch = ImageChops.lighter(patch, mask.filter(ImageFilter.MaxFilter(9)))
    page = Image.composite(repair, original, patch)
    return page, pencil


def _point(curve, u):
    a, b, c, d = curve
    return tuple((1-u)**3*p + 3*(1-u)**2*u*q + 3*(1-u)*u*u*r + u**3*s
                 for p, q, r, s in zip(a, b, c, d))


@lru_cache(maxsize=1)
def _handwriting():
    # Parameterize by distance, keeping the pencil's speed continuous where
    # the curves join. Each rendered point belongs to the same path as the ink.
    points = [_PATH[0][0]]
    lengths = [0.]
    for curve in _PATH:
        for step in range(1, 29):
            point = _point(curve, step / 28)
            lengths.append(lengths[-1] + math.dist(point, points[-1]))
            points.append(point)
    return points, lengths


def _stroke(written):
    points, lengths = _handwriting()
    distance = written * lengths[-1]
    trail = [points[0]]
    for i in range(1, len(points)):
        if lengths[i] > distance:
            f = (distance - lengths[i-1]) / (lengths[i] - lengths[i-1])
            trail.append(tuple(a + (b - a) * f for a, b in zip(points[i-1], points[i])))
            break
        trail.append(points[i])
    return trail


def render(name, original, t):
    """One 30 fps writing gesture. Both endpoints use the original bitmap."""
    if not 0 < t < 1:
        return original.copy()
    if name != 'editor' or original.size != (256, 256):
        raise ValueError('Editor requires the original 256 px editor cutout.')
    page, pencil = _plates(original.tobytes())
    composed = page.copy()
    arriving = _ease(t / .31)
    written = _ease((t - .31) / .37)
    returning = _ease((t - .73) / .25)
    height = (9 * math.sin(math.pi * arriving) +
              7 * math.sin(math.pi * returning))
    trail = _stroke(written)
    px, py = trail[-1]
    dx = (px - _TIP[0]) * arriving * (1 - returning)
    dy = (py - _TIP[1]) * arriving * (1 - returning) - height
    angle = (4.6 + written * 1.6) * arriving * (1 - returning)
    tool = pencil.rotate(angle, Image.Resampling.BICUBIC, center=_TIP, translate=(dx, dy))

    if written > 0:
        ink = Image.new('L', (1024, 1024))
        draw = ImageDraw.Draw(ink)
        opacity = round(222 * (1 - _ease((t - .79) / .18)))
        line = [(round(x * 4), round(y * 4)) for x, y in trail]
        for i in range(1, len(line)):
            pressure = min(1., (i + 4) / 12, (len(_handwriting()[0]) - i + 8) / 24)
            width = round(4 * (2.8 + 2.2*pressure))
            draw.line((line[i-1], line[i]), fill=opacity, width=width)
            x, y = line[i]
            r = width / 2
            draw.ellipse((x-r, y-r, x+r, y+r), fill=opacity)
        composed.paste((75, 77, 86), (0, 0, 256, 256),
                       ink.resize(original.size, Image.Resampling.LANCZOS))

    shadow = ImageChops.offset(tool.getchannel('A'), 3, round(4 + height / 2))
    shadow = shadow.filter(ImageFilter.GaussianBlur(4 + height / 4))
    shadow = ImageChops.multiply(shadow, page.getchannel('A')).point(lambda v: v * .27)
    composed.paste((86, 64, 45), (0, 0, 256, 256), shadow)
    composed.alpha_composite(tool)
    # Match the original painted contact shadow precisely at both handoffs.
    blend = min(_ease(t / .07), _ease((1 - t) / .07))
    return Image.blend(original, composed, blend) if blend < 1 else composed
