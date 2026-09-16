#!/usr/bin/env python3
"""Summarize a local Search Console query CSV; never invent missing account data.

Usage: python tools/seo_baseline.py Queries.csv > baseline.json
Accepts English or Traditional Chinese GSC headers. Keep exports outside this
public repository. No credentials, network requests, or third-party analytics.
"""
import argparse,csv,json,re
p=argparse.ArgumentParser(description=__doc__);p.add_argument('csv');a=p.parse_args()
ALIASES={'query':['Top queries','Query','熱門查詢','查詢'], 'clicks':['Clicks','點擊次數'], 'impressions':['Impressions','曝光次數'], 'position':['Position','平均排序','排名']}
with open(a.csv,encoding='utf-8-sig',newline='') as f:
    reader=csv.DictReader(f);columns={}
    for key,names in ALIASES.items():
        columns[key]=next((n for n in names if n in (reader.fieldnames or [])),None)
    if not all(columns.values()):raise SystemExit('Unsupported/missing CSV columns; export a GSC Queries table in English or Traditional Chinese.')
    result={name:{'queries':0,'clicks':0,'impressions':0,'position_weight':0.0} for name in ('brand','non_brand')}
    for row in reader:
        q=row[columns['query']]
        group='brand' if re.search(r'許\s*哲\s*睿|hsu[\s,.-]*che[\s.-]*jui|che[\s.-]*jui[\s,.-]*hsu|5219rayhsu',q,re.I) else 'non_brand'
        try:
            clicks=int(row[columns['clicks']].replace(',','')); impressions=int(row[columns['impressions']].replace(',','')); position=float(row[columns['position']].replace(',',''))
        except ValueError:raise SystemExit('Non-numeric metrics found; no estimated values were substituted.')
        if clicks<0 or impressions<0 or clicks>impressions:raise SystemExit('Inconsistent counts in CSV.')
        stats=result[group];stats['queries']+=1;stats['clicks']+=clicks;stats['impressions']+=impressions;stats['position_weight']+=position*impressions
for stats in result.values():
    impressions=stats['impressions'];stats['ctr']=stats['clicks']/impressions if impressions else None
    stats['impression_weighted_position']=stats.pop('position_weight')/impressions if impressions else None
print(json.dumps({'scope':'exported query rows only; not whole-property totals','source':a.csv,'segments':result},ensure_ascii=False,indent=2))
