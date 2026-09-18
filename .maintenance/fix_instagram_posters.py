#!/usr/bin/env python3
"""Preserve artwork content; replace five public Instagram previews, not videos.

Instagram's own embed was measured stretching 9:16 source posters to 4:5.
Its cross-origin inner styles cannot be repaired by the host stylesheet. These
local, original-ratio posters link to the exact existing Instagram posts.
"""
from __future__ import annotations
import hashlib, html, io, json, re
from pathlib import Path
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from PIL import Image, ImageOps
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.test-results'; OUT.mkdir(exist_ok=True)
POSTER_DIR = ROOT / 'assets/img/instagram'; POSTER_DIR.mkdir(exist_ok=True)
BASELINE = ROOT / 'site-data/content-baseline.json'
baseline = json.loads(BASELINE.read_text())
pattern = re.compile(r'<iframe\b[^>]*\bsrc="https://(?:www\.)?instagram\.com/[^\"]+"[^>]*>\s*</iframe>|<blockquote\b[^>]*class="instagram-media"[^>]*>.*?</blockquote>(?:\s*<p class="video-embed__fallback">.*?</p>)?', re.S)
labels = {'zh-Hant': ('在 Instagram 觀看 ↗', '在新分頁觀看 Instagram 影片：'), 'en': ('Watch on Instagram ↗', 'Watch Instagram video in a new tab: '), 'ja': ('Instagram で見る ↗', 'Instagram の動画を新しいタブで見る：')}

def info(markup):
    node = BeautifulSoup(markup, 'html.parser').find(['iframe', 'blockquote'])
    url = node.get('src') or node['data-instgrm-permalink']
    match = re.fullmatch(r'/(p|reel|reels|tv)/([A-Za-z0-9_-]+)/(?:embed(?:/captioned)?/?)?', urlsplit(url).path)
    assert match, f'Unexpected Instagram URL: {url}'
    return match[2], f'https://www.instagram.com/{match[1]}/{match[2]}/', node.get('title') or node.get('aria-label')

pages = []
posts = {}
for path in sorted(ROOT.rglob('*.html')):
    if any(part.startswith('.') for part in path.relative_to(ROOT).parts): continue
    text = path.read_text()
    if not pattern.search(text): continue
    pages.append((path, text))
    for match in pattern.finditer(text):
        key, url, title = info(match[0]); posts[key] = {'permalink': url}
assert len(pages) == 6 and len(posts) == 5, 'Unexpected migration scope; review before changing content'
assert set(posts) == {'DLMKGvHTr0I', 'DLfFQBQTV2W', 'DWI0t9Ok3gE', 'DWDtVxWkzjE', 'DWBN2J9k2-P'}

