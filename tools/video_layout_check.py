#!/usr/bin/env python3
"""Video layout regression using actual site images.

BROWSER=chromium|webkit; VIDEO_PHASE=before records the original layout only.
External playback is deliberately blocked. A labelled provider fixture checks
that site CSS allows Instagram to own its height, not Instagram availability.
"""
from __future__ import annotations
import functools, http.server, json, os, threading
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.test-results'
OUT.mkdir(exist_ok=True)
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(ROOT)))
threading.Thread(target=server.serve_forever, daemon=True).start()
ORIGIN = f'http://127.0.0.1:{server.server_port}'
phase = os.environ.get('VIDEO_PHASE', 'after')
kind = os.environ.get('BROWSER', 'chromium')
report = {'browser': kind, 'phase': phase, 'external_playback': 'not tested; requests blocked or provider fixture', 'cases': [], 'errors': []}
def require(ok, message):
    if not ok: report['errors'].append(message)

PROVIDER_FIXTURE = '''(() => {
  document.querySelectorAll('blockquote.instagram-media').forEach((quote, index) => {
    const iframe = document.createElement('iframe');
    iframe.className = 'instagram-media instagram-media-rendered';
    iframe.title = quote.getAttribute('aria-label') || 'Instagram test fixture';
    iframe.dataset.providerFixture = 'true';
    iframe.style.cssText = 'width:calc(100% - 2px);min-width:326px;max-width:540px;margin:1px;border:1px solid #ddd;';
    iframe.srcdoc = '<!doctype html><title>Provider sizing fixture (not Instagram playback)</title><p>Provider sizing fixture</p>';
    quote.replaceWith(iframe);
    const resize = () => {
      const h = Math.round(iframe.getBoundingClientRect().width * (index % 2 ? 1.25 : 16 / 9) + 180);
      iframe.style.height = h + 'px';
      iframe.dataset.providerHeight = String(h);
    };
    resize();
    new ResizeObserver(resize).observe(iframe.parentElement);
  });
})();'''

def routing(mode):
    def handler(route):
        url = urlsplit(route.request.url)
        if url.hostname in ('127.0.0.1', 'localhost'):
            route.continue_()
        elif mode == 'provider_fixture' and url.hostname == 'www.instagram.com' and url.path == '/embed.js':
            route.fulfill(status=200, content_type='application/javascript', body=PROVIDER_FIXTURE)
        else:
            route.abort()
    return handler

GEOMETRY = '''() => [...document.querySelectorAll('.video-embed__frame, .video-embed--ig, .video-embed--reel, .video-embed--9x16, .video-embed--16x9')].map(frame => {
  const rect = el => {const r=el.getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right};};
  const media = frame.querySelector('.video-embed__facade, iframe, blockquote.instagram-media');
  const img = frame.querySelector('img');
  return {className:frame.className,frame:rect(frame),media:media?rect(media):null,
    fit:img?getComputedStyle(img).objectFit:null,
    natural:img?{width:img.naturalWidth,height:img.naturalHeight}:null,
    image:img?rect(img):null};
})'''

