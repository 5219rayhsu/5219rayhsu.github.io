#!/usr/bin/env python3
"""Check local knowledge links and original/translation metadata."""
import json, re
from pathlib import Path
from urllib.parse import unquote, urlsplit
ROOT = Path(__file__).resolve().parents[1]
count = 0
for path in (ROOT / "okf").rglob("*.md"):
    for link in re.findall(r"\]\(([^)]+)\)", path.read_text()):
        url = urlsplit(link)
        if url.scheme or url.netloc or not url.path:
            continue
        target = ROOT / unquote(url.path).lstrip("/") if url.path.startswith("/") else path.parent / unquote(url.path)
        assert target.exists(), (path, link)
        count += 1
base = "https://5219rayhsu.github.io/"
articles = {}
for prefix in ("", "en/", "ja/"):
    text = (ROOT / prefix / "texts/joanna-fu-chaos-body-shop/index.html").read_text()
    data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', text, re.S)[1])
    node = next(n for n in data["@graph"] if n.get("@type") == "Article")
    assert node["author"]["alternateName"] == "Joanna Fu"
    assert node["mainEntityOfPage"]["@id"] == node["url"]
    assert node["inLanguage"] == ("en" if prefix == "en/" else "zh-Hant")
    articles[prefix] = node
assert articles[""]["workTranslation"]["@id"] == articles["en/"]["@id"]
assert articles["en/"]["translationOfWork"]["@id"] == articles[""]["@id"]
assert articles["en/"]["translator"]["@id"] == base + "#person"
print(f"PASS: {count} knowledge links, article authorship and translation relationships")
