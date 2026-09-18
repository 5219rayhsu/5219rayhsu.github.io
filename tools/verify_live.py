#!/usr/bin/env python3
"""Verify the deployed bytes with GET, not search cache or HEAD.

Waits for this exact CSS/JS, then checks all canonical pages and llms.txt.
Run in a network-enabled environment after the Pages deployment.
"""
from __future__ import annotations
import hashlib, json, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
BASE='https://5219rayhsu.github.io'

def get(path):
    request=urllib.request.Request(BASE+'/'+path,headers={'Cache-Control':'no-cache','User-Agent':'PortfolioReleaseVerifier/1.0'})
    with urllib.request.urlopen(request,timeout=30) as response:
        return response.status,response.read(),dict(response.headers)

def verify(path,urlpath=None):
    expected=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
    for attempt in range(6):
        try:
            code,raw,headers=get(urlpath if urlpath is not None else path)
            actual=hashlib.sha256(raw).hexdigest()
            if code==200 and actual==expected:
                return {'path':path,'url':BASE+'/'+(urlpath if urlpath is not None else path),'status':code,'sha256':actual,'matches':True,
                        'headers':{k:v for k,v in headers.items() if k.lower() in ('content-type','cache-control','strict-transport-security','content-security-policy','x-content-type-options','referrer-policy')}}
        except (OSError,urllib.error.URLError) as error:
            actual=str(error)
        if attempt<5:time.sleep(15)
    return {'path':path,'matches':False,'observed':actual}

# CSS is the release sentinel: do not mistake a previous successful deployment for this one.
for attempt in range(20):
    try:
        _,data,_=get('assets/css/site.css?release='+hashlib.sha256((ROOT/'assets/css/site.css').read_bytes()).hexdigest()[:12])
        if data==(ROOT/'assets/css/site.css').read_bytes():break
    except OSError:pass
    time.sleep(15)
else:raise SystemExit('The expected release did not reach Pages in five minutes.')
items=[(p.relative_to(ROOT).as_posix(),p.relative_to(ROOT).as_posix()[:-10]) for p in ROOT.rglob('index.html') if not any(x.startswith('.') for x in p.relative_to(ROOT).parts)]
items += [(p,p) for p in ('assets/css/site.css','assets/js/main.js','llms.txt','sitemap.xml','robots.txt')]
# Verify the newly local posters themselves, not just HTML references to them.
posters=json.loads((ROOT/'site-data/instagram-posters.json').read_text())
items += [(entry['image'],entry['image']) for entry in posters.values()]
with ThreadPoolExecutor(max_workers=4) as pool:
    results=list(pool.map(lambda item:verify(*item),items))
# Old index.html entry points are retained; a 200 response or redirect to the canonical page is fine.
legacy=[]
for path in ('index.html','en/index.html','ja/index.html','works/index.html'):
    code,_,_=get(path);legacy.append({'path':path,'status':code})
try:
    get('release-verification-nonexistent-page-20260916/')
    missing_status=200
except urllib.error.HTTPError as error:missing_status=error.code
report={'checks':results,'legacy_urls':legacy,'missing_page_status':missing_status,
        'passed':all(x['matches'] for x in results) and missing_status==404 and all(x['status']==200 for x in legacy)}
out=ROOT/'.test-results';out.mkdir(exist_ok=True);(out/'live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
raise SystemExit(not report['passed'])
