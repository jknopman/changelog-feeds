#!/usr/bin/env python3
"""
Generate an RSS 2.0 feed from Klaviyo's "What's New" page.

Structure, verified against the live DOM: every changelog entry is an
<article class="card"> containing

    h3.title          the entry title
    time.date         YYYY-MM-DD
    div.description   the blurb
    a[href]           optional "Learn more" target

The marketing "Highlights" blocks at the top of the page do not use
article.card, so this selector needs no extra exclusion list.

Two non-obvious details:

  * Klaviyo publishes no per-entry permalinks. Several entries share a single
    help-centre article and ~9% have no link at all, so a short fragment
    derived from the guid is appended to every link. Without it, readers that
    deduplicate by URL (RSS.app does) silently merge distinct entries and drop
    the newest one.
  * pubDate is when this script first saw an entry, not the printed date.
    See feedstate.py for why that matters.
"""

import hashlib
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

import feedstate

SOURCE_URL = "https://www.klaviyo.com/whats-new"
FEED_TITLE = "Klaviyo - What's New"
FEED_DESC = "Latest Klaviyo product updates and releases (unofficial feed)."
STATE_PATH = "seen-klaviyo.json"
MAX_ITEMS = 60
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def fetch(url):
    headers = {"User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _field(card, selector):
    el = card.select_one(selector)
    return clean(el.get_text()) if el else ""


def parse(html):
    soup = BeautifulSoup(html, "lxml")
    entries, seen = [], set()

    for card in soup.select("article.card"):
        date = _field(card, ".date")
        if not DATE_RE.match(date):
            continue  # not a dated changelog entry
        title = _field(card, ".title")
        if not title:
            continue
        key = (title.lower(), date)
        if key in seen:
            continue
        seen.add(key)
        anchor = card.select_one("a[href]")
        href = anchor["href"] if anchor else None
        if href and not href.startswith("http"):
            href = None
        entries.append({
            "title": title,
            "date": date,
            "description": _field(card, ".description"),
            "link": href,
        })

    entries.sort(key=lambda e: e["date"], reverse=True)
    return entries[:MAX_ITEMS]


def unique_link(href, guid):
    """Give every item a distinct URL. Klaviyo reuses help-centre articles
    across entries and omits links entirely on some, so without this readers
    that dedupe by URL collapse separate entries into one."""
    base = (href or f"{SOURCE_URL}#all-updates").split("#")[0]
    return f"{base}#klv-{guid[:8]}"


def titled_body(entry):
    """Description text that leads with the entry title, without doubling it up
    when the description is missing or already starts with the title."""
    body = entry.get("description") or ""
    title = entry["title"]
    if not body:
        return title
    if body.startswith(title):
        return body
    return f"{title} \u2014 {body}"


def build(entries):
    fg = FeedGenerator()
    fg.title(FEED_TITLE)
    fg.link(href=SOURCE_URL, rel="alternate")
    fg.description(FEED_DESC)
    fg.language("en")
    fg.lastBuildDate(datetime.now(timezone.utc))

    state, seeding = feedstate.load(STATE_PATH)
    now = datetime.now(timezone.utc)
    new_rank = 0
    guids = []

    for e in entries:  # newest-first; append preserves that order
        guid = hashlib.sha1(f'{e["title"]}|{e["date"]}'.encode()).hexdigest()
        guids.append(guid)

        fe = fg.add_entry(order="append")
        fe.title(e["title"])
        fe.link(href=unique_link(e["link"], guid))
        fe.guid(guid, permalink=False)
        # Lead the description with the real title. Some readers (RSS.app)
        # overwrite <title> with the title of the linked help-centre article,
        # which collapses several entries to a generic name like "Composer";
        # repeating it here keeps each item identifiable regardless.
        # Keep Klaviyo's own date visible, since pubDate no longer carries it.
        fe.description(f'{titled_body(e)}\n\n(Published {e["date"]})')

        content_dt = datetime.strptime(e["date"], "%Y-%m-%d").replace(
            hour=12, tzinfo=timezone.utc)
        is_new = guid not in state
        fe.pubDate(
            feedstate.resolve(state, seeding, guid, content_dt, new_rank, now))
        if is_new and not seeding:
            new_rank += 1

    feedstate.save(STATE_PATH, feedstate.prune(state, guids))
    return fg


def main():
    entries = parse(fetch(SOURCE_URL))
    if not entries:
        print("ERROR: parsed 0 entries - page structure likely changed.",
              file=sys.stderr)
        sys.exit(1)
    build(entries).rss_file("whats-new.xml", pretty=True)

    no_desc = sum(1 for e in entries if not e["description"])
    no_link = sum(1 for e in entries if not e["link"])
    print(f"Parsed {len(entries)} entries "
          f"({no_desc} missing description, {no_link} missing link). "
          f"Most recent:")
    for e in entries[:5]:
        print(f"  {e['date']}  {e['title']}")
        print(f"      {(e['description'] or '(none)')[:70]}")


if __name__ == "__main__":
    main()
