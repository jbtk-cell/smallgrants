# Outreach targets

The plan is a small number of personalized emails to organizations that can put
this in front of their own members, rather than a large number of cold emails to
the members directly. Roughly 30 to 50 messages, each written for its recipient.

That choice removes a whole category of problem. Bulk commercial email in the US
has to carry accurate sender identification, a physical postal address and a way
to opt out, and a new domain sending 150 cold messages mostly lands in spam and
burns its own reputation doing it. Forty personalized emails from a named person
are ordinary correspondence and none of that applies.

## Tag every link

Send each recipient a link with `?from=<tag>` on it:

    https://<site>/?from=mdnp
    https://<site>/scholarships?from=reddit-scholarships

`smallgrants stats` then reports which door people came through. Without it the
outcome is "we emailed forty places and got some traffic", which tells you
nothing about where to spend the next round. The tag records only the door, never
anything about the person.

## Tier 1: verified, and worth doing first

**Maryland Nonprofits** (marylandnonprofits.org). A network of 1,800+ Maryland
nonprofits that runs a **weekly member newsletter carrying funding alerts**. That
newsletter is the single best placement on this list: it is already the thing
members open to find money, and you are local to it. Tag: `mdnp`.

**Johns Hopkins SOURCE** (source.jhu.edu). The community engagement centre for
the Public Health, Nursing and Medicine schools, partnered with **more than 100
Baltimore community-based organizations**. You are a Hopkins student, which makes
this the warmest introduction available to you. Tag: `jhu-source`.

**Maryland Philanthropy Network** (marylandphilanthropy.org). An association of
funders rather than grantseekers, so the pitch is different: not "use this to find
money" but "here is a free tool your grantees can use, built from public
filings". Funders recommending it to applicants carries more weight than anything
you can say yourself. Tag: `mpn`.

## Tier 2: the state associations

The **National Council of Nonprofits** network has state associations in 47
states and DC, together connecting **more than 32,000 charitable organizations**.
Each one has a membership newsletter. This is the highest-leverage list on the
page and it is 48 emails.

The directory is at `councilofnonprofits.org/find-your-state-association`. It
blocks automated fetching, so the list has to be copied out by hand in a browser;
it is worth the twenty minutes. Work down it by state, tagging each `nc-<state>`,
for example `nc-mn`.

Start with five, see what comes back, and use the replies to rewrite the message
before sending the other forty-three. The first version of any outreach email is
wrong in a way only a recipient can tell you.

## Tier 3: fiscal sponsors

These are the organizations whose members are structurally locked out of every
free tier, because Candid's Go for Gold and the library programme both need a
501(c)(3) profile the project cannot hold. The pitch writes itself.

**HCB, formerly Hack Club Bank** (hackclub.com/fiscal-sponsorship). Fiscal
sponsorship for thousands of teen and student-led projects, with an active online
community. Post as a participant rather than emailing as a vendor. Tag: `hcb`.

**Fractured Atlas** (fracturedatlas.org). Fiscal sponsorship for artists and arts
projects. Tag: `fractured-atlas`.

Search for others by phrase: "fiscal sponsorship" plus a field, or the
Social Impact Commons and National Network of Fiscal Sponsors directories.

## Tier 4: libraries

Funding Information Network partner libraries already offer free Foundation
Directory access, so they are not competing with you, they are the people who
answer "I need to find grants" for walk-ins all day. A librarian who likes this
will mention it for years. Find them through Candid's network page and start with
your own state. Tag: `lib-<state>`.

## Who not to email

**Foundations.** They are the subject of the data, not the audience for it.
Promoting a tool that indexes their giving directly to them invites exactly one
outcome worth avoiding, which is a foundation deciding to publish less. The
Maryland Philanthropy Network approach above is different: it reaches funders
through their own association, framed as a resource for their applicants.

## What to watch afterwards

    smallgrants stats

Three lines matter more than visit counts. **Where they came from** tells you
which tier is worth repeating. **Searches that returned nothing** says the corpus
is failing people who did arrive, which is a product finding. **Funders reported
as new to the person who found them** is the only number that supports a claim
about impact, and it exists because the site asks.
