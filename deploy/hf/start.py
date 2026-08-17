"""Space entrypoint: fetch the corpus, keep the usage log, serve.

A free Space has no persistent disk. The corpus is pulled from a Dataset repo on
boot, and the usage log is committed back to a private Dataset repo on a timer,
because otherwise every restart silently erases the only record of whether
anybody used this.
"""

from __future__ import annotations

import os
import sys

import uvicorn

CORPUS_REPO = os.environ.get("SMALLGRANTS_CORPUS_REPO", "")
USAGE_REPO = os.environ.get("SMALLGRANTS_USAGE_REPO", "")
DATA = os.environ.get("SMALLGRANTS_DATA", "/home/user/data")


def fetch_corpus() -> None:
    from huggingface_hub import snapshot_download

    if not CORPUS_REPO:
        sys.exit(
            "SMALLGRANTS_CORPUS_REPO is not set. Point it at the Dataset repo "
            "holding smallgrants.duckdb and the embeddings."
        )
    print(f"fetching corpus from {CORPUS_REPO}", flush=True)
    snapshot_download(
        repo_id=CORPUS_REPO,
        repo_type="dataset",
        local_dir=DATA,
        token=os.environ.get("HF_TOKEN"),
    )
    print("corpus ready", flush=True)


def keep_usage_log() -> None:
    """Commit the usage log back on a schedule. Without this the discovery
    numbers live only until the next restart."""
    if not USAGE_REPO:
        print("SMALLGRANTS_USAGE_REPO unset; usage log will not survive a restart",
              flush=True)
        return
    from huggingface_hub import CommitScheduler

    CommitScheduler(
        repo_id=USAGE_REPO,
        repo_type="dataset",
        folder_path=os.path.join(DATA, "usage"),
        path_in_repo="usage",
        every=10,  # minutes
        private=True,
        token=os.environ.get("HF_TOKEN"),
    )
    print(f"usage log will be committed to {USAGE_REPO} every 10 minutes", flush=True)


if __name__ == "__main__":
    fetch_corpus()
    os.makedirs(os.path.join(DATA, "usage"), exist_ok=True)
    keep_usage_log()
    uvicorn.run("smallgrants.app:app", host="0.0.0.0", port=7860)
