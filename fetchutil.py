"""Shared HTTP fetching for the changelog feeds, with retry on transient errors.

Both source pages sit behind Cloudflare, which serves 52x edge errors (520
unknown, 521 origin down, 522 origin timed out, 523 unreachable, 524 origin
timeout) whenever the vendor's own backend is briefly unavailable. These clear
on their own: run #106 died on a 522 from okendo.io that was gone by the next
scheduled run.

Retry policy is deliberately narrow:

  * 5xx and connection/read errors are retried. Nothing is wrong on our end and
    the page is very likely to come back within a minute or two.
  * 4xx is NOT retried and raises immediately. A 404 or 403 means the page moved
    or started blocking us, which is a real breakage that should surface on the
    first attempt instead of three minutes later.

Worst case adds ~85s of waiting per feed before giving up, which is well inside
what a 4x-daily job can absorb.
"""

import sys
import time

import requests

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Seconds to wait between attempts. len(RETRY_DELAYS) + 1 == total attempts.
RETRY_DELAYS = (5, 20, 60)
TIMEOUT = 30


def fetch(url, delays=RETRY_DELAYS, timeout=TIMEOUT):
    """GET `url` and return the response body, retrying transient failures."""
    last_error = None

    # A trailing None marks the final attempt, after which we stop waiting.
    for attempt, delay in enumerate((*delays, None), start=1):
        try:
            response = requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", 0)
            if status < 500:
                raise  # real breakage, not a blip - surface it now
            last_error = exc
        except requests.RequestException as exc:
            last_error = exc  # DNS failure, connection reset, read timeout

        if delay is None:
            break
        print(f"  attempt {attempt} failed ({last_error}); "
              f"retrying in {delay}s", file=sys.stderr)
        time.sleep(delay)

    print(f"ERROR: giving up on {url} after {len(delays) + 1} attempts.",
          file=sys.stderr)
    raise last_error
