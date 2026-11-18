"""Compare two ledger.json reports without rerunning analysis."""

from collections.abc import Iterator
from html import escape
from pathlib import Path

from pydantic import BaseModel

from testledger.models import Verdict


class SnapshotSummary(BaseModel):
    total_cost_usd: float
    total_value_usd: float
    net_usd: float
    portfolio_roi: float | None
    regressions_caught: int
    verdicts: dict[str, int]


class SnapshotAccount(BaseModel):
    test_id: str
    verdict: str
    net_usd: float


class Snapshot(BaseModel):
    summary: SnapshotSummary
    assumptions: dict[str, int | float | dict[str, int | float]]
    accounts: list[SnapshotAccount]

    @classmethod
    def read(cls, path: Path) -> "Snapshot":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


def _change(old: float | int | None, new: float | int | None) -> dict:
    delta = round(new - old, 4) if old is not None and new is not None else None
    return {"old": old, "new": new, "delta": delta}


def _assumptions(values: dict) -> dict:
    threshold_values = values.get("thresholds", {})
    if not isinstance(threshold_values, dict):
        return values
    thresholds = {f"thresholds.{key}": value for key, value in threshold_values.items()}
    return {key: value for key, value in values.items() if key != "thresholds"} | thresholds


def compare_ledgers(old: Snapshot, new: Snapshot) -> dict:
    metrics = ("total_cost_usd", "total_value_usd", "net_usd", "portfolio_roi", "regressions_caught")
    portfolio = {key: _change(getattr(old.summary, key), getattr(new.summary, key)) for key in metrics}
    old_counts, new_counts = old.summary.verdicts, new.summary.verdicts
    verdict_names = {verdict.value for verdict in Verdict} | old_counts.keys() | new_counts.keys()
    verdicts = {key: _change(old_counts.get(key, 0), new_counts.get(key, 0)) for key in sorted(verdict_names)}

    old_accounts = {account.test_id: account for account in old.accounts}
    new_accounts = {account.test_id: account for account in new.accounts}
    verdict_changes = []
    net_changes = []
    for test_id in sorted(old_accounts.keys() & new_accounts.keys()):
        before, after = old_accounts[test_id], new_accounts[test_id]
        if before.verdict != after.verdict:
            verdict_changes.append({"test_id": test_id, "old": before.verdict, "new": after.verdict})
        net = _change(before.net_usd, after.net_usd)
        if net["delta"]:
            net_changes.append({"test_id": test_id, **net})
    net_changes.sort(key=lambda item: -abs(item["delta"]))

    old_rates, new_rates = _assumptions(old.assumptions), _assumptions(new.assumptions)
    missing = object()
    assumptions = {
        key: {"old": old_rates.get(key), "new": new_rates.get(key)}
        for key in sorted(old_rates.keys() | new_rates.keys())
        if old_rates.get(key, missing) != new_rates.get(key, missing)
    }
    return {
        "portfolio": portfolio,
        "verdicts": verdicts,
        "added": sorted(new_accounts.keys() - old_accounts.keys()),
        "removed": sorted(old_accounts.keys() - new_accounts.keys()),
        "verdict_changes": verdict_changes,
        "net_changes": net_changes[:10],
        "assumptions": assumptions,
    }


def _display(value: object) -> str:
    return "n/a" if value is None else str(value)


def diff_tables(report: dict) -> Iterator[tuple[str, tuple[str, ...], list[tuple[str, ...]]]]:
    comparison = ("Previous", "Current", "Change")
    for title, key, first_header in (
        ("Portfolio", "portfolio", "Metric"),
        ("Verdict counts", "verdicts", "Verdict"),
    ):
        yield (
            title,
            (first_header, *comparison),
            [
                (name, _display(row["old"]), _display(row["new"]), _display(row["delta"]))
                for name, row in report[key].items()
            ],
        )
    yield "Tests added", ("Test",), [(name,) for name in report["added"]]
    yield "Tests removed", ("Test",), [(name,) for name in report["removed"]]
    yield (
        "Verdict changes",
        ("Test", "Previous", "Current"),
        [(row["test_id"], row["old"], row["new"]) for row in report["verdict_changes"]],
    )
    yield (
        "Largest net changes (USD)",
        ("Test", *comparison),
        [
            (row["test_id"], _display(row["old"]), _display(row["new"]), _display(row["delta"]))
            for row in report["net_changes"]
        ],
    )
    yield (
        "Changed assumptions",
        ("Assumption", "Previous", "Current"),
        [(name, _display(row["old"]), _display(row["new"])) for name, row in report["assumptions"].items()],
    )


def diff_markdown(report: dict) -> str:
    lines = ["# TestLedger comparison"]
    for title, headers, rows in diff_tables(report):
        lines.extend(("", f"## {title}", ""))
        if not rows:
            lines.append("None.")
            continue
        lines.extend(("| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"))
        for row in rows:
            cells = [
                escape(" ".join(value.splitlines())).replace("\\", "\\\\").replace("|", "\\|")
                for value in row
            ]
            lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
