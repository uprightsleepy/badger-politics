"""Isolated monthly CFIS collection; only the later merge updates cumulative state."""

import json
import re

from nightly.archive import pack
from nightly.finance import months_for, validate_month
from nightly.runner import MAX_STATE, Runner


class MonthRunner(Runner):
    def __init__(self, *args, month: str):
        super().__init__(*args)
        if not re.fullmatch(r"20[0-9]{2}-(0[1-9]|1[0-2])", month):
            raise ValueError("Invalid finance month")
        self.month = month

    def log_name(self, stage):
        return f"{stage}-{self.month}"

    def receipt(self, stage):
        return {**super().receipt(stage), "month": self.month}

    def restore(self, stage):
        if stage != "finance-month":
            raise ValueError("Monthly runner requires the finance-month stage")
        self.check_lock()
        doc = self.finance_plan()
        if self.month not in months_for(doc):
            raise ValueError("Finance month is outside this run's frozen plan")
        if doc.get("completed_at"):
            return False
        try:
            self.load_finance_month(doc, self.month)
        except FileNotFoundError:
            pass
        else:
            return False
        source = self.root / "_data/cfis"
        # No cumulative archive is needed: the month collector emits its own
        # registry, and the merge carries the existing archive forward later.
        source.mkdir(parents=True)
        doc.update(stage=stage, month=self.month)
        self.context.write_text(json.dumps(doc), encoding="utf-8")
        return True

    def checkpoint(self, stage):
        doc = self.checkpoint_context(stage)
        if stage != "finance-month" or doc.get("month") != self.month:
            raise ValueError("Monthly checkpoint mismatch")
        source = self.root / "_data/cfis"
        validate_month(source, self.month)
        target = self.scratch / "cfis.tar.gz"
        expanded = pack(source, "cfis", target)
        if target.stat().st_size > MAX_STATE:
            raise ValueError("Monthly finance bundle exceeds the source budget")
        obj = self.run_prefix + f"months/{self.month}-{self.execution}.tar.gz"
        ref = {**self.store.upload(obj, target), "expanded_bytes": expanded}
        target.unlink()
        receipt = {key: doc[key] for key in (
            "version", "run_id", "revision", "base_generation", "finance_as_of", "stage", "month",
        )}
        receipt["bundle"] = ref
        self.store.put_json(self.run_prefix + f"months/{self.month}.json", receipt, self.scratch)
