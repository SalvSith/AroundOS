#!/usr/bin/env python3
"""Capture the physical circular viewport as a transparent PNG."""
import argparse
import datetime
import io
import math
import os
from pathlib import Path
import subprocess
import tempfile


def circular_image(png):
    import cairo
    source = cairo.ImageSurface.create_from_png(io.BytesIO(png))
    width, height = source.get_width(), source.get_height()
    if width != height:
        raise ValueError(f'Expected a square round display, got {width} × {height}')
    result = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    context = cairo.Context(result)
    context.arc(width / 2, height / 2, width / 2, 0, math.tau)
    context.clip()
    context.set_source_surface(source)
    context.paint()
    return result


def pictures_directory():
    try:
        value = subprocess.check_output(['xdg-user-dir', 'PICTURES'], text=True).strip()
        if value and Path(value).is_absolute():
            return Path(value)
    except (OSError, subprocess.CalledProcessError):
        pass
    return Path.home() / 'Pictures'


def capture(destination=None, output='HDMI-A-1'):
    png = subprocess.check_output(['grim', '-o', output, '-t', 'png', '-'])
    result = circular_image(png)
    if destination is None:
        stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S-%f')
        destination = pictures_directory() / 'Screenshots' / f'Screenshot_{stamp}.png'
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Never expose a partially written screenshot to Files/Photos.
    fd, temporary = tempfile.mkstemp(prefix='.screenshot-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            result.write_to_png(stream)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='HDMI-A-1')
    parser.add_argument('--save', type=Path, help='Explicit PNG destination')
    args = parser.parse_args()
    try:
        print(capture(args.save, args.output))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Screenshot failed: {error}\n')
