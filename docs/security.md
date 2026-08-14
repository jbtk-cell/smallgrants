# Pre-launch security review

Worked through a 20-item launch checklist against the app as it stands. Each row
below was checked by running something, not by reading the code and deciding it
looked fine.

Half the list does not apply, and the reason is worth stating: SmallGrants has no
accounts, no passwords, no cookies, no uploads, and no user-writable data. Every
byte it serves is public IRS filing data that is identical for every visitor. A
whole class of vulnerability is absent because the feature that creates it is
absent. Those rows are marked N/A rather than passed, because skipping a check
and not having the surface are different things.

| # | Item | Status | What was actually checked |
|---|---|---|---|
| 1 | Hide API keys | pass | Only `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` exist, read from the environment and never rendered. No key material in the working tree. |
| 2 | Purge Git secrets | pass | All 143 objects in the full history scanned for Anthropic, AWS, GitHub, Google and PEM key patterns. Nothing. No `.env`, no credentials, no corpus or venv tracked. |
| 3 | Use public DB key | n/a | No hosted database. DuckDB is a local file the server opens read-only; a browser never reaches it. |
| 4 | Enable row-level security | n/a | No per-user rows. Every row is public and the same for everyone. |
| 5 | Encrypt sensitive data | n/a | There is none. The corpus is public federal filings. The usage log is built to hold no personal data at all. |
| 6 | Enforce server-side auth | n/a | No accounts, no login, no privileged action to protect. |
| 7 | Lock record access | n/a | Same as 4. |
| 8 | Block field tampering | pass | Nothing user-writable. Query parameters are parsed through `_int_or_none`, `_flag` and `_clean`, with length caps and an enum whitelist for applicant type. |
| 9 | Secure session cookies | n/a | The site sets no cookies. |
| 10 | Hash passwords | n/a | No passwords. |
| 11 | Rate limit login | **fixed** | There is no login, so the expensive path is search itself. See below. |
| 12 | Add bot protection | partial | Crawlers are detected, excluded from usage figures, and throttled by the search limiter. No CAPTCHA, deliberately. |
| 13 | Parameterize queries | pass | Every user value is bound. The one f-string in SQL sets DuckDB's temp directory from server configuration and cannot be reached from a request. |
| 14 | Validate all input | pass | Length caps, an ascii-digit check that `str.isdigit()` alone fails, and rejection rather than coercion for anything unparseable. |
| 15 | Escape user content | pass | Jinja2 autoescaping, verified end to end against a corpus deliberately poisoned with `<script>` in six fields. |
| 16 | Restrict file uploads | n/a | No uploads. |
| 17 | Trim API responses | pass | No JSON API. The serving corpus carries only the columns the pages render, and errors return a fixed string rather than exception text. |
| 18 | Add security headers | **fixed** | Added `X-Frame-Options`, `Cross-Origin-Opener-Policy` and `Permissions-Policy` alongside the existing CSP, `nosniff` and `Referrer-Policy`. |
| 19 | Force HTTPS | **fixed** | HSTS added, sent only over TLS. `fly.toml` sets `force_https`. |
| 20 | Scan dependencies | pass | All 73 pinned packages queried against the OSV database. No known vulnerabilities. |

## Rate limiting a site with no login

Item 11 assumes a login form. This app does not have one, so applying the item
literally would have produced nothing. The question it is really asking is which
path is expensive enough to be worth abusing.

Here that is search. Each one embeds the query with a local model and scans 8.4M
grant rows, measured at roughly 0.8 seconds of CPU. On the single shared core the
deploy config asks for, that is about one request per second before the site
falls over, and until now nothing stopped one script from taking all of it. The
review endpoint was limited and the expensive one was not.

Searches are now capped at 20 per minute per address, counted in a sliding
window. Throttled requests are logged under their own event so a wave of them
shows up in `smallgrants stats` as throttling rather than as a mysterious drop in
traffic. Idle buckets are swept so a crawl cannot grow the table without bound.

The address is normally the socket peer. Behind a proxy that is the proxy itself,
which would put every visitor in one bucket and lock everyone out during the
first busy minute, so `X-Forwarded-For` is read instead when
`SMALLGRANTS_TRUST_PROXY=1` is set. Reading it unconditionally would be worse
than not limiting at all, since anyone could forge a fresh address per request
and walk straight past the limit. Both directions are pinned by tests.

## HSTS only over TLS

`Strict-Transport-Security` is sent when the request arrived over HTTPS, or when
a proxy says it did. Sending it from a plain-HTTP local run would pin `localhost`
to HTTPS in the developer's browser and quietly break every other project served
from that host.

## What is still open

Bot protection is partial and will stay that way. A CAPTCHA on an open research
tool for volunteer-run nonprofits costs more than it saves, and the rate limit
already removes the incentive. If the site ever gets scraped hard enough to
matter, the fix is a cache in front of search rather than a challenge in front of
users.
