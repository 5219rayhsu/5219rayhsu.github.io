#!/usr/bin/env python3
"""Read-only release gate for static HTML, SEO, artwork integrity and images."""
from __future__ import annotations
import hashlib, json, re, subprocess, sys
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin, urlsplit, unquote
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from PIL import Image
from sync_site import ROOT, BASE, sync, thumbnail_paths

errors=[]
def require(ok, message):
    if not ok: errors.append(message)
def fingerprint(text): return hashlib.sha256(text.encode()).hexdigest()
def resolve(url, page):
    u=urlsplit(urljoin(BASE+'/'+page.relative_to(ROOT).as_posix(),url))
    if u.netloc!=urlsplit(BASE).netloc or u.scheme not in ('http','https'): return None,u.fragment
    target=ROOT/unquote(u.path.lstrip('/'))
    if target.is_dir(): target=target/'index.html'
    return target,unquote(u.fragment)
def luminance(c):
    vals=[int(c[i:i+2],16)/255 for i in (1,3,5)]
    lin=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in vals]
    return sum(a*b for a,b in zip(lin,(.2126,.7152,.0722)))
def contrast(fg,bg):
    a,b=sorted([luminance(fg),luminance(bg)])
    return (b+.05)/(a+.05)

require(not sync(check=True), 'Generated metadata/assets are stale; run tools/sync_site.py')
pages={p:BeautifulSoup(p.read_text(),'html.parser') for p in ROOT.rglob('index.html') if not any(x.startswith('.') for x in p.relative_to(ROOT).parts)}
baseline=json.loads((ROOT/'site-data/content-baseline.json').read_text())
versions={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest()[:12] for n in ('assets/css/site.css','assets/js/main.js')}
canonicals={};titles=[];descriptions=[];refs=0;srcsets=0
for p,s in pages.items():
    name=p.relative_to(ROOT).as_posix()
    require(s.html and s.html.get('lang') in ('zh-Hant','en','ja'),f'{name}: lang')
    require(len(s.select('h1'))==1,f'{name}: one H1 required')
    title=s.title.get_text(strip=True) if s.title else ''
    ds=s.select('meta[name="description"]'); desc=ds[0].get('content','').strip() if len(ds)==1 else ''
    titles.append(title);descriptions.append(desc)
    require(bool(title) and bool(desc),f'{name}: empty title/description')
    c=s.select('link[rel="canonical"]')
    expected=BASE+'/'+name[:-10]
    require(len(c)==1 and c[0].get('href')==expected,f'{name}: canonical')
    canonicals[expected]=p
    if name in baseline:
        b=baseline[name]; text='\n'.join(s.select_one('main').stripped_strings)
        require(fingerprint(text)==b['main_text_sha256'],f'{name}: artwork narrative changed; needs owner review')
        require(title==b['title'],f'{name}: original title changed')
        require(fingerprint(json.dumps([i.get('alt') for i in s.select('main img')],ensure_ascii=False))==b['alt_sha256'],f'{name}: alt text changed')
    ids=[e['id'] for e in s.select('[id]')]
    require(len(ids)==len(set(ids)),f'{name}: duplicate IDs')
    for node in s.select('[href], [src], [data-full]'):
        for key in ('href','src','data-full'):
            val=node.get(key)
            if not val or val.startswith('data:'):continue
            target,frag=resolve(val,p)
            if target is None:continue
            refs+=1
            require(target.is_file(),f'{name}: missing {key} {val}')
            if frag and target.suffix=='.html' and target.is_file():
                dest=pages.get(target) or BeautifulSoup(target.read_text(),'html.parser')
                require(dest.find(id=frag) is not None,f'{name}: missing anchor {val}')
            if node.name=='a':require(not urlsplit(val).path.endswith('index.html'),f'{name}: noncanonical internal link {val}')
    for asset,v in versions.items():
        for val in re.findall(re.escape(asset)+r'(?:\?[^"\s<>]+)?',p.read_text()):
            require(val==asset+'?v='+v, f'{name}: stale {asset} version')
    for img in s.select('img[src]'):
        require(img.has_attr('alt'),f'{name}: missing alt')
        require(img.has_attr('width') and img.has_attr('height'),f'{name}: missing image dimensions {img.get("src")}')
    for node in s.select('[srcset], [imagesrcset]'):
        for value in [node.get('srcset'),node.get('imagesrcset')]:
            if not value:continue
            for entry in value.split(','):
                parts=entry.strip().split(); url=parts[0]; w=parts[1] if len(parts)>1 else '1x'
                target,_=resolve(url,p)
                require(target is not None and target.is_file(),f'{name}: missing responsive image {url}')
                if target and target.is_file():
                    with Image.open(target) as im:
                        if w.endswith('w'):require(w==str(im.width)+'w',f'{name}: wrong width descriptor {entry}')
                srcsets+=1
    def walk(n):
        if isinstance(n,dict):
            require(not (n.get('@type')=='VisualArtwork' and 'dateCreated' in n and not re.fullmatch(r'\d{4}(?:-\d{2}(?:-\d{2})?)?(?:T[^ ]+)?',str(n['dateCreated']))),f'{name}: invalid dateCreated')
            require('in progress' not in json.dumps(n.get('hasCredential','')).lower(),f'{name}: ongoing credential declared awarded')
            for v in n.values():walk(v)
        elif isinstance(n,list):
            for v in n:walk(v)
    scripts=s.select('script[type="application/ld+json"]')
    require(bool(scripts),f'{name}: missing JSON-LD')
    for tag in scripts:
        try:walk(json.loads(tag.string or tag.get_text()))
        except ValueError as e:errors.append(f'{name}: invalid JSON-LD: {e}')
    if 'hero--framed' in p.read_text():
        source=s.select_one('.hero__frame source'); preload=s.select_one('link[rel="preload"][as="image"]')
        require(source['sizes']==preload['imagesizes'] and source['sizes']!='100vw',f'{name}: preload/hero sizes mismatch')
