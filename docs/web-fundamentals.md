# Web fundamentals review

Worked through a 20-item checklist of things that mark a site as thrown together.
Server rendering meant several were already fine, but nine were genuinely missing
and are now fixed.

| # | Item | Before | Now |
|---|---|---|---|
| 1 | Platform-default URL | n/a, not deployed | Set `SMALLGRANTS_SITE_URL` to a real domain at deploy |
| 2 | View source empty | pass | Jinja renders on the server; there is no client framework |
| 3 | No 404 page | **fail**, returned `{"detail":"Not Found"}` | A real page explaining the `/f/<EIN>` URL shape, with a search box |
| 4 | Tab says Vite or React | pass | Never applied |
| 5 | Same title everywhere | **fail** | Per page. A search shows the query, a foundation shows its name |
| 6 | No meta description | **fail** | Per page. Foundation descriptions are written from the filing |
| 7 | No og:image | **fail** | 1200x630 card, with `og:*` and `twitter:card` |
| 8 | No structured data | **fail** | `Dataset` on the index, `Organization` on foundation pages |
| 9 | Multiple H1s | pass | Exactly one per page |
| 10 | No H1 | pass | |
| 11 | No canonical | **fail** | Absolute canonical on every page |
| 12 | No llms.txt | **fail** | `/llms.txt`, including what the data cannot support |
| 13 | AI blocked in robots.txt | n/a, no robots.txt | Present, and AI crawlers are allowed deliberately |
| 14 | No favicon | **fail** | SVG of a ledger with one red mark |
| 15 | No sitemap.xml | **fail** | 28,829 URLs, the foundations that published how to apply |
| 16 | No lang attribute | pass | `<html lang="en">` |
| 17 | Missing alt text | pass | No images in the markup; the one chart carries `role="img"` and a label |
| 18 | Source maps in production | pass | Nothing is bundled |
| 19 | Console full of errors | pass | No JavaScript at all |
| 20 | Enormous JS bundles | pass | Zero bytes of JavaScript |

## Decisions worth recording

**The site refuses crawlers until it has a real address.** `SMALLGRANTS_SITE_URL`
defaults to localhost, and while it is unset `robots.txt` is `Disallow: /` and no
sitemap is advertised. A canonical tag pointing at `127.0.0.1` is worse than no
canonical tag, and a dev box should not invite indexing. Setting the variable at
deploy flips robots, canonicals, sitemap and `og:image` to the real host at once.

**AI crawlers are allowed on purpose.** Blocking them is the default advice, but
people increasingly ask an assistant where to look for funding, and this data
exists to be found. `/llms.txt` goes further and tells an assistant what the data
*cannot* support: not to report a foundation as closed unless it filed the Part XV
declaration, and not to report that it never funds individuals when its recipients
are largely unidentified. Those are the two ways a summarizer would most plausibly
get it wrong.

**The sitemap lists 28,829 of 142,806 foundations**, being those that published
application information and have at least one grant on record. Submitting every
page would mostly submit names with nothing attached.

**Structured data states only filed facts.** Foundation markup carries name, EIN
and address, and nothing scored, ranked or inferred. A test asserts that no score
or rating vocabulary appears in the markup, because schema.org output is read by
machines that will not check whether the number was earned.