try:
    with sync_playwright() as pw:
        launcher = getattr(pw, kind)
        launch_options = {'headless': True}
        if kind == 'chromium' and os.environ.get('CHROMIUM_PATH'):
            launch_options['executable_path'] = os.environ['CHROMIUM_PATH']
        browser = launcher.launch(**launch_options)
        widths = (390, 1280) if phase == 'before' else (320, 375, 390, 768, 1280, 1440)
        prefixes = ('',) if phase == 'before' else ('', 'en/', 'ja/')
        modes = ('blocked',) if phase == 'before' else ('blocked', 'no_js', 'provider_fixture')
        paths = ('works/chaos-body-shop/', 'works/answer/', 'exhibitions/answer-keelung-2025/', 'exhibitions/seikai-tokyo-2026/')
        for width in widths:
            for mode in modes:
                ctx = browser.new_context(viewport={'width': width, 'height': 900 if width > 700 else 844},
                                          java_script_enabled=mode != 'no_js', reduced_motion='reduce')
                ctx.route('**/*', routing(mode))
                page = ctx.new_page()
                js_errors = []
                page.on('pageerror', lambda error: js_errors.append(str(error)))
                for prefix in prefixes:
                    for path in paths:
                        name = prefix + path
                        page.goto(ORIGIN + '/' + name, wait_until='load')
                        for image in page.locator('.video-embed__facade img').all():
                            image.scroll_into_view_if_needed()
                            image.evaluate('(img) => img.decode()')
                        boxes = page.evaluate(GEOMETRY)
                        case = {'page': name, 'width': width, 'mode': mode, 'boxes': boxes}
                        report['cases'].append(case)
                        if phase != 'before':
                            require(not js_errors, f'{name}@{width}/{mode}: JavaScript errors {js_errors}')
                            for box in boxes:
                                f, m = box['frame'], box['media']
                                require(f['width'] > 0 and f['x'] >= -.5 and f['right'] <= width + .5,
                                        f'{name}@{width}/{mode}: frame outside viewport {box}')
                                if m:
                                    require(m['width'] <= f['width'] + .5 and m['right'] <= width + .5,
                                            f'{name}@{width}/{mode}: media overflow {box}')
                                if box['className'] == 'video-embed__frame':
                                    require(abs(f['height'] - f['width'] * 16 / 9) < 1,
                                            f'{name}@{width}/{mode}: portrait frame ratio {box}')
                                    require(m and abs(m['width'] - f['width']) < 1 and abs(m['height'] - f['height']) < 1,
                                            f'{name}@{width}/{mode}: facade not filling frame {box}')
                                    require(box['fit'] == 'contain' and box['natural']['width'] > 0,
                                            f'{name}@{width}/{mode}: poster is not loaded/contained {box}')
                            fallback = page.locator('.video-embed__fallback a')
                            embeds = page.locator('.video-embed--ig, .video-embed--reel')
                            require(fallback.count() == embeds.count(), f'{name}: missing persistent Instagram fallback')
                            for link in fallback.all():
                                require(link.is_visible() and link.get_attribute('href').startswith('https://www.instagram.com/'),
                                        f'{name}: unusable Instagram fallback')
                            for iframe in page.locator('[data-provider-fixture]').all():
                                result = iframe.evaluate('(el)=>({actual:el.getBoundingClientRect().height,expected:+el.dataset.providerHeight})')
                                require(abs(result['actual'] - result['expected']) < 1, f'{name}: site overrides provider height {result}')
                            if embeds.count():
                                require(page.locator('script[src="https://www.instagram.com/embed.js"]').count() == 1,
                                        f'{name}: provider script missing/duplicated')
                                if mode == 'provider_fixture':
                                    require(page.locator('[data-provider-fixture]').count() == embeds.count(), f'{name}: fixture not rendered')
                                else:
                                    require(page.locator('blockquote.instagram-media').count() == embeds.count(), f'{name}: missing no-script placeholder')
                            if mode != 'no_js':
                                for frame in page.locator('.video-embed__frame').all():
                                    before = frame.bounding_box()
                                    button = frame.locator('button.video-embed__facade')
                                    if not button.count(): continue
                                    button.click()
                                    iframe = frame.locator('iframe')
                                    result = iframe.bounding_box()
                                    require(result and abs(result['width'] - before['width']) < 1 and abs(result['height'] - before['height']) < 1,
                                            f'{name}@{width}: YouTube collapses after click')
                            for iframe in page.locator('iframe[src*="youtube.com/embed/"], iframe[src*="youtube-nocookie.com/embed/"]').all():
                                dims = iframe.evaluate('el=>{const p=el.parentElement,r=p.getBoundingClientRect(),i=el.getBoundingClientRect();return {ratio:getComputedStyle(p).aspectRatio,w:r.width,h:r.height,iw:i.width,ih:i.height};}')
                                if dims['ratio'] == '16 / 9':
                                    require(abs(dims['iw'] / dims['ih'] - 16 / 9) < .015, f'{name}: landscape YouTube ratio changed {dims}')
                        if prefix == '' and width in (390,1280) and mode in ('blocked','provider_fixture'):
                            target = page.locator('.award--video, .video-embed--ig, .video-embed--reel').first
                            if target.count():
                                target.screenshot(path=str(OUT / f'video-{phase}-{kind}-{width}-{mode}-{path.strip("/").replace("/","-")}.png'))
                        js_errors.clear()
                ctx.close()
        browser.close()
finally:
    server.shutdown()
    (OUT / f'video-{phase}-{kind}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'browser':kind,'phase':phase,'layout_cases':len(report['cases']),'errors':report['errors']}, ensure_ascii=False, indent=2))
if report['errors']:
    raise SystemExit(1)