for p,s in pages.items():
    links={x['hreflang']:x['href'] for x in s.select('link[hreflang]')}
    require(set(links)=={'zh-Hant','en','ja','x-default'},f'{p}: missing language alternate')
    own=s.select_one('link[rel="canonical"]')['href']
    for lang,url in links.items():
        target=canonicals.get(url)
        require(target is not None,f'{p}: alternate {url} missing')
        if target:
            require(own in [a['href'] for a in pages[target].select('link[hreflang]')],f'{p}: alternate lacks return link')
require(not [t for t,n in Counter(titles).items() if n>1],'Duplicate titles')
require(not [t for t,n in Counter(descriptions).items() if n>1],'Duplicate descriptions')
ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9','i':'http://www.google.com/schemas/sitemap-image/1.1'}
xml=ET.parse(ROOT/'sitemap.xml');urls=[e.text for e in xml.findall('.//s:url/s:loc',ns)]
require(set(urls)==set(canonicals) and len(urls)==len(canonicals),'Sitemap content-page mismatch')
image_urls=[e.text for e in xml.findall('.//i:image/i:loc',ns)]
for url in image_urls:
    target,_=resolve(url,ROOT/'index.html');require(target and target.is_file(),f'Sitemap image missing: {url}')
# llms.txt remains an owner-maintained source, checked but never overwritten.
llms=ROOT/'llms.txt';require(llms.is_file() and llms.stat().st_size>0,'llms.txt missing')
llms_refs=re.findall(r'\]\((https://5219rayhsu\.github\.io/[^\s)]+)\)',llms.read_text())
for url in llms_refs:
    target,_=resolve(url,ROOT/'index.html');require(target and target.is_file(),f'llms.txt target missing: {url}')
pairs={'#ffffff':'#6e6e73','#f5f5f7':'#6e6e73','#f4f0e8':'#65656b'}
for bg,fg in pairs.items():
    require(contrast(fg,bg)>=4.5,f'Low contrast on {bg}')
subprocess.run(['node','--check',str(ROOT/'assets/js/main.js')],check=True)
small=sum(t.stat().st_size for _,t in thumbnail_paths());previous=sum(p.stat().st_size for p,_ in thumbnail_paths())
report={'content_pages':len(pages),'local_references_checked':refs,'responsive_candidates_checked':srcsets,
        'sitemap_urls':len(urls),'sitemap_image_references':len(image_urls),'llms_local_links':len(llms_refs),
        'artwork_text_and_alt_unchanged':not any('changed' in x for x in errors),
        'tarot_320w_bytes':small,'tarot_previous_506w_bytes':previous,
        'contrast':{bg:round(contrast(fg,bg),4) for bg,fg in pairs.items()},'errors':errors}
out=ROOT/'.test-results';out.mkdir(exist_ok=True);(out/'static.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
sys.exit(bool(errors))
