"""Shared first-seen timestamp tracking for the changelog feeds.

Why this exists: Slack's RSS app decides what's new by comparing each item's
pubDate against a stored bookmark (the date of the last item it retrieved). It
does NOT dedupe by guid. So if a newly published item carries a date Slack has
already bookmarked, that item is silently never posted.

Both source pages hit this. Okendo publishes no per-entry dates at all (entries
sit under month headers), and Klaviyo frequently ships several entries sharing
one date. Either way, a new entry can land on an already-bookmarked date.

Fix: use the moment THIS script first saw an item as its pubDate.
  - On the initial seeding run there is no history, so fall back to a
    content-derived date. That keeps the backfill looking historically correct
    instead of stamping 140 items with the same "now".
  - After that, any newly discovered item gets the current build time, which is
    always later than any bookmark a reader holds.

State lives in a small JSON file committed alongside the XML.
"""

import json
import os
from datetime import datetime, timedelta, timezone


def load(path):
    """Return (state, seeding). seeding is True when there's no usable history."""
    if not os.path.exists(path):
        return {}, True
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        # Corrupt state is better re-seeded than crashed on.
        return {}, True
    state = {}
    for guid, iso in (raw or {}).items():
        try:
            dt = datetime.fromisoformat(iso)
        except (TypeError, ValueError):
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        state[guid] = dt
    return state, (not state)


def save(path, state):
    data = {
        guid: dt.astimezone(timezone.utc).isoformat()
        for guid, dt in state.items()
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
        fh.write("\n")


def resolve(state, seeding, guid, content_dt, new_rank, now):
    """Return the pubDate for one item, recording it on first sight.

    content_dt : best-effort date from the page; used only while seeding
    new_rank   : 0-based position among items new in THIS run, newest first,
                 so the newest new item gets the latest timestamp
    """
    if guid in state:
        return state[guid]
    dt = content_dt if seeding else now - timedelta(seconds=new_rank)
    state[guid] = dt
    return dt


def prune(state, live_guids, keep=500):
    """Drop history for items that have aged off the page, so the file can't
    grow without bound. Keeps the newest `keep` entries plus anything live."""
    if len(state) <= keep:
        return state
    live = set(live_guids)
    ordered = sorted(state.items(), key=lambda kv: kv[1], reverse=True)
    kept = {g: d for g, d in ordered[:keep]}
    kept.update({g: state[g] for g in live if g in state})
    return kept
