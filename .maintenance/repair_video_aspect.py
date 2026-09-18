#!/usr/bin/env python3
"""One-time, guarded repair. No artwork prose, media URL or image is changed."""
from pathlib import Path
import hashlib, html, json, re
from urllib.parse import urlsplit
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
css_path = ROOT / 'assets/css/site.css'
original = css_path.read_bytes()
blob = hashlib.sha1(b'blob ' + str(len(original)).encode() + b'\0' + original).hexdigest()
assert blob == '40b09e86f4dde91e79c54e19372dee12cf1860b1', 'CSS changed since diagnosis; review before applying'
css = original.decode()
replacements = {
    '.video-embed__frame { aspect-ratio: 9 / 16; border-radius: 3px; overflow: hidden; position: relative; }':
    '.video-embed__frame { aspect-ratio: 9 / 16; min-width: 0; min-height: 0; flex-shrink: 0; border-radius: 3px; overflow: hidden; position: relative; background: #111; }',
    '.video-embed__frame iframe { width: 100%; height: 100%; display: block; border: 0; }':
    '.video-embed__frame iframe { position: absolute; inset: 0; width: 100%; height: 100%; display: block; border: 0; }',
    '.video-embed__facade { position: relative; display: block;':
    '.video-embed__facade { position: absolute; inset: 0; display: block;',
    '.video-embed__facade img { display: block; width: 100%; height: 100%; object-fit: cover; }':
    '.video-embed__facade img { display: block; width: 100%; height: 100%; object-fit: contain; }',
}
for old, new in replacements.items():
    assert css.count(old) == 1, f'Expected one CSS rule: {old}'
    css = css.replace(old, new, 1)
css += '''

/* Responsive Instagram posts: the provider owns the complete post height,
   including its header/controls. Never force these iframes into a video ratio
   or a fixed pixel height. Width overrides also cover the provider's inline
   minimum width on narrow phones; fallback links remain outside the embed. */
.video-embed.video-embed--ig,
.video-embed.video-embed--reel { padding: 0; min-width: 0; height: auto; aspect-ratio: auto; background: #fff; }
.video-embed--ig .instagram-media,
.video-embed--reel .instagram-media {
  display: block; width: 100% !important; min-width: 0 !important;
  max-width: 100% !important; margin: 0 !important;
  border: 0 !important; box-shadow: none !important;
}
.video-embed blockquote.instagram-media { padding: 1.25rem; line-height: 1.6; overflow-wrap: anywhere; }
.video-embed__fallback { margin: 0; padding: .85rem 1rem; text-align: center; font-size: .875rem; line-height: 1.5; overflow-wrap: anywhere; }
.video-embed__fallback a { color: var(--c-accent-ink); text-decoration: underline; text-underline-offset: 3px; }
.video-embed__fallback a:hover { color: var(--c-accent); }
'''
css_path.write_text(css)

