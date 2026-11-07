"""One-shot artwork for the mint terminal prompt and pearlescent crescent."""

import math

from PIL import Image, ImageDraw, ImageFilter


def _ease(t, start, end):
    x = min(1.0, max(0.0, (t - start) / (end - start)))
    return x * x * (3 - 2 * x)


def _cursor(strip, width):
    # Preserve the original rounded, bevelled ends of the underline as it types.
    cap = 19
    height = strip.height
    cursor = Image.new("RGBA", (width, height))
    cursor.paste(strip.crop((0, 0, cap, height)), (0, 0))
    middle = strip.crop((cap, 0, strip.width - cap, height))
    cursor.paste(middle.resize((width - 2 * cap, height), Image.Resampling.LANCZOS), (cap, 0))
    cursor.paste(strip.crop((strip.width - cap, 0, strip.width, height)), (width - cap, 0))
    return cursor


def _terminal(original, t):
    frame = original.copy()
    # This rectangle isolates the cursor from the chevron in the 256px cutout.
    box = (115, 156, 255, 203)
    strip = original.crop(box)
    frame.paste((0, 0, 0, 0), box)

    # The prompt types two stops. Each appears on its own keystroke, then
    # the cursor returns in one sweep as the entry clears.
    compact = _ease(t, 0, 0.23) * (1 - _ease(t, 0.74, 1))
    clear = 1 - _ease(t, 0.72, 0.95)
    typed = [_ease(t, 0.245, 0.36) * clear, _ease(t, 0.43, 0.545) * clear]
    width = round(strip.width - 77 * compact)
    cursor = _cursor(strip, width)
    # Reuse the glass of the cursor itself for both periods.
    dot = _cursor(strip, 44).resize((24, 27), Image.Resampling.LANCZOS)
    for index, visibility in enumerate(typed):
        if visibility:
            glyph = dot.copy()
            glyph.putalpha(dot.getchannel("A").point(lambda a: round(a * visibility)))
            frame.alpha_composite(glyph, (122 + 37 * index, 172))
    frame.alpha_composite(cursor, (box[0] + round(37 * sum(typed)), box[1]))
    return frame


def _star(frame, x, y, r, tint, brightness):
    # Render four tapered rays with a pearl core. A small halo ties their
    # edges to the moon's existing soft, iridescent highlights.
    if brightness <= 0:
        return
    side = math.ceil(r * 4) + 1
    c = side // 2
    radius = r * (0.65 + 0.35 * brightness)
    shape = Image.new("L", (side, side))
    ImageDraw.Draw(shape).polygon([
        (c, c - radius), (c + radius * 0.22, c - radius * 0.24),
        (c + radius * 0.8, c), (c + radius * 0.22, c + radius * 0.24),
        (c, c + radius), (c - radius * 0.22, c + radius * 0.24),
        (c - radius * 0.8, c), (c - radius * 0.22, c - radius * 0.24),
    ], fill=255)
    halo = Image.new("RGBA", shape.size, tint)
    halo.putalpha(shape.filter(ImageFilter.GaussianBlur(radius / 3)).point(lambda a: round(a * brightness * 0.50)))
    light = Image.new("RGBA", shape.size, tint)
    light.putalpha(shape.point(lambda a: round(a * brightness)))
    halo.alpha_composite(light)
    frame.alpha_composite(halo, (x - c, y - c))


def _sleep(original, t):
    frame = original.copy()
    # The larger star catches first, then two softer lights echo across
    # the dark bowl of the crescent. The moon stays perfectly still.
    stars = (
        (167, 79, 20, (230, 225, 255), 0.00, 0.80),
        (208, 119, 14, (255, 234, 212), 0.16, 1.00),
        (215, 53, 8, (183, 211, 255), 0.32, 0.94),
    )
    for x, y, radius, tint, start, end in stars:
        phase = min(1.0, max(0.0, (t - start) / (end - start)))
        _star(frame, x, y, radius, tint, math.sin(math.pi * phase) ** 2)
    return frame


def render(name, original, t):
    """Render the original 256px cutout at normalized time t."""
    if t <= 0 or t >= 1:
        return original.copy()
    renderer = {"terminal": _terminal, "sleep": _sleep}[name]
    if original.size == (256, 256):
        return renderer(original, t)
    art = original.resize((256, 256), Image.Resampling.LANCZOS)
    return renderer(art, t).resize(original.size, Image.Resampling.LANCZOS)
