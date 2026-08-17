# Deploying to Hugging Face Spaces

Free, no card. Roughly fifteen minutes, most of it upload time.

## 1. Log in

    ~/smallgrants/.venv/bin/hf auth login

Paste a token from huggingface.co/settings/tokens with **write** access.

## 2. Upload the corpus

The Space downloads the corpus at boot rather than baking 700 MB into the image.

    cd ~/smallgrants
    .venv/bin/smallgrants package                 # -> data/dist, ~735 MB
    .venv/bin/hf repo create smallgrants-corpus --repo-type dataset
    .venv/bin/hf upload smallgrants-corpus data/dist . --repo-type dataset

## 3. Create the private usage repo

    .venv/bin/hf repo create smallgrants-usage --repo-type dataset --private

## 4. Create the Space

    .venv/bin/hf repo create smallgrants --repo-type space --space_sdk docker

Then push the app to it:

    git clone https://huggingface.co/spaces/<owner>/smallgrants /tmp/sg-space
    cp -r src pyproject.toml /tmp/sg-space/
    cp deploy/hf/Dockerfile deploy/hf/start.py deploy/hf/README.md /tmp/sg-space/
    cd /tmp/sg-space && git add -A && git commit -m "SmallGrants" && git push

## 5. Set the variables

Under the Space's Settings, add the variables and the `HF_TOKEN` secret listed in
`deploy/hf/README.md`. The Space rebuilds on save.

## 6. Check it

- `/` returns results for a real query
- `/robots.txt` says `Allow: /`, not `Disallow: /`. If it still says Disallow,
  `SMALLGRANTS_SITE_URL` is unset.
- `/scholarships` loads
- `/sitemap.xml` has absolute URLs on the Space domain

## Notes

Free Spaces sleep after inactivity and cold start takes a couple of minutes,
because the corpus downloads on boot. That is tolerable for launch and is the
first thing to fix if traffic justifies paying for a machine.

Moving to a custom domain later means changing `SMALLGRANTS_SITE_URL` and
redeploying. Nothing else in the app hardcodes a host.
