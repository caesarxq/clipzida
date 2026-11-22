from clipping_tools.ingest.news import fetch_news_items
items = fetch_news_items()
print(f"got {len(items)} items")
for it in items[:3]:
    print(it)
