# Changelog Feeds

RSS feeds for vendor changelog pages that don't publish their own.

| Source | Output |
|---|---|
| [Klaviyo — What's New](https://www.klaviyo.com/whats-new) | `whats-new.xml` |
| [Okendo — Product Releases](https://okendo.io/product-releases/) | `okendo-releases.xml` |

A GitHub Action (`.github/workflows/build-feeds.yml`) rebuilds both daily at
13:00 UTC and commits the XML when it changes.

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
- **Klaviyo** entries are anchored on the `YYYY-MM-DD` date string, not CSS
  classes. Entries without a "Learn more" link still appear (GUIDs are
  content-hashed, so they never collide).
- **Okendo** has no per-entry dates — entries are grouped under month headers,
  so pubDate is month-level and ordering follows the page. Items are titled
  `[Topic] Title`.
- **Okendo topic filter:** set `TOPICS` near the top of `build_feed_okendo.py`
  to restrict by topic name, e.g. `TOPICS = {"reviews", "loyalty"}`. Empty set
  means all topics.
