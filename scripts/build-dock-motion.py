#!/usr/bin/env python3
"""Bake the home-dock one-shots. Only the authoring Mac needs Pillow."""
from pathlib import Path

from PIL import Image

from dock_motion import editor, globe_gear, launch_files, terminal_sleep


DOCK = Path(__file__).resolve().parents[1] / 'src/round-desktop/dock-icons'
# Samples at 30 fps, including both original-art endpoints.
SHOTS = {
    'launchpad': (launch_files, 34),
    'files': (launch_files, 41),
    'editor': (editor, 44),
    'terminal': (terminal_sleep, 34),
    'browser': (globe_gear, 49),
    'settings': (globe_gear, 31),
    'sleep': (terminal_sleep, 47),
}
TILE = 112  # Largest dock presentation is 84 px.


def bake(name, renderer, count):
    with Image.open(DOCK / 'cutouts' / f'{name}.png') as source:
        original = source.convert('RGBA')
    strip = Image.new('RGBA', (count * TILE, TILE))
    for i in range(count):
        frame = renderer.render(name, original, i / (count - 1))
        if frame.mode != 'RGBA' or frame.size != original.size:
            raise ValueError(f'{name} frame {i} has an unexpected format')
        if i in (0, count - 1) and frame.tobytes() != original.tobytes():
            raise ValueError(f'{name} must land on its exact original cutout')
        strip.paste(frame.resize((TILE, TILE), Image.Resampling.LANCZOS), (TILE * i, 0))
    path = DOCK / 'motion' / f'{name}.png'
    path.parent.mkdir(exist_ok=True)
    temporary = path.with_suffix('.tmp')
    strip.save(temporary, format='PNG', optimize=True)
    temporary.replace(path)
    print(f'{name}: {count} frames, {path.stat().st_size // 1024} KiB', flush=True)


if __name__ == '__main__':
    for name, (renderer, count) in SHOTS.items():
        bake(name, renderer, count)
