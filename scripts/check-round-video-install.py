#!/usr/bin/env python3
"""Isolated registration checks; run on the Pi with playback dependencies installed."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile

with tempfile.TemporaryDirectory(prefix='video-install-check-') as folder:
    home = Path(folder)
    os.environ['XDG_DATA_HOME'] = str(home/'.local/share')
    os.environ['XDG_CONFIG_HOME'] = str(home/'.config')
    spec = importlib.util.spec_from_file_location('video_install', str(Path(__file__).with_name('install-round-videos.py')))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.HOME = home; module.STATE = home/'.local/state/aroundos-round'
    config = home/'.config/mimeapps.list'; config.parent.mkdir(parents=True)
    config.write_text('[Default Applications]\nimage/png=aroundos-photos.desktop;\n')
    module.install()
    text = config.read_text()
    assert 'image/png=aroundos-photos.desktop;' in text
    assert 'video/mp4=aroundos-videos.desktop;' in text
    assert 'video/x-matroska=aroundos-videos.desktop;' in text
    backups = list(module.STATE.glob('before-videos-*'))
    assert json.loads((backups[0]/'manifest.json').read_text())[str(module.ENTRY)] is False
    module.install()
    assert len(list(module.STATE.glob('before-videos-*'))) == 2
    assert (home/module.ENTRY).read_text().count('[Desktop Entry]') == 1
    print('6 isolated installer checks passed')
