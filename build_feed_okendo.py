#!/usr/bin/env python3
"""
Generate an RSS 2.0 feed from Okendo's "Product Releases" changelog.

Okendo's page has no per-entry dates (entries sit under month headers) and no
clean item container, so we anchor on two stable signals: the month headers
("June 2026") and the per-entry CTA link ("Explore this feature" / "Learn More"
/ "View documentation"). Parsing is bounded to the region after the real
"Changelog" heading, which excludes the "Recent highlights" marketing cards.
"""

import hashlib
import re
import sys
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://okendo.io/product-releases/"
FEED_TITLE = "Okendo - Product Releases"
FEED_DESC = "New features and updates to Okendo (unofficial feed)."
MAX_ITEMS = 80

# Optional: restrict to specific topics by NAME (case-insensitive). Empty = all.
# e.g. {"reviews", "loyalty", "okendo platform"}
TOPICS = set()

MONTH_RE = re.compile(
    r"^(january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\s+(\d{4})$", re.I)
CTA_RE = re.compile(
    r"^(explore this feature|explore the features|learn more|"
    r"view documentation)$", re.I)
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}
# Short badge lines that are metadata, not titles/descriptions.
KNOWN_RELEASE_TYPES = {
    "enhancement", "new", "beta", "general availability (ga)", "ga",
    "fix", "improvement", "new feature", "coming soon",
}


def fetch(url):
    headers = {"User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def clean(t):
    return re.sub(r"\s+", " ", t or "").strip()


def tokenize(soup):
    """Flatten the document into ordered tokens: ('month', s) | ('cta', text, href)
    | ('text', s). Links are emitted as their own token so their inner text is
    not double-counted."""
    body = soup.body or soup
    tokens = []
    for el in body.descendants:
        name = getattr(el, "name", None)
        if name == "a":
            txt = clean(el.get_text())
            href = el.get("href", "")
            if txt:
                if CTA_RE.match(txt):
                    tokens.append(("cta", txt, href))
                else:
                    tokens.append(("text", txt))
        elif name is None:  # NavigableString
            # Skip strings that live inside an <a> (already captured above).
            if el.find_parent("a"):
                continue
            s = clean(str(el))
            if s:
                tokens.append(("month", s) if MONTH_RE.match(s) else ("text", s))
    return tokens


def parse(html):
    soup = BeautifulSoup(html, "lxml")
    tokens = tokenize(soup)

    # Start after the LAST "Changelog" heading (skips nav + Recent highlights).
    start = 0
    for i, tok in enumerate(tokens):
        if tok[0] == "text" and tok[1].lower() == "changelog":
            start = i + 1
    tokens = tokens[start:]

    entries = []
    seen = set()
    current_month = None
    buf = []  # accumulates text lines since last CTA / month header
    for tok in tokens:
        if tok[0] == "month":
            current_month = tok[1]
            buf = []  # month header is a divider
        elif tok[0] == "text":
            # Drop filter-UI labels and empty noise.
            if tok[1].lower() in {"release type", "topic"}:
                continue
            buf.append(tok[1])
        elif tok[0] == "cta":
            if len(buf) >= 2 and current_month:
                description = buf[-1]
                title = buf[-2]
                meta = [b for b in buf[:-2] if b]
                topic = meta[-1] if meta else None
                rtype = " / ".join(meta[:-1]) if len(meta) >= 2 else None
                key = (title.lower(), current_month)
                if title and key not in seen:
                    seen.add(key)
                    entries.append({
                        "title": title, "description": description,
                        "month": current_month, "topic": topic,
                        "rtype": rtype, "link": tok[2] or SOURCE_URL})
            buf = []

    if TOPICS:
        entries = [e for e in entries
                   if (e["topic"] or "").lower() in TOPICS]
    return entries[:MAX_ITEMS]


def month_base(month_str):
    name, year = month_str.split()
    return datetime(int(year), MONTHS[name.lower()], 1, 12, tzinfo=timezone.utc)


def build(entries):
    from feedgen.feed import FeedGenerator
    fg = FeedGenerator()
    fg.title(FEED_TITLE)
    fg.link(href=SOURCE_URL, rel="alternate")
    fg.description(FEED_DESC)
    fg.language("en")
    fg.lastBuildDate(datetime.now(timezone.utc))

    # Page lists newest-first; keep that order and give each item a strictly
    # decreasing timestamp so readers sort it the same way.
    for i, e in enumerate(entries):
        fe = fg.add_entry(order="append")
        prefix = f"[{e['topic']}] " if e["topic"] else ""
        fe.title(prefix + e["title"])
        fe.link(href=e["link"])
        guid = hashlib.sha1(
            (e["title"] + "|" + e["month"]).encode()).hexdigest()
        fe.guid(guid, permalink=False)
        tag = " / ".join(x for x in (e["rtype"], e["topic"]) if x)
        desc = e["description"] + (f"\n\n({tag} - {e['month']})" if tag else "")
        fe.description(desc)
        fe.pubDate(month_base(e["month"]) - timedelta(minutes=i))
    return fg


def main():
    entries = parse(fetch(SOURCE_URL))
    if not entries:
        print("ERROR: parsed 0 entries - page structure likely changed.",
              file=sys.stderr)
        sys.exit(1)
    build(entries).rss_file("okendo-releases.xml", pretty=True)
    print(f"Parsed {len(entries)} entries. Most recent:")
    for e in entries[:6]:
        print(f"  {e['month']:<14} [{e['topic']}] {e['title']}")


if __name__ == "__main__":
    main()
