# Publishing

Everything below is prepared. These are the steps that need your account.

## 1. GitHub

`gh` is already authenticated as `jbtk-cell`. One command creates the repository
and pushes:

    cd ~/smallgrants
    gh repo create smallgrants --public --source=. --remote=origin --push \
      --description "An open index of US foundation giving, built from IRS Form 990-PF bulk filings"

Swap `--public` for `--private` to look it over first; `gh repo edit --visibility public`
flips it later.

Before you run it, two things to know:

- Commit history carries three author identities: `jklaus27@students.hopkins.edu`
  and two laptop hostnames. All of it becomes public. That is normal for a
  student project, but it is your name and school address on it permanently.
- No corpus, database, or virtual environment is tracked. 41 files, 1 MB.
  The data rebuilds from the IRS source.

## 2. Zenodo DOI

Zenodo archives GitHub releases automatically, which is the least fragile route
to a citable DOI.

1. Sign in at zenodo.org with GitHub.
2. Under Settings, GitHub, switch `smallgrants` on.
3. Tag and release:

        git tag -a v1.0.0 -m "First public release"
        git push origin v1.0.0
        gh release create v1.0.0 --title "v1.0.0" --generate-notes

Zenodo reads `.zenodo.json` for the metadata and mints the DOI. Add the badge to
the README once you have it.

The switch must be on **before** the release. Zenodo does not archive releases
made earlier.

## 3. JOSS

See `paper/SUBMITTING.md`, which covers what to fill in and where this may fail
review. Do it after the Zenodo DOI exists, since the submission form asks for it.

## What each one gets you

Publishing the repository makes the work inspectable, which matters because the
project asks people to trust claims about their funding prospects. The Zenodo DOI
makes the corpus citable and permanently archived, independent of GitHub. JOSS
would add peer review, and is the only one of the three that can be refused.
