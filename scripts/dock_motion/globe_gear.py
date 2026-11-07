"""Author Browser and Settings poses from their transparent home dock cutouts."""

import math
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter


def _clamp(value):
    return max(0., min(1., value))


def _ease(t):
    return t * t * (3 - 2 * t)


def _gear(original, phase):
    # Eight teeth. Interpolate equivalent tooth positions, so the overhead
    # light remains at eleven o'clock as the teeth advance to the next stop.
    angle = -45 * phase
    w, h = original.size
    center = (w * .5, h * .502)
    metal = original.convert('RGBa')
    outgoing = metal.rotate(angle, Image.Resampling.BICUBIC, center=center)
    incoming = metal.rotate(angle + 45, Image.Resampling.BICUBIC, center=center)
    teeth = Image.blend(outgoing, incoming, _ease(phase)).convert('RGBA')

    hub = Image.new('L', original.size)
    cx, cy = center
    ImageDraw.Draw(hub).ellipse((cx - w * .244, cy - h * .244,
                                cx + w * .244, cy + h * .244), fill=255)
    return Image.composite(original, teeth, hub.filter(ImageFilter.GaussianBlur(w / 256)))


# The cutout shows Europe and Africa. These illustrated coastlines complete
# the far side of the glass sphere. All points are (longitude, latitude).
_FAR_COASTS = (
    # North America, Hudson Bay and the Gulf of Mexico
    [(-168,66),(-164,70),(-153,71),(-144,69),(-130,70),(-123,74),(-111,75),
     (-101,72),(-96,72),(-91,69),(-83,68),(-82,65),(-88,63),(-94,60),
     (-92,57),(-85,55),(-82,53),(-79,55),(-79,59),(-76,61),(-77,64),
     (-72,63),(-68,60),(-64,61),(-62,57),(-58,54),(-56,52),(-59,50),
     (-66,49),(-62,46),(-66,44),(-69,45),(-70,42),(-74,40),(-76,36),
     (-79,33),(-81,31),(-80,26),(-81.5,25),(-83,29),(-88,30),(-90,29),
     (-94,30),(-97,27),(-98,23),(-96,19),(-92,18),(-90,21),(-87,21),
     (-87,17),(-88,16),(-84,16),(-83,14),(-83,11),(-79,9),(-77,8),
     (-79,7),(-82,8),(-85,10),(-87,13),(-90,14),(-94,16),(-97,15),
     (-103,18),(-106,22),(-109,23),(-112,29),(-114,31),(-113,27),
     (-110,24),(-110,22),(-114,25),(-116,29),(-117,32),(-121,35),
     (-124,41),(-124,46),(-123,49),(-128,51),(-131,55),(-136,58),
     (-142,60),(-149,61),(-152,59),(-158,56),(-165,54),(-159,58),
     (-162,60),(-166,61),(-164,63),(-168,65)],
    # Greenland, Arctic islands and Caribbean
    [(-73,77),(-66,81),(-45,83),(-22,82),(-17,76),(-22,70),(-30,68),
     (-39,63),(-44,60),(-48,61),(-53,67),(-52,71),(-58,75),(-65,76)],
    [(-87,73),(-80,75),(-74,72),(-68,71),(-64,67),(-66,63),(-69,62),(-76,66),(-73,69),(-83,70)],
    [(-119,76),(-110,79),(-96,76),(-101,72),(-114,72)],
    [(-85,22),(-80,23),(-75,20),(-77,20),(-82,22)],
    [(-74,20),(-70,20),(-68,18),(-72,18)],
    # South America
    [(-81,5),(-77,8),(-73,11),(-70,12),(-66,10),(-62,11),(-60,8),
     (-54,6),(-51,4),(-50,1),(-46,-1),(-40,-3),(-36,-5),(-35,-8),
     (-38,-13),(-39,-18),(-40,-21),(-44,-23),(-48,-25),(-49,-29),
     (-53,-33),(-57,-36),(-57,-39),(-62,-41),(-65,-42),(-66,-47),
     (-69,-50),(-69,-53),(-65,-55),(-69,-55),(-74,-52),(-75,-48),
     (-73,-44),(-74,-41),(-72,-36),(-72,-32),(-70,-27),(-70,-20),
     (-75,-15),(-77,-12),(-80,-7),(-81,-4),(-80,0)],
    # East Asia, Southeast Asia, Japan and the Indonesian archipelago
    [(42,74),(60,76),(85,73),(103,78),(118,74),(142,72),(160,70),
     (174,68),(180,67),(180,63),(174,61),(166,60),(163,58),(161,55),
     (158,51),(155,52),(156,57),(158,60),(151,59),(144,60),(137,56),
     (139,53),(141,51),(139,47),(134,45),(132,42),(130,42),(129,38),
     (129,35),(126,34),(125,38),(122,40),(120,39),(118,39),(119,37),
     (123,37),(120,34),(122,31),(121,28),(117,24),(114,22),(108,21),
     (106,19),(109,15),(109,12),(105,9),(103,10),(101,12),(100,14),
     (99,12),(100,8),(103,4),(104,1),(102,1),(99,6),(98,9),(97,15),
     (94,16),(92,20),(90,22),(87,21),(83,17),(80,14),(78,9),(77,8),
     (75,12),(72,19),(68,23),(59,25),(48,28)],
    [(141,46),(145,44),(143,42),(141,41),(140,38),(137,36),(134,35),
     (131,34),(130,32),(129,33),(131,35),(135,36),(139,39),(140,42)],
    [(95,6),(98,5),(102,1),(106,-5),(105,-6),(100,-3)],
    [(106,-6),(113,-7),(115,-8),(110,-8)],
    [(109,1),(112,3),(117,7),(119,5),(117,1),(117,-3),(114,-4),(111,-3)],
    [(120,19),(122,18),(123,14),(121,13),(120,15)],
    [(125,10),(126,8),(125,6),(122,7)],
    [(131,-1),(136,-2),(139,-2),(142,-3),(146,-6),(150,-7),(153,-10),
     (149,-10),(145,-8),(143,-9),(139,-8),(137,-5),(134,-4)],
    # Australia and New Zealand
    [(113,-22),(115,-21),(117,-20),(119,-20),(122,-18),(123,-16),
     (127,-14),(130,-14),(131,-12),(135,-12),(137,-12),(136,-15),
     (139,-17),(141,-16),(142,-11),(144,-15),(146,-18),(149,-21),
     (151,-23),(153,-27),(153,-30),(151,-34),(148,-37),(145,-39),
     (141,-38),(139,-36),(137,-35),(136,-33),(134,-32),(131,-31),
     (127,-32),(122,-34),(118,-35),(115,-34),(115,-31),(114,-28)],
    [(144,-41),(148,-41),(147,-43.5),(145,-43.5)],
    [(173,-34),(176,-37),(178,-38),(176,-40),(174,-41),(174,-38)],
    [(173,-41),(174,-41),(172,-44),(168,-47),(166,-46),(168,-44)],
)


