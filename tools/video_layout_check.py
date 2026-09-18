#!/usr/bin/env python3
"""Video geometry tests using actual repository posters, never image substitutes.
External playback is blocked. The explicitly labelled provider fixture tests
CSS height ownership, not Instagram's availability. VIDEO_PHASE=before records
baseline geometry; BROWSER chooses Chromium or WebKit.
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
phase, kind = os.environ.get('VIDEO_PHASE', 'after'), os.environ.get('BROWSER', 'chromium')
report = {'browser':kind, 'phase':phase, 'external_playback':'not tested; blocked or provider fixture', 'cases':[], 'errors':[]}
def require(ok, message):
    if not ok: report['errors'].append(message)
PROVIDER_FIXTURE = '''(() => {
  document.querySelectorAll('blockquote.instagram-media').forEach((quote, index) => {
    const iframe = document.createElement('iframe');
    iframe.className = 'instagram-media instagram-media-rendered';
    iframe.title = quote.getAttribute('aria-label') || 'Instagram sizing fixture';
    iframe.dataset.providerFixture = 'true';
    iframe.style.cssText = 'width:calc(100% - 2px);min-width:326px;max-width:540px;margin:1px;border:1px solid #ddd;';
    iframe.srcdoc = '<!doctype html><title>Provider fixture, not Instagram playback</title><p>Provider sizing fixture</p>';
    quote.replaceWith(iframe);
    const resize = () => {
      const height = Math.round(iframe.getBoundingClientRect().width * (index % 2 ? 1.25 : 16 / 9) + 180);
      iframe.style.height = height + 'px'; iframe.dataset.providerHeight = String(height);
    };
    resize(); new ResizeObserver(resize).observe(iframe.parentElement);
  });
})();'''
def routing(mode):
    def handler(route):
        url = urlsplit(route.request.url)
        if url.hostname in ('127.0.0.1','localhost'): route.continue_()
        elif mode == 'provider_fixture' and url.hostname == 'www.instagram.com' and url.path == '/embed.js':
            route.fulfill(status=200, content_type='application/javascript', body=PROVIDER_FIXTURE)
        else: route.abort()
    return handler
GEOMETRY = '''() => [...document.querySelectorAll('.video-embed__frame,.video-embed--ig,.video-embed--reel,.video-embed--9x16,.video-embed--16x9')].map(frame => {
  const rect = el => {const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right};};
  const media=frame.querySelector('.video-embed__facade,iframe,blockquote.instagram-media'), img=frame.querySelector('img');
  return {className:frame.className,frame:rect(frame),media:media?rect(media):null,
    fit:img?getComputedStyle(img).objectFit:null,src:img?img.currentSrc:null,
    natural:img?{width:img.naturalWidth,height:img.naturalHeight}:null,image:img?rect(img):null};
})'''
try:
    with sync_playwright() as pw:
        options={'headless':True}
        if kind=='chromium' and os.environ.get('CHROMIUM_PATH'): options['executable_path']=os.environ['CHROMIUM_PATH']
        browser=getattr(pw,kind).launch(**options)
        widths=(390,1280) if phase=='before' else (320,375,390,768,1280,1440)
        prefixes=('',) if phase=='before' else ('','en/','ja/')
        modes=('blocked',) if phase=='before' else ('blocked','no_js','provider_fixture')
        paths=('works/chaos-body-shop/','works/answer/','exhibitions/answer-keelung-2025/','exhibitions/seikai-tokyo-2026/')
        for width in widths:
            for mode in modes:
                ctx=browser.new_context(viewport={'width':width,'height':900 if width>700 else 844},java_script_enabled=mode!='no_js',reduced_motion='reduce')
                ctx.route('**/*',routing(mode)); page=ctx.new_page(); js_errors=[]
                page.on('pageerror',lambda error:js_errors.append(str(error)))
                for prefix in prefixes:
                    for path in paths:
                        name=prefix+path
                        page.goto(ORIGIN+'/'+name,wait_until='load')
                        case={'page':name,'width':width,'mode':mode,'image_loads':[]}; report['cases'].append(case)
                        for image in page.locator('.video-embed__facade img').all():
                            # Eager decoding here isolates geometry from native lazy-load
                            # scheduling and srcset races; the real image is unchanged.
                            image.evaluate("img=>{img.loading='eager';}")
                            image.scroll_into_view_if_needed()
                            try:
                                page.wait_for_function('(img)=>img.complete && img.naturalWidth>0',arg=image.element_handle(),timeout=10000)
                                image.evaluate('img=>img.decode().catch(()=>{})')
                            except Exception as error:
                                case['image_loads'].append({'src':image.get_attribute('src'),'error':str(error)[:300]})
                        boxes=page.evaluate(GEOMETRY); case['boxes']=boxes
                        if prefix=='' and width in (390,1280) and mode in ('blocked','provider_fixture'):
                            target=page.locator('.award--video,.video-embed--ig,.video-embed--reel').first
                            if target.count(): target.screenshot(path=str(OUT/f'video-{phase}-{kind}-{width}-{mode}-{path.strip("/").replace("/","-")}.png'))
                        if phase=='before': continue
                        require(not js_errors,f'{name}@{width}/{mode}: JS errors {js_errors}'); js_errors.clear()
                        require(not case['image_loads'],f'{name}@{width}/{mode}: failed poster load {case["image_loads"]}')
                        for box in boxes:
                            f,m=box['frame'],box['media']
                            require(f['width']>0 and f['x']>=-.5 and f['right']<=width+.5,f'{name}@{width}/{mode}: frame overflow {box}')
                            if m: require(m['width']<=f['width']+.5 and m['right']<=width+.5,f'{name}@{width}/{mode}: media overflow {box}')
                            if box['className']=='video-embed__frame':
                                require(abs(f['height']-f['width']*16/9)<1,f'{name}@{width}/{mode}: wrong portrait ratio {box}')
                                require(m and abs(m['width']-f['width'])<1 and abs(m['height']-f['height'])<1,f'{name}@{width}/{mode}: facade does not fill frame {box}')
                                require(box['fit']=='contain' and box['natural']['width']>0,f'{name}@{width}/{mode}: poster not loaded/contained {box}')
                        embeds=page.locator('.video-embed--ig,.video-embed--reel'); fallback=page.locator('.video-embed__fallback a')
                        require(fallback.count()==embeds.count(),f'{name}: missing persistent fallback')
                        for link in fallback.all(): require(link.is_visible() and link.get_attribute('href').startswith('https://www.instagram.com/'),f'{name}: unusable fallback')
                        if embeds.count():
                            require(page.locator('script[src="https://www.instagram.com/embed.js"]').count()==1,f'{name}: provider script missing/duplicated')
                            selector='[data-provider-fixture]' if mode=='provider_fixture' else 'blockquote.instagram-media'
                            require(page.locator(selector).count()==embeds.count(),f'{name}: missing rendered provider/placeholder')
                        for iframe in page.locator('[data-provider-fixture]').all():
                            result=iframe.evaluate('(el)=>({actual:el.getBoundingClientRect().height,expected:+el.dataset.providerHeight})')
                            require(abs(result['actual']-result['expected'])<1,f'{name}: provider height overridden {result}')
                        if mode!='no_js':
                            for frame in page.locator('.video-embed__frame').all():
                                before=frame.bounding_box(); button=frame.locator('button.video-embed__facade')
                                if not button.count(): continue
                                button.click(); result=frame.locator('iframe').bounding_box()
                                require(result and abs(result['width']-before['width'])<1 and abs(result['height']-before['height'])<1,f'{name}@{width}: YouTube collapses after click')
                        for iframe in page.locator('iframe[src*="youtube.com/embed/"],iframe[src*="youtube-nocookie.com/embed/"]').all():
                            dims=iframe.evaluate('el=>{const r=el.getBoundingClientRect();return {ratio:getComputedStyle(el.parentElement).aspectRatio,w:r.width,h:r.height};}')
                            if dims['ratio']=='16 / 9': require(abs(dims['w']/dims['h']-16/9)<.015,f'{name}: landscape ratio changed {dims}')
                ctx.close()
        browser.close()
finally:
    server.shutdown()
    (OUT/f'video-{phase}-{kind}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'browser':kind,'phase':phase,'layout_cases':len(report['cases']),'errors':report['errors']},ensure_ascii=False,indent=2))
if report['errors']: raise SystemExit(1)