iframe_pattern = re.compile(r'<iframe\b[^>]*\bsrc="https://(?:www\.)?instagram\.com/[^\"]+"[^>]*>\s*</iframe>', re.S)
fixed_height = re.compile(r'^[ \t]*\.video-embed--(?:ig|reel) iframe\s*\{[^}]*\}\s*\n', re.M)
labels = {'zh-Hant': '在 Instagram 觀看 ↗', 'en': 'Watch on Instagram ↗', 'ja': 'Instagram で見る ↗'}
baseline_path = ROOT / 'site-data/content-baseline.json'
baseline = json.loads(baseline_path.read_text())
changed = []
for path in sorted(ROOT.rglob('*.html')):
    if any(part.startswith('.') for part in path.relative_to(ROOT).parts):
        continue
    text = path.read_text()
    if not iframe_pattern.search(text):
        continue
    soup = BeautifulSoup(text, 'html.parser')
    lang = soup.html['lang']
    assert lang in labels, f'Unexpected page language: {path}'
    name = path.relative_to(ROOT).as_posix()
    old_fingerprint = hashlib.sha256('\n'.join(soup.select_one('main').stripped_strings).encode()).hexdigest()
    assert baseline[name]['main_text_sha256'] == old_fingerprint, f'Unreviewed existing content change: {name}'
    before_imgs = [str(img) for img in soup.find_all('img')]
    before_links = [str(a) for a in soup.find_all('a')]
    before_scripts = [str(s) for s in soup.select('script[type="application/ld+json"]')]
    records = []
    def convert(match):
        tag = BeautifulSoup(match[0], 'html.parser').iframe
        parsed = urlsplit(html.unescape(tag['src']))
        media = re.fullmatch(r'/(p|reel|reels|tv)/([A-Za-z0-9_-]+)/embed(?:/captioned)?/?', parsed.path)
        assert media, f'Unsupported Instagram URL: {tag["src"]}'
        url = f'https://www.instagram.com/{media[1]}/{media[2]}/'
        title = tag.get('title') or labels[lang]
        safe_url, safe_title = html.escape(url, quote=True), html.escape(title, quote=True)
        records.append({'old_src': tag['src'], 'permalink': url, 'title': title})
        captioned = ' data-instgrm-captioned' if '/captioned' in parsed.path else ''
        return (f'<blockquote class="instagram-media" data-instgrm-permalink="{safe_url}" '
                f'data-instgrm-version="14"{captioned} aria-label="{safe_title}">\n'
                f'                <a href="{safe_url}" target="_blank" rel="noopener">{safe_title}</a>\n'
                '              </blockquote>\n'
                f'              <p class="video-embed__fallback"><a href="{safe_url}" target="_blank" rel="noopener">{labels[lang]}</a></p>')
    updated = iframe_pattern.sub(convert, text)
    updated, removed = fixed_height.subn('', updated)
    assert removed >= 1, f'No legacy fixed-height Instagram rule removed: {path}'
    assert 'instagram.com/embed.js' not in updated, f'Unexpected existing Instagram script: {path}'
    assert updated.count('</body>') == 1
    updated = updated.replace('</body>', '  <script async src="https://www.instagram.com/embed.js"></script>\n</body>', 1)
    after = BeautifulSoup(updated, 'html.parser')
    assert before_imgs == [str(img) for img in after.find_all('img')], f'Images changed: {path}'
    remaining_links = [str(a) for a in after.find_all('a') if not a.find_parent(class_='instagram-media') and not a.find_parent(class_='video-embed__fallback')]
    assert before_links == remaining_links, f'Existing links changed: {path}'
    assert before_scripts == [str(s) for s in after.select('script[type="application/ld+json"]')], f'Metadata changed: {path}'
    new_fingerprint = hashlib.sha256('\n'.join(after.select_one('main').stripped_strings).encode()).hexdigest()
    # The only new visible strings are the provider placeholder and the persistent
    # fallback controls. Prove the complete old body remains identical first.
    for tag in after.select('.instagram-media, .video-embed__fallback'):
        tag.decompose()
    assert soup.body.get_text(' ', strip=True) == after.body.get_text(' ', strip=True), f'Existing visible text changed: {path}'
    # Advance only these pages' UI-inclusive snapshots; keep all other baseline
    # hashes and the existing static release gate unchanged.
    baseline[name]['main_text_sha256'] = new_fingerprint
    path.write_text(updated)
    changed.append({'page': name, 'embeds': records, 'original_body_text_unchanged': True})
assert changed, 'No Instagram embeds found'
assert {record['page'].split('/')[0] for record in changed} == {'exhibitions', 'en', 'ja'}, 'Expected all three languages'
baseline_path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + '\n')
OUT = ROOT / '.test-results'
OUT.mkdir(exist_ok=True)
(OUT / 'video-migration.json').write_text(json.dumps(changed, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'changed_pages': len(changed), 'instagram_embeds': sum(len(r['embeds']) for r in changed), 'details': changed}, ensure_ascii=False, indent=2))
