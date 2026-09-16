#!/usr/bin/env python3
"""Browser regression tests with REAL repository images, not placeholders.

BROWSER=webkit uses Playwright WebKit. CHROMIUM_PATH can choose local Chromium.
No third-party requests are sent. Failures exit nonzero before release.
"""
from __future__ import annotations
import functools, http.server, json, os, threading
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.test-results';OUT.mkdir(exist_ok=True)
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
ORIGIN=f'http://127.0.0.1:{server.server_port}'
pages=sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob('index.html') if not any(x.startswith('.') for x in p.relative_to(ROOT).parts))
selected=[pre+tail for pre in ('','en/','ja/') for tail in ('index.html','exhibitions/index.html','works/answer/index.html','works/medicine/index.html')]
report={'browser':os.environ.get('BROWSER','chromium'),'layout':[],'failure_modes':[],'images':[],'lightbox':[],'errors':[]}
def require(ok,message):
    if not ok: report['errors'].append(message)
def route(route):
    if urlsplit(route.request.url).hostname not in ('127.0.0.1','localhost'):route.abort()
    else:route.continue_()
visible_js='''() => [...document.querySelectorAll('[data-reveal], img[loading="lazy"]')].filter(el => {
  for (let n=el; n && n!==document.documentElement; n=n.parentElement) {
    if (+getComputedStyle(n).opacity===0) return true;
  }
  return false;
}).length'''
with sync_playwright() as pw:
    kind=report['browser'];launcher=getattr(pw,kind)
    options={'headless':True}
    if kind=='chromium' and os.environ.get('CHROMIUM_PATH'):options['executable_path']=os.environ['CHROMIUM_PATH']
    browser=launcher.launch(**options)
    for width,height in ((390,844),(1280,900)):
        ctx=browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce')
        ctx.route('**/*',route)
        page=ctx.new_page();page_errors=[];page.on('pageerror',lambda e:page_errors.append(str(e)))
        for name in pages:
            response=page.goto(ORIGIN+'/'+name,wait_until='load')
            require(response.status==200,f'HTTP {name}')
            result=page.evaluate('''() => ({hidden: [...document.querySelectorAll('[data-reveal]')].filter(e => +getComputedStyle(e).opacity===0).length,
              overflow: [...document.querySelectorAll('main *')].filter(e => {
                if (e.closest('[hidden]') || e.classList.contains('visually-hidden')) return false;
                let r=e.getBoundingClientRect();return r.width>0 && (r.left < -.5 || r.right > innerWidth+.5);
              }).map(e => ({tag:e.tagName,cls:e.className})).slice(0,5)})''')
            require(result['hidden']==0,f'{name}@{width}: hidden content')
            require(not result['overflow'],f'{name}@{width}: horizontal overflow {result["overflow"]}')
            require(not page_errors,f'{name}@{width}: JS exceptions {page_errors}');page_errors.clear()
            report['layout'].append({'page':name,'width':width,**result})
        ctx.close()
        for mode in ('normal','no_js','blocked_js','broken_images','observer_failure'):
            ctx=browser.new_context(viewport={'width':width,'height':height},java_script_enabled=mode!='no_js')
            ctx.route('**/*',route)
            if mode=='blocked_js':ctx.route('**/assets/js/main.js*',lambda r:r.abort())
            if mode=='broken_images':ctx.route('**/assets/img/**',lambda r:r.abort())
            if mode=='observer_failure':ctx.add_init_script('window.IntersectionObserver = class { constructor() { throw new Error("Simulated observer failure"); } };')
            page=ctx.new_page()
            for name in selected:
                page.goto(ORIGIN+'/'+name,wait_until='load')
                page.wait_for_timeout(850)
                hidden=page.evaluate(visible_js)
                require(hidden==0,f'{name}@{width}/{mode}: {hidden} hidden text/image nodes')
                report['failure_modes'].append({'page':name,'width':width,'mode':mode,'hidden':hidden})
            ctx.close()
    for width,height,dpr in ((390,844,1),(390,844,2),(390,844,3),(1280,900,1),(1280,900,2),(768,1024,2)):
        ctx=browser.new_context(viewport={'width':width,'height':height},device_scale_factor=dpr,reduced_motion='reduce')
        ctx.route('**/*',route);page=ctx.new_page()
        for work in ('answer','medicine'):
            requests=[];page.on('request',lambda r:requests.append(r.url))
            page.goto(ORIGIN+'/works/'+work+'/',wait_until='load')
            info=page.locator('.hero__frame img').evaluate('''img => ({src:img.currentSrc,width:img.getBoundingClientRect().width,height:img.getBoundingClientRect().height,complete:img.complete,natural:img.naturalWidth})''')
            require(info['complete'] and info['natural']>0,f'{work}: failed hero load')
            info.update({'page':work,'viewport':width,'dpr':dpr});report['images'].append(info)
            if work=='medicine':
                first=page.locator('.gallery__item img[src*="medicine-tarot-"]').first
                first.scroll_into_view_if_needed();page.wait_for_function("() => document.querySelector('.gallery__item img[src*=\"medicine-tarot-\"]').complete")
                src=first.evaluate('(img)=>img.currentSrc')
                require('-320w.webp' in src if dpr==1 and width==390 else bool(src),f'Thumbnail not selected on low-DPR mobile: {src}')
                require(not any('medicine-tarot-' in u and urlsplit(u).path.endswith('.jpg') for u in requests),'Full-resolution tarot downloaded before zoom')
                first.click();page.locator('[data-lightbox]').wait_for(state='visible')
                page.wait_for_function("() => document.querySelector('.lightbox__img').complete && document.querySelector('.lightbox__img').naturalWidth>0")
                full=page.locator('.lightbox__img').get_attribute('src')
                require(full.endswith('.jpg'),'Zoom should retain full JPG')
                page.keyboard.press('Tab');require(page.evaluate("() => !!document.activeElement.closest('[data-lightbox]')"),'Focus escaped dialog')
                page.keyboard.press('ArrowRight');page.keyboard.press('Escape')
                require(page.locator('[data-lightbox]').is_hidden(),'Escape did not close dialog')
                report['lightbox'].append({'viewport':width,'dpr':dpr,'preview':src,'full':full,'keyboard':'passed'})
        ctx.close()
    # Persist screenshots of actual content for visual inspection.
    ctx=browser.new_context(viewport={'width':390,'height':844},reduced_motion='reduce');ctx.route('**/*',route);page=ctx.new_page()
    for name,slug in [('index.html','home'),('exhibitions/index.html','exhibitions'),('works/medicine/index.html','medicine')]:
        page.goto(ORIGIN+'/'+name,wait_until='load');page.evaluate("() => Promise.all([...document.images].filter(i=>i.complete && i.naturalWidth>0).map(i=>i.decode().catch(()=>{})))");page.wait_for_timeout(100);page.screenshot(path=str(OUT/f'{kind}-{slug}-mobile.png'))
    ctx.close();browser.close()
server.shutdown()
(OUT/f'browser-{report["browser"]}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'browser':report['browser'],'layout_cases':len(report['layout']),'failure_cases':len(report['failure_modes']),
 'image_cases':len(report['images']),'lightbox_cases':len(report['lightbox']),'errors':report['errors']},ensure_ascii=False,indent=2))
raise SystemExit(bool(report['errors']))
