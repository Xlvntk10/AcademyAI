"""Validate generated shell references and icon dimensions without a browser."""
import json
import re
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def run():
    dist = ROOT / 'frontend' / 'dist'
    manifest = json.loads((dist/'manifest.webmanifest').read_text(encoding='utf8'))
    worker = (dist/'sw.js').read_text(encoding='utf8')
    html = (dist/'index.html').read_text(encoding='utf8')
    precache = json.loads(re.search(r'const PRECACHE = (\[.*?\]);', worker).group(1))
    assert '__VERSION__' not in worker and '__PRECACHE__' not in worker
    assert manifest['scope'] == '/' and manifest['start_url'].startswith('/#')
    assert manifest['display'] == 'standalone'
    for url in precache:
        assert url.startswith('/') and not url.startswith('/api')
        assert (dist/url.lstrip('/')).is_file(), url
    for url in re.findall(r'(?:src|href)="(/[^\"]+)"', html):
        assert url in precache, url
    for icon in manifest['icons']:
        path = dist/icon['src'].lstrip('/')
        assert path.is_file()
        if icon['type'] == 'image/png':
            with Image.open(path) as image:
                assert f'{image.width}x{image.height}' == icon['sizes']
    with Image.open(dist/'icons/apple-touch-icon.png') as icon:
        assert icon.size == (180,180)
    print(json.dumps(dict(precache_files=len(precache), icons=len(manifest['icons']),
                         html_assets_present=True, apple_icon='180x180'), indent=2))


if __name__ == '__main__':
    run()
