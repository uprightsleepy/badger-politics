"""Derive bills.status from the action history.

Precedence (first match wins):
  enacted       became-law / executive-signature present. Wisconsin partial
                vetoes (executive-veto-line-item) accompany a signed act, so
                enacted outranks vetoed.
  vetoed        executive-veto present and the bill never became law. Failed
                veto overrides ("... Joint Rule 82") stay vetoed.
  failed_sjr1   "Failed to pass pursuant to Senate Joint Resolution 1" —
                the end-of-biennium death of everything still pending.
  passed        passage actions in both chambers.
  passed_chamber passage action in exactly one chamber.
  in_committee  referred to committee, nothing further.
  introduced    everything else.
"""

from __future__ import annotations

import re

# All three docs.legis phrasings of the end-of-biennium death: bills in
# committee "fail to pass", bills awaiting the second chamber "fail to
# concur in", resolutions "fail to adopt".
SJR1_RE = re.compile(
    r"failed to (pass|concur in|adopt) pursuant to senate joint resolution 1", re.I
)

ENACTED = {"became-law", "executive-signature"}
VETOED = {"executive-veto", "executive-veto-line-item"}


def _classes(action: dict) -> set[str]:
    raw = action.get("classification") or []
    if isinstance(raw, str):  # comma-joined (database form)
        raw = [c for c in raw.split(",") if c]
    return set(raw)


def derive_status(actions: list[dict], classification: str | None = None) -> str:
    all_classes: set[str] = set()
    passage_chambers: set[str] = set()
    sjr1 = False
    for action in actions:
        classes = _classes(action)
        all_classes |= classes
        if "passage" in classes:
            passage_chambers.add(action.get("chamber") or "?")
        if SJR1_RE.search(action.get("description") or ""):
            sjr1 = True

    # resolutions never go to the governor: final legislative approval is
    # adoption, never enactment, a veto, or "passed, awaiting signature"
    is_resolution = classification is not None and "resolution" in classification

    if all_classes & ENACTED:
        return "adopted" if is_resolution else "enacted"
    if all_classes & VETOED:
        return "vetoed"
    if sjr1:
        return "failed_sjr1"
    if len(passage_chambers) >= 2:
        return "adopted" if is_resolution else "passed"
    if len(passage_chambers) == 1:
        return "passed_chamber"
    if "referral-committee" in all_classes:
        return "in_committee"
    return "introduced"
