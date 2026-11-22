import httpx
from clipping_tools.ingest.news import NEWS_SOURCES

for source_name, url in NEWS_SOURCES:
    try:
        r = httpx.get(url, headers={"User-Agent": "CLIPZIDA test"}, timeout=30)
        print(f"{source_name}: status={r.status_code} len={len(r.content)}")
        print(f"  first 200: {r.text[:200]}")
    except Exception as e:
        print(f"{source_name}: ERROR {e}")
