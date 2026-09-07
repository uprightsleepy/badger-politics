"""CLI boundaries let Actions refresh OIDC credentials after long collection."""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from nightly.finance import months_for
from nightly.month import MonthRunner
from nightly.runner import Runner, seed
from nightly.stages import STAGES, commands
from nightly.storage import GCS


def run_stage(runner: Runner, stage: str, cycle: str):
    if not re.fullmatch(r"20[0-9]{2}", cycle):
        raise ValueError("CYCLE must be a four-digit election year")
    context = json.loads(runner.context.read_text(encoding="utf-8"))
    runner.same_run(context)
    if context.get("stage") != stage:
        raise ValueError("Restore this stage before running it")
    success = runner.scratch / "success.json"
    success.unlink(missing_ok=True)
    runner.root.parent.joinpath("data").mkdir(exist_ok=True)
    started = time.monotonic()
    # Subprocess output can contain private source data. Keep it off public
    # Actions logs. It is uploaded to the private checkpoint prefix separately.
    with (runner.scratch / f"{runner.log_name(stage)}.log").open("wb") as log:
        for command in commands(stage, runner.root, cycle, context):
            command_started = time.monotonic()
            print(f"Running {command[0]} ({runner.log_name(stage)})", flush=True)
            remaining = 5 * 3600 - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("Stage reached its five-hour collection budget")
            subprocess.run([sys.executable, "-u", "-m", *command], cwd=runner.root,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=remaining)
            elapsed = time.monotonic() - command_started
            print(f"Completed {command[0]} in {elapsed:.0f}s", flush=True)
    success.write_text(json.dumps(runner.receipt(stage)), encoding="utf-8")
    print(f"Stage completed in {time.monotonic() - started:.0f}s", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("seed", "acquire", "restore", "run", "checkpoint",
                                       "logs", "publish", "release", "finance-plan"))
    ap.add_argument("--stage", choices=(*STAGES, "finance-month"))
    ap.add_argument("--month", default=os.environ.get("FINANCE_MONTH", ""))
    ap.add_argument("--bucket", default="badgerpolitics-prod-snapshots")
    ap.add_argument("--revision", default=os.environ.get("GITHUB_SHA", ""))
    ap.add_argument("--run-id", default=os.environ.get("NIGHTLY_RUN_ID", ""))
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.action in ("restore", "run", "checkpoint", "logs") and not args.stage:
        ap.error("This action requires --stage")
    # The pure execution step needs no cloud credentials in its process.
    store = None if args.action == "run" else GCS(args.bucket)
    if args.action == "seed":
        seed(store, root, root.parent / ".private/nightly-seed", args.revision)
        print("Private source seed created")
        return 0
    execution = f"{os.environ.get('GITHUB_RUN_ID', '')}-{os.environ.get('GITHUB_RUN_ATTEMPT', '')}"
    if args.month and args.stage != "finance-month":
        ap.error("--month is only valid for finance-month")
    if args.stage == "finance-month":
        runner = MonthRunner(store, root, args.run_id, args.revision, execution, month=args.month)
    else:
        runner = Runner(store, root, args.run_id, args.revision, execution)
    if args.action == "acquire":
        runner.acquire()
    elif args.action == "release":
        runner.release()
    elif args.action == "restore":
        needed = runner.restore(args.stage)
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with Path(output).open("a", encoding="utf-8") as stream:
                stream.write(f"needed={'true' if needed else 'false'}\n")
        print("Restored stage inputs" if needed else "Using completed checkpoint")
    elif args.action == "run":
        run_stage(runner, args.stage, os.environ.get("CYCLE", "2026"))
    elif args.action == "checkpoint":
        runner.checkpoint(args.stage)
        print("Private checkpoint saved")
    elif args.action == "publish":
        runner.publish()
        print("Validated snapshot published; hosting requires a separate release")
    elif args.action == "finance-plan":
        months = months_for(runner.finance_plan())
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with Path(output).open("a", encoding="utf-8") as stream:
                stream.write(f"months={json.dumps(months)}\n")
        print(f"Planned {len(months)} sequential monthly jobs", flush=True)
    elif args.action == "logs":
        label = runner.log_name(args.stage)
        path = runner.scratch / f"{label}.log"
        if path.exists():
            # Bound failure diagnostics; they remain private and expire with checkpoints.
            limit = 10 * 1024**2
            tail = runner.scratch / "diagnostic.log"
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - limit))
                tail.write_bytes(stream.read(limit))
            runner.check_lock()
            store.upload(runner.run_prefix + f"{label}-{execution}.log", tail)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        # No raw subprocess output, credentials, HTTP response bodies, or source records.
        print(f"Nightly parser stopped: {error}", file=sys.stderr)
        sys.exit(1)
