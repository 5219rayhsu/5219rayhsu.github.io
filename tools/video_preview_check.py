#!/usr/bin/env python3
"""Regression for actual, local media posters at mobile and desktop widths.

All original video/Instagram posters and fonts are used. Unrelated artwork
images and external players are blocked here; browser_check.py separately
covers the complete site. No fake Instagram rendering is used in this test.
"""
from __future__ import annotations
import functools, http.server, json, os, threading
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.test-results'; OUT.mkdir(exist_ok=True)
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(ROOT)))
threading.Thread(target=server.serve_forever, daemon=True).start()
ORIGIN = f'http://127.0.0.1:{server.server_port}'
kind = os.environ.get('BROWSER', 'chromium')
manifest = json.loads((ROOT / 'site-data/instagram-posters.json').read_text())
report = {'browser': kind, 'external_playback': 'not tested; Instagram opens its original post and YouTube uses its existing iframe', 'cases': [], 'errors': []}
def require(ok, message):
    if not ok: report['errors'].append(message)
def route_request(route):
    u = urlsplit(route.request.url)
    if u.hostname not in ('127.0.0.1', 'localhost'): return route.abort()
    if route.request.resource_type == 'image' and '/instagram/' not in u.path and 'video' not in Path(u.path).name: return route.abort()
    return route.continue_()
GEOMETRY = '''() => [...document.querySelectorAll('.video-embed__frame,.video-embed__instagram-preview')].map(el=>{
 const box=e=>{let r=e.getBoundingClientRect();return {x:r.x,width:r.width,height:r.height,right:r.right};};
 const img=el.querySelector('img'),child=el.querySelector('.video-embed__facade');
 return {type:el.className,frame:box(el),child:child?box(child):null,
 image:img?box(img):null,natural:img?[img.naturalWidth,img.naturalHeight]:null,
 fit:img?getComputedStyle(img).objectFit:null,src:img?img.currentSrc:null,href:el.getAttribute('href')};
})'''
try:
    with sync_playwright() as pw:
        options = {'headless': True}
        if kind == 'chromium' and os.environ.get('CHROMIUM_PATH'): options['executable_path'] = os.environ['CHROMIUM_PATH']
        browser = getattr(pw, kind).launch(**options)
        for width in (320, 375, 390, 768, 1280, 1440):
            for enabled in (True, False):
                # All languages/widths normally; both narrow and desktop no-JS.
                if not enabled and width not in (320, 1280): continue
                ctx = browser.new_context(viewport={'width': width, 'height': 900}, java_script_enabled=enabled, reduced_motion='reduce')
                ctx.route('**/*', route_request)
                page = ctx.new_page(); errors = []; external_instagram = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.on('request', lambda r: external_instagram.append(r.url) if 'instagram.com' in urlsplit(r.url).netloc else None)
                for prefix in ('', 'en/', 'ja/'):
                    for slug in ('works/chaos-body-shop/', 'works/answer/', 'exhibitions/answer-keelung-2025/', 'exhibitions/seikai-tokyo-2026/'):
                        name = prefix + slug
                        page.goto(ORIGIN + '/' + name, wait_until='load')
                        for image in page.locator('.video-embed__instagram-preview img,.video-embed__facade img').all():
                            image.evaluate("el=>{el.loading='eager';}")
                            page.wait_for_function('el=>el.complete&&el.naturalWidth>0', arg=image.element_handle(), timeout=10000)
                        boxes = page.evaluate(GEOMETRY)
                        report['cases'].append({'page': name, 'width': width, 'javascript': enabled, 'boxes': boxes})
                        require(not errors, f'{name}@{width}: JavaScript errors {errors}'); errors.clear()
                        require(not external_instagram, f'{name}: unexpected Instagram request while reading {external_instagram}'); external_instagram.clear()
                        require(page.locator('iframe[src*="instagram.com"],script[src*="instagram.com"]').count() == 0, f'{name}: distorted vendor preview reintroduced')
                        for box in boxes:
                            f, image = box['frame'], box['image']
                            require(f['width'] > 0 and f['x'] >= -.5 and f['right'] <= width + .5, f'{name}@{width}: frame overflow {box}')
                            require(box['fit'] == 'contain' and box['natural'][0] > 0, f'{name}: missing or stretched poster {box}')
                            if box['type'] == 'video-embed__instagram-preview':
                                nw, nh = box['natural']
                                require(abs(image['height'] - image['width'] * nh / nw) < 1, f'{name}@{width}: Instagram poster squashed {box}')
                                require(abs(f['height'] - image['height']) < 1, f'{name}: poster clipped by wrapper {box}')
                                key = box['href'].strip('/').split('/')[-1]
                                require(key in manifest and box['href'] == manifest[key]['permalink'], f'{name}: original Instagram URL changed')
                            else:
                                require(abs(f['height'] - f['width'] * 16 / 9) < 1, f'{name}@{width}: portrait YouTube frame ratio {box}')
                                require(abs(box['child']['height'] - f['height']) < 1 and abs(box['child']['width'] - f['width']) < 1, f'{name}: YouTube facade size mismatch')
                        previews = page.locator('.video-embed__instagram-preview')
                        require(previews.count() == page.locator('.video-embed__fallback a').count(), f'{name}: missing visible original-post link')
                        for link in previews.all():
                            require(link.get_attribute('target') == '_blank' and 'noopener' in link.get_attribute('rel') and bool(link.get_attribute('aria-label')), f'{name}: unsafe or unlabelled link')
                        if enabled and not prefix and width in (390, 1280):
                            target = page.locator('.video-grid,.award--video,.video-embed--ig').first
                            if target.count(): target.screenshot(path=str(OUT / f'final-video-{kind}-{width}-{slug.strip("/").replace("/","-")}.png'))
                        if enabled:
                            for frame in page.locator('.video-embed__frame').all():
                                before = frame.bounding_box(); frame.locator('button.video-embed__facade').click()
                                after = frame.locator('iframe').bounding_box()
                                require(after and abs(after['width'] - before['width']) < 1 and abs(after['height'] - before['height']) < 1, f'{name}@{width}: YouTube playback geometry changed')
                        for iframe in page.locator('iframe[src*="youtube.com/embed/"],iframe[src*="youtube-nocookie.com/embed/"]').all():
                            value = iframe.evaluate('el=>{const r=el.getBoundingClientRect();return {ratio:getComputedStyle(el.parentElement).aspectRatio,w:r.width,h:r.height};}')
                            if value['ratio'] == '16 / 9': require(abs(value['w'] / value['h'] - 16 / 9) < .015, f'{name}: landscape YouTube ratio changed')
                ctx.close()
        browser.close()
finally:
    server.shutdown()
    (OUT / f'video-preview-{kind}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'browser': kind, 'cases': len(report['cases']), 'errors': report['errors']}, ensure_ascii=False, indent=2))
if report['errors']: raise SystemExit(1)
