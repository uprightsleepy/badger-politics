"""Make cloud-writing run.sh executions participate in the nightly lease."""

import argparse
import re
from pathlib import Path

from nightly.runner import LOCK
from nightly.storage import GCS, Conflict


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("acquire", "release"))
    ap.add_argument("--owner", required=True)
    ap.add_argument("--bucket", required=True)
    args = ap.parse_args()
    if not re.fullmatch(r"local-[0-9a-f]{32}", args.owner):
        ap.error("Invalid local lock owner")
    store = GCS(args.bucket)
    if args.action == "acquire":
        scratch = Path(__file__).resolve().parents[2] / ".private/local-parser" / args.owner
        scratch.mkdir(parents=True, exist_ok=True)
        try:
            store.put_json(LOCK, {"execution": args.owner}, scratch)
        except Conflict:
            raise SystemExit("Another parser owns the lock; wait for it to finish") from None
    else:
        lock, generation = store.read_json(LOCK)
        if lock.get("execution") != args.owner:
            raise SystemExit("Lock owner changed; refusing to release another parser's lock")
        store.delete(LOCK, generation)


if __name__ == "__main__":
    main()
