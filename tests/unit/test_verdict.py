"""Unit tests for persisted gate verdicts (meta_harness.verdict)."""

from __future__ import annotations

from pathlib import Path

from meta_harness.verdict import (
    LAST_VERDICT_FILE,
    Verdict,
    read_last_verdict,
    write_last_verdict,
)


def test_write_then_read_round_trips(tmp_path: Path) -> None:
    v = Verdict(
        ok=True, checks=(("00_build", "pass"), ("40_test", "pass")), run_id="r1", digest="d1"
    )
    write_last_verdict(tmp_path, v)
    assert (tmp_path / LAST_VERDICT_FILE).is_file()
    got = read_last_verdict(tmp_path)
    assert got == v


def test_write_creates_evidence_dir(tmp_path: Path) -> None:
    # .meta-harness/ need not pre-exist — write creates it.
    write_last_verdict(tmp_path, Verdict(ok=False, checks=(("50_security", "fail"),)))
    got = read_last_verdict(tmp_path)
    assert got is not None
    assert got.ok is False
    assert got.checks == (("50_security", "fail"),)


def test_read_missing_returns_none(tmp_path: Path) -> None:
    assert read_last_verdict(tmp_path) is None


def test_read_malformed_json_returns_none(tmp_path: Path) -> None:
    path = tmp_path / LAST_VERDICT_FILE
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert read_last_verdict(tmp_path) is None


def test_read_wrong_shape_returns_none(tmp_path: Path) -> None:
    path = tmp_path / LAST_VERDICT_FILE
    path.parent.mkdir(parents=True)
    # a JSON array, and an object missing 'ok', both invalid
    for bad in ("[1, 2, 3]", '{"checks": []}', '{"ok": "yes"}', '{"ok": true, "checks": "nope"}'):
        path.write_text(bad, encoding="utf-8")
        assert read_last_verdict(tmp_path) is None


def test_to_dict_is_json_shaped() -> None:
    v = Verdict(ok=True, checks=(("00_build", "pass"),), run_id="r", digest="d")
    d = v.to_dict()
    assert d == {"ok": True, "run_id": "r", "digest": "d", "checks": [["00_build", "pass"]]}
