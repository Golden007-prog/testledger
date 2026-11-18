import json
from pathlib import Path

from typer.testing import CliRunner

from testledger.cli import app

runner = CliRunner()
fixtures = Path(__file__).parent / "fixtures" / "ledger"
previous = fixtures / "previous.json"
current = fixtures / "current.json"


def test_diff_reports_portfolio_tests_and_assumptions():
    result = runner.invoke(app, ["diff", str(previous), str(current), "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["portfolio"]["net_usd"] == {"old": 10, "new": 16, "delta": 6}
    assert report["portfolio"]["portfolio_roi"]["delta"] == -0.2
    assert report["portfolio"]["regressions_caught"]["delta"] == 2
    assert report["verdicts"]["fix"] == {"old": 1, "new": 0, "delta": -1}
    assert report["added"] == ["suite::added"]
    assert report["removed"] == ["suite::removed"]
    assert report["verdict_changes"] == [
        {"test_id": "suite::declines", "old": "asset", "new": "hold"},
        {"test_id": "suite::improves", "old": "fix", "new": "asset"},
    ]
    assert [(row["test_id"], row["delta"]) for row in report["net_changes"]] == [
        ("suite::improves", 13),
        ("suite::declines", -4),
    ]
    assert report["assumptions"] == {
        "ci_minute_usd": {"old": 0.1, "new": 0.2},
        "thresholds.min_executions_for_verdict": {"old": 8, "new": 10},
    }


def test_diff_prints_tables_and_writes_markdown(tmp_path):
    out = tmp_path / "diff.md"
    result = runner.invoke(app, ["diff", str(previous), str(current), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "Portfolio" in result.output
    markdown = out.read_text(encoding="utf-8")
    assert "| net_usd | 10" in markdown
    assert "| suite::improves | fix | asset |" in markdown
    assert "thresholds.min_executions_for_verdict" in markdown


def test_diff_does_not_overwrite_an_input_file(tmp_path):
    source = tmp_path / "ledger.json"
    data = current.read_text(encoding="utf-8")
    source.write_text(data, encoding="utf-8")
    result = runner.invoke(app, ["diff", str(previous), str(source), "--out", str(source)])
    assert result.exit_code != 0
    assert source.read_text(encoding="utf-8") == data


def test_diff_leaves_delta_undefined_when_previous_roi_is_missing(tmp_path):
    old = json.loads(previous.read_text(encoding="utf-8"))
    old["summary"]["portfolio_roi"] = None
    source = tmp_path / "ledger.json"
    source.write_text(json.dumps(old), encoding="utf-8")
    result = runner.invoke(app, ["diff", str(source), str(current), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["portfolio"]["portfolio_roi"] == {
        "old": None,
        "new": 0.8,
        "delta": None,
    }
