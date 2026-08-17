# Outreach

Drafts to send once the site is live. Replace `LINK` with the real URL.

Two rules that matter more than the wording. **Post where you actually belong**,
which for you means Hopkins and Baltimore first, because a stranger dropping a
link in a community they have never participated in gets removed regardless of
how good the thing is. And **lead with the limitation**. Every one of these
audiences has been sold a grant database before. Saying what it cannot do is the
fastest way to be believed about what it can.

Do not post the same text in five places on the same day. Pick one, watch what
people ask, and let the questions rewrite the next one.

---

## r/scholarships

Largest audience, and the one currently served worst.

> **I built a free search over the IRS records of foundations that pay
> scholarships directly to students**
>
> Every private foundation in the US files a tax return listing every grant it
> paid, including money paid to individual people. The IRS publishes all of it.
> It is close to unusable in raw form, so I parsed it: 8.4 million grants from
> 142,806 foundations.
>
> You can search it by what you are studying and your state. It shows you the
> actual grants each foundation paid, with amounts and years, so you can see
> whether they fund people like you before you spend an evening on an
> application.
>
> There are 4,167 foundations in there that mostly fund individuals, never filed
> that they refuse unsolicited requests, and published how to apply.
>
> What it will not do: it does not have deadlines for most of them, it cannot
> tell you if you are eligible, and filings run a year or two behind, so a fund
> could have changed or closed. It is a way to find candidates from the public
> record, not a scholarship list. Free, no account, no ads. Source is public.
>
> LINK

Answer every eligibility question with what the filing actually says. Do not
guess.

---

## r/nonprofit

Read the rules first; some subreddits require a flair or restrict self-promotion
to certain days.

> **Free funder search built from 990-PF filings, for orgs that cannot get Candid
> free**
>
> If you are a registered 501(c)(3) under $1M in revenue, stop reading and go get
> Candid Premium free through their Go for Gold program, or use a Funding
> Information Network library. Those are better products than mine.
>
> This is for everyone that route excludes: fiscally sponsored projects, student
> groups, unincorporated volunteer groups, mutual aid, anyone without a nonprofit
> profile of their own.
>
> It searches 8.4 million grants that foundations reported paying, and ranks
> funders by what they actually paid for, where they paid it, and whether your
> ask fits the size of grant they write. Then it reads the foundation's own
> filing against your specific ask and tells you the reasons not to bother:
> your amount exceeds the largest grant they have ever made, their stated
> restrictions name a state that is not yours, they filed that they take no
> unsolicited requests.
>
> Known limits, up front: 40% of grant recipients could not be matched to a known
> organization, so cause profiles are partial. Filings lag by a year or more.
> 990-PF only, so community foundations are absent entirely.
>
> LINK, source and the full validation record on GitHub.

---

## Hack Club / HCB community

Fiscally sponsored teen and student-led projects: exactly the group locked out of
every free tier, and unusually concentrated. Post as a member, not an outsider.

> Anyone here chasing grant money for their HCB project: I made a search over the
> IRS filings where foundations list every grant they paid. You can search by what
> your project does and your state and see who actually funded similar things,
> with real amounts.
>
> The useful part for us is the size filter. Most of these are small foundations
> writing $2,500 cheques, which is the range we are in, and it tells you when your
> ask is bigger than anything they have ever given.
>
> Free, no signup, open source. LINK

---

## Fractured Atlas / arts fiscal sponsorship

> Fiscally sponsored arts projects cannot get the free Candid tier, because it
> needs a 501(c)(3) profile of your own.
>
> I built a free search over the IRS filings instead. It covers 8.4 million grants
> foundations reported paying, and it will show you which ones funded arts work in
> your state, at what size, with the actual grant lines from their return.
>
> It is honest about what it does not know: 40% of recipients could not be
> identified, and filings run a year behind. LINK

---

## Hopkins SOURCE and student groups

Send as email, not a post. This is the one where being a student is the asset.

> Subject: A free funder-search tool I built, for the community orgs you work with
>
> I am a Hopkins student and I built a free tool that searches the IRS filings
> where every private foundation lists the grants it paid: 8.4 million grants,
> 142,806 foundations.
>
> It is aimed at organizations that cannot use the paid databases and do not
> qualify for the free tiers, which need a 501(c)(3) and a maintained public
> profile. Student groups and small volunteer organizations have neither.
>
> You describe what you do, and it returns funders that have actually paid for
> similar work nearby, at a similar size, showing the real grant lines. It also
> reads a foundation's filing against a specific ask and gives reasons not to
> apply, which saves more time than the search does.
>
> No cost, no account, and the source and methodology are public. If it is useful
> to the organizations you work with I would rather hear what is wrong with it
> than have it quietly ignored.

---

## Data Is Plural

Jeremy Singer-Vine's newsletter, submitted through the form at
data-is-plural.com. Reaches a large number of journalists and researchers. Pitch
the dataset, not the website.

> **US private foundation grants, parsed from 990-PF bulk filings.** Every US
> private foundation files a Form 990-PF listing each grant it paid: recipient,
> city, state, stated purpose and amount. The IRS publishes these as bulk XML,
> which is why they are rarely used. This project parses filing years 2022 to
> 2026 into 8,388,280 grant records from 142,806 foundations, deduplicates
> double-filed returns, and matches recipients against the IRS Business Master
> File to recover activity codes. It documents what it cannot do: 40.2% of
> recipients remain unidentified, and five of the 49 source archives use a
> compression format most tools report as corrupt. Code MIT, corpus rebuildable
> from source.

---

## Show HN

Expect scrutiny rather than users, which is the point: it is where the data work
gets checked.

> **Show HN: SmallGrants – search 8.4M foundation grants from IRS 990-PF filings**
>
> Foundations report every grant they pay on their tax return. The IRS publishes
> the filings as bulk XML across 49 zip archives, five of which use deflate64 and
> are reported as corrupt by most tools, which is a decent summary of why the data
> is not widely used.
>
> The part I would most like torn apart is the validation. I proposed a signal,
> grantee turnover as a proxy for whether a foundation takes new applicants,
> tested it against the 70% of foundations that declare their own status, found
> it real but weak (Cohen's d = 0.286), and cut its weight rather than shipping
> it as if it worked. That write-up, and the defects found while checking, are in
> docs/validation.md.

---

## What to watch after posting

`smallgrants stats` answers two questions no visit counter does. **Searches that
returned nothing** tells you the corpus is failing people who arrived, which is
worth more than knowing how many arrived. **Funders reported as new to the
person who found them** is the only number that supports any claim of impact.

If searches return nothing often, the answer is usually the state filter, which
is strict on purpose. That is a product finding, not a marketing one.
