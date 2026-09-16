#!/usr/bin/env python3
"""Regenerate shared metadata/navigation, responsive hints and asset versions.

No prose, artwork title, URL path, llms.txt or original image is rewritten.
Run before tests; --check runs the same transformation and rejects drift.
"""
from __future__ import annotations
import argparse, hashlib, html, json, re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from bs4 import BeautifulSoup
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://5219rayhsu.github.io'
PROFILE = {'alumniOf', 'memberOf', 'award', 'disambiguatingDescription'}
JSONLD = re.compile(r'(<script\b[^>]*type="application/ld\+json"[^>]*>)(.*?)(</script>)', re.S)

def framed_sizes(ratio: float) -> str:
    # Keep HTML sizes portable: WebKit may fall back to 100vw for nested
    # min/max/typed arithmetic even when the same expression is valid CSS.
    # Height-limited frames use vh; remaining slots conservatively approximate
    # the existing 760px two-column breakpoint and 1120px content container.
    height_slot = f"{56 * ratio:.4g}vh"
    return (f"(min-width: 1200px) and (max-height: 1000px) {height_slot}, "
            "(min-width: 1200px) 480px, "
            f"(min-width: 760px) and (max-height: 600px) {height_slot}, "
            "(min-width: 760px) calc(50vw - 4rem), "
            f"(min-aspect-ratio: 5/9) {height_slot}, "
            "calc(100vw - 3.75rem)")

def normalize_link(match):
    prefix, href, end = match.groups()
    u = urlsplit(html.unescape(href))
    if u.netloc and u.netloc != urlsplit(BASE).netloc:
        return match[0]
    if u.scheme not in ('', 'http', 'https') or not u.path.endswith('index.html'):
        return match[0]
    path = u.path[:-10] or './'
    return prefix + html.escape(urlunsplit(u._replace(path=path)), quote=True) + end

def thumbnail_paths():
    for source in sorted((ROOT / 'assets/img/medicine').glob('medicine-tarot-*-800.webp')):
        yield source, source.with_name(source.name.replace('-800.webp', '-320w.webp'))

def sync(check: bool = False) -> list[str]:
    changes = []
    def put(path, text):
        if path.read_text() != text:
            changes.append(path.relative_to(ROOT).as_posix())
            if not check:
                path.write_text(text)
    people = json.loads((ROOT / 'site-data/person.json').read_text())
    nav = json.loads((ROOT / 'site-data/navigation.json').read_text())
    versions = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()[:12]
                for name in ('assets/css/site.css', 'assets/js/main.js')}
    for original, thumb in thumbnail_paths():
        if not thumb.exists():
            changes.append(thumb.relative_to(ROOT).as_posix())
            if not check:
                with Image.open(original) as im:
                    h = round(im.height * 320 / im.width)
                    im.convert('RGB').resize((320, h), Image.Resampling.LANCZOS).save(thumb, 'WEBP', quality=88, method=6)
    for path in sorted(ROOT.rglob('*.html')):
        if any(part.startswith('.') for part in path.relative_to(ROOT).parts):
            continue
        text = path.read_text()
        soup = BeautifulSoup(text, 'html.parser')
        canonical = soup.select_one('link[rel="canonical"]')
        lang = soup.html.get('lang') if soup.html else None
        is_content = path.name == 'index.html' and canonical is not None
        if is_content:
            def ld(match):
                obj = json.loads(match[2])
                def visit(node):
                    if isinstance(node, dict):
                        if node.get('@type') == 'Person' and node.get('@id') == BASE + '/#person':
                            # Existing profile pages retain richer fields; other pages get only shared core facts.
                            rich = any(key in node for key in ('alumniOf', 'award', 'memberOf'))
                            data = people[lang]
                            node.pop('hasCredential', None)
                            for key, value in data.items():
                                if rich or key not in PROFILE:
                                    node[key] = value
                        if node.get('@type') == 'VisualArtwork' and node.get('dateCreated') == '2024–2025':
                            del node['dateCreated']  # Do not fabricate a representative date.
                        for value in list(node.values()):
                            visit(value)
                    elif isinstance(node, list):
                        for value in node:
                            visit(value)
                visit(obj)
                return match[1] + '\n' + json.dumps(obj, ensure_ascii=False, indent=2) + '\n  ' + match[3]
            text = JSONLD.sub(ld, text)
            canonical_path = urlsplit(canonical['href']).path
            prefix = '' if lang == 'zh-Hant' else '/' + lang
            section = canonical_path[len(prefix):].strip('/').split('/')[0]
            links = []
            for item in nav[lang]:
                active = ' class="is-active" aria-current="page"' if section == item['path'] else ''
                links.append(f'        <a href="{prefix}/{item["path"]}/"{active}>{html.escape(item["label"])}</a>')
            text = re.sub(r'(<nav class="nav__links"[^>]*>).*?(</nav>)',
                          lambda m: m[1] + '\n' + '\n'.join(links) + '\n      ' + m[2], text, flags=re.S)
            if 'hero--framed' in text:
                image = soup.select_one('.hero__frame img')
                hint = framed_sizes(int(image['width']) / int(image['height']))
                # The first preloaded image and first picture are the framed hero.
                text = re.sub(r'imagesizes="[^"]*"', 'imagesizes="' + hint + '"', text, count=1)
                text = re.sub(r'(<source\b[^>]*\bsizes=")[^"]*(")', lambda m:m[1]+hint+m[2], text, count=1)
            def add_thumb(m):
                content = m[2]
                if 'medicine-tarot-' not in content or '-320w.webp' in content:
                    return m[0]
                source = re.search(r'([^,\s]+-800\.webp)\s+\d+w', content)
                if not source:
                    return m[0]
                thumb = source[1].replace('-800.webp', '-320w.webp')
                return m[1] + thumb + ' 320w, ' + content + m[3]
            text = re.sub(r'(\bsrcset=")([^"]*)(")', add_thumb, text)
        text = re.sub(r'(<a\b[^>]*\bhref=")([^"]*)(")', normalize_link, text)
        for asset, version in versions.items():
            text = re.sub(re.escape(asset) + r'(?:\?v=[^"\s<>]+)?(?=")', asset + '?v=' + version, text)
        put(path, text)
    return changes

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    changes = sync(args.check)
    print(json.dumps({'changed_or_stale': changes}, ensure_ascii=False, indent=2))
    if args.check and changes:
        raise SystemExit('Generated files are stale. Run python tools/sync_site.py and commit the result.')
