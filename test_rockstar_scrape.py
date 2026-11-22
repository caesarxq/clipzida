import httpx
from bs4 import BeautifulSoup

url = "https://www.rockstargames.com/newswire/"
r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; CLIPZIDA/1.0)"}, timeout=30)
print(f"status={r.status_code} len={len(r.content)}")
soup = BeautifulSoup(r.text, "html.parser")
links = []
for a in soup.find_all("a", href=True):
    href = a["href"]
    text = a.get_text(strip=True)
    if "newswire" in href and text and len(text) > 10:
        links.append((text, href))
        if len(links) >= 10:
            break
for text, href in links:
    print(f"{text[:80]} -> {href}")
