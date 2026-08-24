# Changelog Feeds

RSS feeds for vendor changelog pages that don't publish their own.

| Source | Output |
|---|---|
| [Klaviyo — What's New](https://www.klaviyo.com/whats-new) | `whats-new.xml` |
| [Okendo — Product Releases](https://okendo.io/product-releases/) | `okendo-releases.xml` |

A GitHub Action (`.github/workflows/build-feeds.yml`) rebuilds both 4x daily
(11:00, 15:00, 19:00, 23:00 UTC) and commits the XML when it changes.

## Feed URLs

```
https://raw.githubusercontent.com/jknopman/changelog-feeds/main/whats-new.xml
https://raw.githubusercontent.com/jknopman/changelog-feeds/main/okendo-releases.xml
```

Add each to RSS.app, or subscribe directly in Slack:

```
/feed subscribe <feed-url>
```

Because these are already valid RSS, RSS.app ingests them directly instead of
trying to auto-detect a feed from the vendor HTML — which is the step that fails
on both source pages.

## Notes

- **Verify after a run:** each script prints `Parsed N entries` to the Action
  log. If it prints `Parsed 0 entries` the job fails loudly — that means the
  vendor changed their page markup and the parser needs re-pointing.
- **The two feeds fail independently.** Each build step is `continue-on-error`,
  so one vendor being down no longer discards the other vendor's output — the
  commit step still runs, and a failed script leaves its XML and state file
  untouched. The `Report build failures` step re-fails the job afterwards, so a
  red run still means something is genuinely broken.
- **Transient outages are retried.** `fetchutil.fetch` retries 5xx and
  connection errors 4 times (5s / 20s / 60s backoff). Cloudflare 52x errors from
  either vendor usually clear within seconds. A 4xx is *not* retried — a 404
  means the page actually moved and should surface immediately.
- **Klaviyo** entries are anchored on the `YYYY-MM-DD` date string, not CSS
  classes. Entries without a "Learn more" link still appear (GUIDs are
  content-hashed, so they never collide).
- **Okendo** has no per-entry dates — entries are grouped under month headers,
  so pubDate is month-level and ordering follows the page. Items are titled
  `[Topic] Title`.
- **Okendo topic filter:** set `TOPICS` near the top of `build_feed_okendo.py`
  to restrict by topic name, e.g. `TOPICS = {"reviews", "loyalty"}`. Empty set
  means all topics.
