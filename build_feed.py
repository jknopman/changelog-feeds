#!/usr/bin/env python3
"""
Generate an RSS 2.0 feed from Klaviyo's "What's New" page.

Why this exists: RSS.app / generic builders can't auto-detect a feed from this
page because the dated changelog entries under "All updates" have no clean,
repeating item container or per-item permalink. This script parses them
directly and emits valid RSS, which RSS.app and Slack ingest without any
HTML parsing on their end.

Parsing strategy: anchor on the date string (YYYY-MM-DD), which is the most
stable signal on the page, rather than on hashed CSS classes. For each date we
grab the nearest preceding heading (title), the nearest following paragraph
(description), and the first following "Learn more"-style link (optional).
"""

import hashlib
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup, NavigableString
from feedgen.feed import FeedGenerator

SOURCE_URL = "https://www.klaviyo.com/whats-new"
FEED_TITLE = "Klaviyo — What's New"
FEED_DESC = "Latest Klaviyo product updates and releases (unofficial feed)."
MAX_ITEMS = 60
DATE_RE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})\s*$")
HEADING_TAGS = ["h3", "h2", "h4"]
# Section headers that are NOT entry titles, so we never mistake them for one.
NON_ENTRY_TITLES = {
    "what's new", "highlights", "all updates", "free tools to try",
    "composer", "customer agent", "social marketing",
    "custom object expansion", "whatsapp enhancements",
    "website personalization", "multi-branch flows",
    "always know what's new in klaviyo",
}


def fetch(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def nearest_title(date_el):
    """Closest preceding heading that looks like an entry title."""
    for tag in HEADING_TAGS:
        h = date_el.find_previous(tag)
        if h:
            t = clean(h.get_text())
            if t and t.lower() not in NON_ENTRY_TITLES and len(t) < 160:
                return t
    return None


def nearest_description(date_el, next_date_el):
    """First meaningful paragraph after the date, bounded by the next entry."""
    for p in date_el.find_all_next("p"):
        if next_date_el is not None and _comes_after(p, next_date_el):
            break
        t = clean(p.get_text())
        if t and "learn more" not in t.lower() and len(t) > 20:
            return t
    return ""


def nearest_link(date_el, next_date_el):
    """First 'Learn more'-style link before the next entry, else any http link."""
    fallback = None
    for a in date_el.find_all_next("a", href=True):
        if next_date_el is not None and _comes_after(a, next_date_el):
            break
        href = a["href"]
        if not href.startswith("http"):
            continue
        if "learn more" in clean(a.get_text()).lower():
            return href
        if fallback is None:
            fallback = href
    return fallback


def _comes_after(a, b) -> bool:
    """True if element a appears at/after element b in document order."""
    for el in b.find_all_next():
        if el is a:
            return True
    return a is b


def parse(html: str):
    soup = BeautifulSoup(html, "lxml")

    # Collect date text nodes in document order.
    date_nodes = []
    for s in soup.find_all(string=DATE_RE):
        if isinstance(s, NavigableString):
            date_nodes.append((s.parent, DATE_RE.match(str(s)).group(1)))

    entries, seen = [], set()
    for i, (date_el, date_str) in enumerate(date_nodes):
        next_el = date_nodes[i + 1][0] if i + 1 < len(date_nodes) else None
        title = nearest_title(date_el)
        if not title:
            continue
        key = (title.lower(), date_str)
        if key in seen:
            continue
        seen.add(key)
        entries.append({
            "title": title,
            "date": date_str,
            "description": nearest_description(date_el, next_el),
            "link": nearest_link(date_el, next_el),
        })

    entries.sort(key=lambda e: e["date"], reverse=True)
    return entries[:MAX_ITEMS]


def build(entries):
    fg = FeedGenerator()
    fg.title(FEED_TITLE)
    fg.link(href=SOURCE_URL, rel="alternate")
    fg.description(FEED_DESC)
    fg.language("en")
    fg.lastBuildDate(datetime.now(timezone.utc))

    for e in entries:  # entries are newest-first; append preserves that order
        fe = fg.add_entry(order="append")
        fe.title(e["title"])
        # Link to the announcement target if present, else the page itself.
        fe.link(href=e["link"] or f"{SOURCE_URL}#all-updates")
        # Stable, unique guid even when entries share/lack a link.
        guid = hashlib.sha1(f'{e["title"]}|{e["date"]}'.encode()).hexdigest()
        fe.guid(guid, permalink=False)
        fe.description(e["description"] or e["title"])
        dt = datetime.strptime(e["date"], "%Y-%m-%d").replace(
            hour=12, tzinfo=timezone.utc
        )
        fe.pubDate(dt)
    return fg


def main():
    html = fetch(SOURCE_URL)
    entries = parse(html)
    if not entries:
        print("ERROR: parsed 0 entries — page structure likely changed.",
              file=sys.stderr)
        sys.exit(1)
    fg = build(entries)
    fg.rss_file("whats-new.xml", pretty=True)

    # Verification output (shows up in the GitHub Actions run log).
    print(f"Parsed {len(entries)} entries. Most recent:")
    for e in entries[:5]:
        link = e["link"] or "(no link)"
        print(f"  {e['date']}  {e['title']}  ->  {link}")


if __name__ == "__main__":
    main()
