import httpx
import xml.etree.ElementTree as ET

url = "https://news.google.com/rss/search?q=GTA+6&hl=en-US&gl=US&ceid=US:en"
r = httpx.get(url, headers={"User-Agent": "CLIPZIDA news ingest"}, timeout=30)
print(f"status={r.status_code} len={len(r.content)}")
root = ET.fromstring(r.content)
items = list(root.iter("item"))[:5]
for item in items:
    title = item.findtext("title", default="")
    link = item.findtext("link", default="")
    print(f"- {title} -> {link}")