def _far_side(w, h):
    mask = Image.new('L', (w, h))
    draw = ImageDraw.Draw(mask)
    for coast in _FAR_COASTS:
        draw.polygon([((lon + 180) * w / 360, (90 - lat) * h / 180)
                      for lon, lat in coast], fill=255)
    return mask.filter(ImageFilter.GaussianBlur(.7))


def _coasts_and_water(original):
    # Peel the raised mint coastlines off the cobalt glass, leaving its
    # specular stripe and edge refraction in screen space throughout the turn.
    w, h = original.size
    mask = Image.new('L', original.size)
    values = []
    for i, (r, g, b, a) in enumerate(original.getdata()):
        x = ((i % w + .5) / w - .5) / .458
        y = ((i // w + .5) / h - .497) / .469
        rim = _clamp((.994 - math.hypot(x, y)) / .052)
        green = (_clamp((g - b + 6) / 15) * _clamp((g - 68) / 30)
                 * _clamp((g - r - 5) / 20))
        values.append(round(255 * rim * green))
    mask.putdata(values)
    spill = mask.filter(ImageFilter.MaxFilter(11))
    dry = ImageChops.multiply(ImageChops.invert(spill), original.getchannel('A'))
    rgb = original.convert('RGB')
    weighted = Image.composite(rgb, Image.new('RGB', rgb.size), dry)
    # Extrapolate the nearby water at several radii. The fine blur supplies
    # coastal detail, the broad blur carries color underneath large land masses.
    ocean = Image.new('RGB', original.size, (1, 52, 153))
    for radius in (w / 4, w / 9, w / 22):
        weight = dry.filter(ImageFilter.GaussianBlur(radius))
        color = weighted.filter(ImageFilter.GaussianBlur(radius))
        fill = Image.new('RGB', original.size)
        fill.putdata([tuple(min(255, round(ch * 255 / max(1, k))) for ch in pixel)
                      for pixel, k in zip(color.getdata(), weight.getdata())])
        strength = weight.point(lambda k: round(255 * _ease(_clamp((k - 14) / 76))))
        ocean = Image.composite(fill, ocean, strength)
    water = Image.composite(ocean, rgb, spill.filter(ImageFilter.GaussianBlur(1)))
    # Retain the original upper-left specular reflection in front of the enamel.
    gloss = Image.new('L', original.size)
    gloss.putdata([round(255 * _clamp((p[0] - 12) / 220)
                         * _clamp((.43 - (i % w) / w) / .10)
                         * _clamp((.38 - (i // w) / h) / .12))
                   for i, p in enumerate(original.getdata())])
    return mask, water, gloss


def _geometry(w, h):
    return w * .5, h * .497, w * .458, h * .469


_CAMERA_LAT = math.radians(13)
_CL, _SL = math.cos(_CAMERA_LAT), math.sin(_CAMERA_LAT)
_MERIDIAN = math.radians(8)


def _light(nx, ny, nz):
    return .45 * nz - .33 * nx - .37 * ny + .11 * math.cos(4.5 * nx + 3 * ny)


@lru_cache(maxsize=1)
def _globe_layers(size, original_bytes):
    art = Image.frombytes('RGBA', size, original_bytes)
    mask, water, gloss = _coasts_and_water(art)
    cx, cy, rx, ry = _geometry(*size)
    aw, ah = 1024, 512
    coasts = _far_side(aw, ah).load()
    src_mask = mask.load()
    atlas = bytearray(aw * ah)
    texture = bytearray([128]) * (aw * ah)
    src = art.load()
    for y in range(ah):
        lat = math.pi * (.5 - (y + .5) / ah)
        cl, sl = math.cos(lat), math.sin(lat)
        for x in range(aw):
            lon = ((x + .5) / aw - .5) * math.tau - _MERIDIAN
            nx, nz = cl * math.sin(lon), cl * math.cos(lon)
            depth = _CL * nz + _SL * sl
            value = coasts[x, y]
            if depth > .02:
                sx = int(cx + rx * nx)
                ny = _SL * nz - _CL * sl
                sy = int(cy + ry * ny)
                weight = _ease(_clamp((depth - .32) / .23))
                alpha = src_mask[sx, sy]
                value += (alpha - value) * weight
                if alpha > 160:
                    # Keep the original enamel grain, including its polished
                    # raised edges, independent of the screen-space lighting.
                    diffuse = 55 + 80 * _light(nx, ny, depth)
                    grain = max(-44., min(56., src[sx, sy][0] - diffuse))
                    texture[y * aw + x] = 128 + round(grain * weight)
                if 0 < weight < 1:
                    value = 255 * _ease(_clamp((value - 75) / 105))
            atlas[y * aw + x] = round(value)

    samples = []
    w, h = size
    for y in range(h):
        ny = (cy - y - .5) / ry
        for x in range(w):
            nx = (x + .5 - cx) / rx
            dist2 = nx * nx + ny * ny
            if dist2 >= 1:
                continue
            nz = math.sqrt(1 - dist2)
            lat = math.asin(_clamp_signed(_CL * ny + _SL * nz))
            lon = _MERIDIAN + math.atan2(nx, _CL * nz - _SL * ny)
            v = int(ah * (.5 - lat / math.pi)) % ah
            u = ((lon / math.tau + .5) * aw) % aw
            rim = _ease(_clamp((nz - .04) / .34))
            samples.append((y * w + x, v * aw, u, rim))
    return bytes(atlas), bytes(texture), aw, samples, water, gloss


def _clamp_signed(value):
    return min(1., max(-1., value))


def _globe(original, phase):
    atlas, texture, aw, samples, water, gloss = _globe_layers(original.size, original.tobytes())
    shift = aw * phase
    mask_bytes = bytearray(original.width * original.height)
    grain = bytearray([128]) * len(mask_bytes)
    for i, row, u, rim in samples:
        s = u + shift
        index = int(s)
        j = row + index % aw
        k = row + (index + 1) % aw
        f = s - index
        mask_bytes[i] = round(rim * (atlas[j] + (atlas[k] - atlas[j]) * f))
        grain[i] = round(texture[j] + (texture[k] - texture[j]) * f)
    mask = Image.frombytes('L', original.size, bytes(mask_bytes))
    # Mint enamel has a softly embossed shoreline with light catching its
    # northwest edge. Bake the same material onto the newly visible side.
    w, h = original.size
    cx, cy, rx, ry = _geometry(w, h)
    bevel = mask.filter(ImageFilter.GaussianBlur(w / 220))
    shade = ImageChops.subtract(ImageChops.offset(bevel, -1, -2), ImageChops.offset(bevel, 1, 2),
                                scale=2, offset=128)
    enamel = Image.new('RGB', original.size)
    colors = []
    for i, edge in enumerate(shade.getdata()):
        nx, ny = ((i % w - cx) / rx), ((i // w - cy) / ry)
        nz = math.sqrt(max(0., 1 - nx * nx - ny * ny))
        light = _light(nx, ny, nz)
        relief = (edge - 128) * .95 + grain[i] - 128
        colors.append((round(55 + 80 * light + relief), round(188 + 43 * light + relief * .65),
                       round(166 + 34 * light + relief * .7)))
    enamel.putdata(colors)
    painted = Image.composite(enamel, water, mask)
    painted = Image.composite(original.convert('RGB'), painted, gloss).convert('RGBA')
    painted.putalpha(original.getchannel('A'))
    # Allow the exact hand-painted light and bevel detail to resolve as the
    # sphere eases into and out of its resting pose.
    settle = _ease(_clamp(min(phase, 1 - phase) / .014))
    return Image.blend(original, painted, settle)


def render(name, original, t):
    """Render a single one-shot at the source cutout's native dimensions."""
    if t <= 0 or t >= 1:
        return original.copy()
    phase = _ease(t)
    if name == 'settings':
        return _gear(original, phase)
    if name == 'browser':
        return _globe(original, phase)
    raise ValueError(f'Unknown globe/gear icon {name}')