# Read the public embed to obtain its actual native image. Do not screenshot,
# rescale a distorted image, use an avatar, or depend on an expiring CDN URL.
with sync_playwright() as pw:
    browser = pw.chromium.launch()
    context = browser.new_context(viewport={'width': 720, 'height': 1280})
    page = context.new_page()
    for key, record in posts.items():
        page.goto(record['permalink'] + 'embed/?cr=1&v=14&wp=720', wait_until='domcontentloaded', timeout=30000)
        page.wait_for_function('()=>[...document.images].some(i=>i.complete&&i.naturalWidth>=300&&i.naturalHeight/i.naturalWidth>1.5)', timeout=20000)
        candidates = page.locator('img').evaluate_all('els=>els.filter(i=>i.naturalWidth>=300&&i.naturalHeight/i.naturalWidth>1.5).map(i=>({src:i.currentSrc||i.src,w:i.naturalWidth,h:i.naturalHeight})).sort((a,b)=>b.w*b.h-a.w*a.h)')
        assert candidates, f'No real portrait poster found for {key}'
        chosen = candidates[0]
        response = context.request.get(chosen['src'], timeout=20000)
        assert response.ok, f'Poster download failed for {key}'
        with Image.open(io.BytesIO(response.body())) as original:
            image = ImageOps.exif_transpose(original).convert('RGB')
            width, height = image.size
            assert width >= 300 and 1.5 < height / width < 2.1, f'Unexpected poster shape for {key}: {image.size}'
            target = POSTER_DIR / f'{key}.jpg'
            image.save(target, 'JPEG', quality=92, optimize=True)
        record.update({'image': target.relative_to(ROOT).as_posix(), 'width': width, 'height': height,
                       'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
    browser.close()

css_path = ROOT / 'assets/css/site.css'
raw = css_path.read_bytes()
blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
assert blob in {'40b09e86f4dde91e79c54e19372dee12cf1860b1', 'f9abe8a61675fbd2a5678aff8f3f7221ba78f3aa'}, 'Unreviewed CSS change'
css = raw.decode()
marker = '/* Responsive Instagram posts:'
if marker in css: css = css.split(marker)[0].rstrip() + '\n'
replacements = {
 '.video-embed__frame { aspect-ratio: 9 / 16; border-radius: 3px; overflow: hidden; position: relative; }': '.video-embed__frame { aspect-ratio: 9 / 16; min-width: 0; min-height: 0; flex-shrink: 0; border-radius: 3px; overflow: hidden; position: relative; background: #111; }',
 '.video-embed__frame iframe { width: 100%; height: 100%; display: block; border: 0; }': '.video-embed__frame iframe { position: absolute; inset: 0; width: 100%; height: 100%; display: block; border: 0; }',
 '.video-embed__facade { position: relative; display: block;': '.video-embed__facade { position: absolute; inset: 0; display: block;',
 '.video-embed__facade img { display: block; width: 100%; height: 100%; object-fit: cover; }': '.video-embed__facade img { display: block; width: 100%; height: 100%; object-fit: contain; }',
}
for old, new in replacements.items():
    assert css.count(old) + css.count(new) == 1, f'Unexpected video rule: {old}'
    css = css.replace(old, new, 1)
css += '''

/* Instagram embeds distort portrait posters inside their cross-origin frame.
   Serve the actual local poster at its native ratio; activation opens the
   original post. No third-party script, cookies or fixed-height iframe is
   needed while reading. width/height attributes reserve space before loading. */
.video-embed.video-embed--ig,
.video-embed.video-embed--reel { padding: 0; min-width: 0; max-width: min(360px, 100%); height: auto; aspect-ratio: auto; background: #111; }
.video-embed__instagram-preview { display: block; position: relative; overflow: hidden; background: #111; }
.video-embed__instagram-preview img { display: block; width: 100%; height: auto; object-fit: contain; }
.video-embed__instagram-preview:hover .video-embed__play,
.video-embed__instagram-preview:focus-visible .video-embed__play { background: rgba(20, 14, 6, .72); transform: translate(-50%, -50%) scale(1.08); }
.video-embed__instagram-preview:focus-visible { outline: 3px solid var(--c-accent); outline-offset: -3px; }
.video-embed__fallback { margin: 0; padding: .85rem 1rem; text-align: center; font-size: .875rem; line-height: 1.5; overflow-wrap: anywhere; background: #fff; }
.video-embed__fallback a { color: var(--c-accent-ink); text-decoration: underline; text-underline-offset: 3px; }
.video-embed__fallback a:hover { color: var(--c-accent); }
'''
css_path.write_text(css)

def strip_new_ui(soup):
    for node in soup.select('.instagram-media, .video-embed__instagram-preview, .video-embed__fallback'): node.decompose()
    return soup

migration = []
for path, text in pages:
    before = BeautifulSoup(text, 'html.parser')
    name, lang = path.relative_to(ROOT).as_posix(), before.html['lang']
    assert lang in labels
    assert hashlib.sha256('\n'.join(before.select_one('main').stripped_strings).encode()).hexdigest() == baseline[name]['main_text_sha256'], f'Unreviewed narrative change: {name}'
    old_images = [str(i) for i in before.find_all('img')]
    old_structured = [str(i) for i in before.select('script[type="application/ld+json"]')]
    clean_before = strip_new_ui(BeautifulSoup(text, 'html.parser'))
    old_links = [str(a) for a in clean_before.find_all('a')]
    records = []
    def replace(match):
        key, url, title = info(match[0]); record = posts[key]
        assert title, f'Missing original title: {key}'
        depth = len(path.relative_to(ROOT).parents) - 1
        src = '../' * depth + record['image']
        safe_url, safe_title = html.escape(url, quote=True), html.escape(title, quote=True)
        aria = html.escape(labels[lang][1] + title, quote=True)
        records.append(key)
        return (f'<a class="video-embed__instagram-preview" href="{safe_url}" target="_blank" rel="noopener" aria-label="{aria}">\n'
                f'                <img src="{src}" width="{record["width"]}" height="{record["height"]}" loading="lazy" decoding="async" alt="{safe_title}" />\n'
                '                <span class="video-embed__play" aria-hidden="true"></span>\n'
                '              </a>\n'
                f'              <p class="video-embed__fallback"><a href="{safe_url}" target="_blank" rel="noopener">{labels[lang][0]}</a></p>')
    updated = pattern.sub(replace, text)
    updated = re.sub(r'^[ \t]*\.video-embed--(?:ig|reel) iframe\s*\{[^}]*\}\s*\n', '', updated, flags=re.M)
    updated = re.sub(r'^[ \t]*<script\b[^>]*\bsrc="https://www.instagram.com/embed.js"[^>]*>\s*</script>\s*\n', '', updated, flags=re.M)
    after = BeautifulSoup(updated, 'html.parser')
    assert old_structured == [str(i) for i in after.select('script[type="application/ld+json"]')], f'Metadata changed: {name}'
    assert old_images == [str(i) for i in after.find_all('img') if not i.find_parent(class_='video-embed__instagram-preview')], f'Original images changed: {name}'
    baseline[name]['main_text_sha256'] = hashlib.sha256('\n'.join(after.select_one('main').stripped_strings).encode()).hexdigest()
    baseline[name]['alt_sha256'] = hashlib.sha256(json.dumps([i.get('alt') for i in after.select('main img')], ensure_ascii=False).encode()).hexdigest()
    clean_after = strip_new_ui(BeautifulSoup(updated, 'html.parser'))
    assert clean_before.body.get_text(' ', strip=True) == clean_after.body.get_text(' ', strip=True), f'Original body text changed: {name}'
    assert old_links == [str(a) for a in clean_after.find_all('a')], f'Original links changed: {name}'
    path.write_text(updated)
    migration.append({'page': name, 'posters': records, 'original_body_text_unchanged': True, 'original_images_unchanged': True, 'original_links_unchanged': True})
BASELINE.write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + '\n')
(ROOT / 'site-data/instagram-posters.json').write_text(json.dumps(posts, ensure_ascii=False, indent=2) + '\n')
report = {'pages': migration, 'posts': posts, 'playback': 'Instagram opens original post in a new tab; YouTube retains inline playback'}
(OUT / 'instagram-poster-migration.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False, indent=2))
