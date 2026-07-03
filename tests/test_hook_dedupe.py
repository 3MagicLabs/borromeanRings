"""Duplicate hook registrations must not double-apply non-idempotent effects.

A workspace can have the same hook registered twice — its own project-level
``.claude/settings.json`` entry plus the user-level one written by
``install-global.sh``. The substrate then runs the hook script twice per event:
the prompt-rewrite directive was injected twice per prompt, and the Stop gate
ran twice (double-counting retry attempts toward the escalation CAP).

``meta_harness.hook_dedupe.claim`` is the fix: an atomic first-writer-wins
claim with a freshness window. Unit tests cover the claim semantics; the
integration tests drive the real ``prompt_rewrite.sh`` hook twice and assert
the directive is emitted exactly once.
"""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from meta_harness.hook_dedupe import claim

BORROMEANRINGS_HOME = Path(__file__).resolve().parents[1]
HOOKS = BORROMEANRINGS_HOME / ".claude" / "hooks"

# --- unit: claim semantics ---------------------------------------------------


def test_first_claim_wins(tmp_path: Path) -> None:
    assert claim(tmp_path / "markers", "stop", "session-1") is True


def test_duplicate_within_window_is_rejected(tmp_path: Path) -> None:
    markers = tmp_path / "markers"
    assert claim(markers, "stop", "session-1") is True
    assert claim(markers, "stop", "session-1") is False


def test_distinct_keys_do_not_collide(tmp_path: Path) -> None:
    markers = tmp_path / "markers"
    assert claim(markers, "stop", "session-1") is True
    assert claim(markers, "stop", "session-2") is True
    assert claim(markers, "user_prompt_submit", "session-1") is True


def test_stale_marker_is_reclaimed(tmp_path: Path) -> None:
    markers = tmp_path / "markers"
    assert claim(markers, "stop", "session-1", window_seconds=5.0) is True
    marker = next(markers.iterdir())
    old = time.time() - 60
    os.utime(marker, (old, old))
    assert claim(markers, "stop", "session-1", window_seconds=5.0) is True
    # ...and the reclaim refreshed the window, so a duplicate now loses again.
    assert claim(markers, "stop", "session-1", window_seconds=5.0) is False


def test_unwritable_marker_dir_fails_open(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("")  # a FILE where the marker dir's parent should be
    assert claim(blocker / "markers", "stop", "session-1") is True


def test_uncreatable_marker_fails_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def deny(*args: object, **kwargs: object) -> int:
        raise PermissionError("no")

    monkeypatch.setattr(os, "open", deny)
    assert claim(tmp_path / "markers", "stop", "session-1") is True


def test_vanished_marker_fails_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The marker 'exists' at open time but is gone by stat time (cleanup race)."""
    markers = tmp_path / "markers"
    markers.mkdir()

    def race(*args: object, **kwargs: object) -> int:
        raise FileExistsError("marker existed a moment ago")

    monkeypatch.setattr(os, "open", race)
    # os.open says the marker exists; the real stat() then finds nothing there.
    assert claim(markers, "stop", "session-1") is True


# --- integration: the prompt-rewrite hook emits the directive once -----------


def _governed_project(tmp_path: Path) -> Path:
    (tmp_path / "borromeanrings.toml").write_text(
        '[project]\nlanguage = "none"\npackage = "x"\n\n'
        '[checks]\nrequired = ["05_hygiene"]\n\n'
        "[hygiene]\nrequires = []\n\n"
        "[prompt_rewriting]\nenabled = true\n\n"
        '[context]\naccount = "test/acct"\n'
    )
    return tmp_path


def _run_prompt_rewrite(project: Path, payload: dict[str, str]) -> str:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project)
    result = subprocess.run(
        ["bash", str(HOOKS / "prompt_rewrite.sh")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    return result.stdout


def test_duplicate_registration_injects_directive_once(tmp_path: Path) -> None:
    project = _governed_project(tmp_path)
    payload = {"session_id": "s1", "prompt": "add a feature"}
    first = _run_prompt_rewrite(project, payload)
    second = _run_prompt_rewrite(project, payload)  # the duplicate registration
    assert "[borromeanRings]" in first
    assert second.strip() == ""


def test_new_prompt_gets_a_fresh_directive(tmp_path: Path) -> None:
    project = _governed_project(tmp_path)
    assert "[borromeanRings]" in _run_prompt_rewrite(
        project, {"session_id": "s1", "prompt": "first ask"}
    )
    assert "[borromeanRings]" in _run_prompt_rewrite(
        project, {"session_id": "s1", "prompt": "second, different ask"}
    )


def test_empty_payload_still_emits_directive(tmp_path: Path) -> None:
    # Fail-open: a missing/timed-out payload must never silently drop governance.
    project = _governed_project(tmp_path)
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project)
    result = subprocess.run(
        ["bash", str(HOOKS / "prompt_rewrite.sh")],
        input="",
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert "[borromeanRings]" in result.stdout
