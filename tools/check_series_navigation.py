#!/usr/bin/env python3
"""Cold-load regression: lazy collage images must not shift anchor landings."""
import functools,http.server,threading
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args): pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    with sync_playwright() as pw:
        import os
        options={'headless':True}
        if os.environ.get('CHROMIUM_PATH'):options['executable_path']=os.environ['CHROMIUM_PATH']
        browser=pw.chromium.launch(**options)
        for prefix in ('','en/','ja/'):
            for width in (390,1280):
                page=browser.new_page(viewport={'width':width,'height':900})
                page.goto(f'http://127.0.0.1:{server.server_port}/{prefix}works/chaos-body-shop/',wait_until='load')
                page.locator('.series-card__link[href="#id"]').click()
                page.wait_for_timeout(2200)
                top=page.locator('#id').evaluate('(e)=>e.getBoundingClientRect().top')
                assert abs(top-72)<8,(prefix,width,top)
                assert page.locator('.rail__item[href="#series"]').count()==1
                assert page.locator('.rail__item[href="#awards"]').count()==1
                if width==1280:
                    for anchor in ('series','awards'):
                        page.locator(f'.rail__item[href="#{anchor}"]').click()
                        page.wait_for_timeout(2200)
                        y=page.locator('#'+anchor).evaluate('(e)=>e.getBoundingClientRect().top')
                        assert abs(y-72)<8,(prefix,anchor,y)
                page.close()
                print('PASS',prefix or 'zh',width,flush=True)
        browser.close()
finally:
    server.shutdown()
