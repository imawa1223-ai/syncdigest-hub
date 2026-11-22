import datetime
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

INDEX_FILE = Path("index.html")
MAX_NEW_PER_SOURCE = 3
MAX_TOTAL_ARTICLES = 120

# 對應五站看板的 sourceId：inspirr | ithome | bnext | design | koc_apple
RSS_SOURCES = [
    {
        "sourceId": "ithome",
        "sourceName": "iT 邦幫忙",
        "url": "https://ithelp.ithome.com.tw/rss/articles",
    },
    {
        "sourceId": "bnext",
        "sourceName": "數位時代 Business Next",
        "url": "https://www.bnext.com.tw/rss",
    },
    {
        "sourceId": "koc_apple",
        "sourceName": "電腦王阿達 & 蘋果仁",
        "url": "https://www.kocpc.com.tw/feed",
    },
    {
        "sourceId": "koc_apple",
        "sourceName": "電腦王阿達 & 蘋果仁",
        "url": "https://applealmond.com/feed",
    },
    {
        "sourceId": "inspirr",
        "sourceName": "Inspirr Creation",
        "url": "https://www.inspirr.com/feed/",
    },
    {
        "sourceId": "design",
        "sourceName": "設計趨勢與 UX 觀察",
        "url": "https://www.shoppingdesign.com.tw/rss/articles.xml",
    },
]

CATEGORY_KEYWORDS = {
    "EXHIBITION": [
        "展", "雙年展", "藝術節", "博覽會", "美術館", "文創園區", "策展",
        "exhibition", "biennale", "festival", "expo", "museum",
    ],
    "AI": [
        "ai", "人工智慧", "生成式", "claude", "gpt", "chatgpt", "codex",
        "gemini", "llm", "agent", "代理", "firefly", "midjourney", "提示詞", "prompt",
    ],
    "ECOMMERCE": [
        "電商", "雙11", "雙 11", "618", "9.9", "導購", "選品", "零售",
        "品牌", "行銷", "轉換率", "購物", "rmn", "d2c", "ecommerce", "retail",
    ],
    "DESIGN": [
        "設計", "字體", "排版", "ui", "ux", "視覺", "品牌識別", "平面",
        "插畫", "動效", "svg", "figma", "包容性設計", "design", "typography",
    ],
}

POSTER_META = {
    "EXHIBITION": {
        "badgeLine1": "展訊",
        "badgeLine2": "速報",
        "posterCaps": "EXHIBITION & CULTURE",
        "posterTitle": "EXHIBITION",
        "posterPill": "最新展演快訊",
        "footerTag": "展覽動態 • 藝文現場",
    },
    "AI": {
        "badgeLine1": "最新",
        "badgeLine2": "AI",
        "posterCaps": "AI INSIGHTS & TECH",
        "posterTitle": "AI UPDATE",
        "posterPill": "AI 趨勢速報",
        "footerTag": "AI 技術 • 每日同步",
    },
    "DESIGN": {
        "badgeLine1": "設計",
        "badgeLine2": "新知",
        "posterCaps": "DESIGN & UX TRENDS",
        "posterTitle": "DESIGN NOTE",
        "posterPill": "設計靈感速報",
        "footerTag": "設計新知 • 視覺觀察",
    },
    "ECOMMERCE": {
        "badgeLine1": "電商",
        "badgeLine2": "趨勢",
        "posterCaps": "COMMERCE & BRAND",
        "posterTitle": "COMMERCE",
        "posterPill": "電商策略速報",
        "footerTag": "電商營運 • 品牌趨勢",
    },
}


def clean_text(raw: str) -> str:
    if not raw:
        return ""
    text = html.unescape(raw)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_date(date_str: str) -> str:
    today = datetime.date.today().strftime("%Y-%m-%d")
    if not date_str:
        return today
    date_str = date_str.strip()
    iso_match = re.match(r"^(\d{4}-\d{2}-\d{2})", date_str)
    if iso_match:
        return iso_match.group(1)
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return today


def classify_category(title: str, summary: str) -> str:
    content = f"{title} {summary}".lower()
    scores = {cat: 0 for cat in ["EXHIBITION", "AI", "DESIGN", "ECOMMERCE"]}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in content:
                scores[cat] += 1

    best_cat = max(scores, key=scores.get)
    if scores[best_cat] > 0:
        return best_cat
    return "DESIGN"


def detect_ai_model(title: str, summary: str) -> str:
    content = f"{title} {summary}".lower()
    if "claude" in content:
        return "Claude"
    if "codex" in content:
        return "Codex"
    if "gpt" in content or "chatgpt" in content:
        return "GPT"
    return ""


def fetch_rss_items(source: dict) -> list[dict]:
    items = []
    req = urllib.request.Request(
        source["url"],
        headers={"User-Agent": "Mozilla/5.0 (compatible; KnowledgeHubBot/1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
    except Exception as exc:
        print(f"[WARN] 抓取失敗 {source['url']}: {exc}")
        return items

    entries = root.findall(".//item")
    if not entries:
        entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    for entry in entries[:MAX_NEW_PER_SOURCE]:
        title_el = entry.find("title")
        if title_el is None:
            title_el = entry.find("{http://www.w3.org/2005/Atom}title")

        link_el = entry.find("link")
        link = ""
        if link_el is not None:
            link = (link_el.text or "").strip() or link_el.attrib.get("href", "").strip()
        if not link:
            atom_link = entry.find("{http://www.w3.org/2005/Atom}link")
            if atom_link is not None:
                link = atom_link.attrib.get("href", "").strip()

        desc_el = entry.find("description")
        if desc_el is None:
            desc_el = entry.find("summary")
        if desc_el is None:
            desc_el = entry.find("{http://www.w3.org/2005/Atom}summary")

        date_el = entry.find("pubDate")
        if date_el is None:
            date_el = entry.find("updated")
        if date_el is None:
            date_el = entry.find("{http://www.w3.org/2005/Atom}updated")

        title = clean_text(title_el.text if title_el is not None else "")
        summary = clean_text(desc_el.text if desc_el is not None else "")[:140]
        pub_date = parse_date(date_el.text if date_el is not None else "")

        if not title or not link:
            continue

        category = classify_category(title, summary)
        ai_model = detect_ai_model(title, summary) if category == "AI" else ""
        meta = POSTER_META.get(category, POSTER_META["DESIGN"])

        items.append({
            "id": f"auto-{abs(hash(link)) % 10**8}",
            "title": title,
            "sourceId": source["sourceId"],
            "sourceName": source["sourceName"],
            "category": category,
            "aiModel": ai_model,
            "date": pub_date,
            "url": link,
            "summary": summary or f"來自 {source['sourceName']} 的最新分享內容。",
            "badgeLine1": meta["badgeLine1"],
            "badgeLine2": meta["badgeLine2"],
            "posterCaps": meta["posterCaps"],
            "posterTitle": meta["posterTitle"],
            "posterSub": f"{source['sourceName']} • 每日自動同步",
            "posterPill": meta["posterPill"],
            "footerTag": meta["footerTag"],
        })

    return items


def load_existing_articles(html_content: str) -> list[dict]:
    match = re.search(
        r"const\s+ARTICLES\s*=\s*(\[[\s\S]*?\]);",
        html_content,
    )
    if not match:
        raise ValueError("在 index.html 中找不到 const ARTICLES = [...]")
    raw_array = match.group(1)
    return json.loads(raw_array)


def save_articles_to_html(html_content: str, articles: list[dict]) -> str:
    formatted_json = json.dumps(articles, ensure_ascii=False, indent=2)
    new_block = f"const ARTICLES = {formatted_json};"
    updated_html, count = re.subn(
        r"const\s+ARTICLES\s*=\s*\[[\s\S]*?\];",
        lambda _: new_block,
        html_content,
        count=1,
    )
    if count == 0:
        raise ValueError("無法替換 index.html 中的 ARTICLES 區塊")
    return updated_html


def main() -> None:
    if not INDEX_FILE.exists():
        raise FileNotFoundError("找不到 index.html，請確認與 update_news.py 放在同一層資料夾。")

    html_content = INDEX_FILE.read_text(encoding="utf-8")
    existing = load_existing_articles(html_content)
    seen_urls = {item.get("url", "").strip() for item in existing if item.get("url")}

    newly_added = []
    for src in RSS_SOURCES:
        for article in fetch_rss_items(src):
            if article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                newly_added.append(article)

    if not newly_added:
        print("沒有抓到新的不重複文章，維持現有內容。")
        return

    merged = (newly_added + existing)[:MAX_TOTAL_ARTICLES]
    new_html = save_articles_to_html(html_content, merged)
    INDEX_FILE.write_text(new_html, encoding="utf-8")
    print(f"成功新增 {len(newly_added)} 篇最新文章，目前共收錄 {len(merged)} 篇。")


if __name__ == "__main__":
    main()
