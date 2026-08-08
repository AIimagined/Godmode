"""Does each mechanism actually fire, and what does the brief cost?

A published figure needs a corpus chosen before the result is seen, or it is not
evidence. These four tasks were written from the capabilities this product
claims, not from what happened to look good.

Three of the four are binary: the mechanism either catches the planted fault or
it does not, and no agent session is required to find out. The fourth is the
token question, measured as what the brief costs against the material it stands
in for — not as a saving, which would require running the same work twice and is
not something this harness pretends to know.

**Every task ships its own falsification.** A control run with the fault absent
must produce the opposite result. A task whose control also "passes" measures
nothing, and is reported as broken rather than as a success.

Run:  python benchmarks/benchmark.py
      python benchmarks/benchmark.py --json results/latest.json

Requires nothing but this repository and Python. No network, no model, no keys.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
GODMODE = ROOT / "scripts" / "godmode.py"

WEAKENED = """import pytest

@pytest.mark.skip(reason="flaky")
def test_expiry():
    assert True
"""
INTACT = """def test_expiry():
    token = make_token(ttl=0)
    assert token.expired()
    assert token.refresh_required()
"""


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300)


def _godmode(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _run(sys.executable, str(GODMODE), "--project", str(project), *args, cwd=project)


def _seed(repo: Path, test_body: str) -> None:
    _run("git", "init", "-q", cwd=repo)
    _run("git", "config", "user.email", "bench@example.invalid", cwd=repo)
    _run("git", "config", "user.name", "bench", cwd=repo)
    (repo / "tests").mkdir(exist_ok=True)
    (repo / "tests" / "test_auth.py").write_text(test_body, encoding="utf-8")
    _run("git", "add", "-A", cwd=repo)
    _run("git", "commit", "-q", "-m", "baseline", cwd=repo)
    _godmode(repo, "init")


def task_planted_regression(repo: Path) -> dict:
    """A test weakened to manufacture a pass must be blocked."""
    _seed(repo, INTACT)
    (repo / "tests" / "test_auth.py").write_text(WEAKENED, encoding="utf-8")
    treated = _godmode(repo, "integrity", "--base", "HEAD").returncode

    # Control: restore the assertions, and the same check must not block.
    (repo / "tests" / "test_auth.py").write_text(INTACT, encoding="utf-8")
    control = _godmode(repo, "integrity", "--base", "HEAD").returncode
    return {"caught": treated != 0, "control_clean": control == 0}


def task_seeded_drift(repo: Path) -> dict:
    """One version surface moved out of step must fail reconciliation."""
    _seed(repo, INTACT)
    (repo / "packaging").mkdir(exist_ok=True)
    (repo / "packaging" / "hosts.json").write_text(
        json.dumps({"identity": {"version": "1.0.0"}}), encoding="utf-8")
    (repo / ".claude-plugin").mkdir(exist_ok=True)
    manifest = repo / ".claude-plugin" / "plugin.json"
    manifest.write_text(json.dumps({"name": "x", "version": "1.0.0"}), encoding="utf-8")
    control = _godmode(repo, "version", "--reconcile", "--brief").returncode

    manifest.write_text(json.dumps({"name": "x", "version": "9.9.9"}), encoding="utf-8")
    treated = _godmode(repo, "version", "--reconcile", "--brief").returncode
    return {"caught": treated != 0, "control_clean": control == 0}


def task_spent_hypothesis(repo: Path) -> dict:
    """Three checkpoints under one explanation must end that explanation."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from godmode_runtime.godmode_loop import hypothesis_reset_required

    def run(count: int) -> bool:
        records = [{"sequence": i, "kind": "checkpoint", "subject": "still failing",
                    "data": {"status": "failed", "hypothesis": "the list is incomplete"}}
                   for i in range(count)]
        return bool(hypothesis_reset_required(records))

    return {"caught": run(3), "control_clean": not run(2)}


def task_brief_cost(repo: Path) -> dict:
    """What the bounded brief costs against the records it stands in for.

    Not a saving. Establishing a saving needs the same work done twice, which
    this harness cannot do and does not claim.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from godmode_runtime.godmode_anchor import resolve_anchor
    from godmode_runtime.godmode_chronicle import Chronicle
    from godmode_runtime.godmode_lens import build_context_brief

    anchor = resolve_anchor(str(ROOT))
    archive = Chronicle(anchor)
    records = archive.read_events()
    raw = max(1, len(json.dumps(records, default=str)) // 4)
    brief = int(build_context_brief(anchor, archive).get("estimated_tokens") or raw)
    return {
        "records": len(records),
        "raw_tokens": raw,
        "brief_tokens": brief,
        "ratio": round(brief / raw, 4) if raw else None,
        # No control: this measures a size, not a detection, so there is no
        # fault to plant and nothing to falsify. Stated rather than implied.
        "control_clean": None,
    }


TASKS = {
    "planted-regression": task_planted_regression,
    "seeded-drift": task_seeded_drift,
    "spent-hypothesis": task_spent_hypothesis,
    "brief-cost": task_brief_cost,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", help="Write results to this path as well")
    arguments = parser.parse_args()

    results: dict[str, dict] = {}
    for name, task in TASKS.items():
        with tempfile.TemporaryDirectory(prefix=f"bench-{name}-") as raw:
            try:
                results[name] = task(Path(raw))
            except Exception as exc:  # noqa: BLE001 - a broken task is a result
                results[name] = {"error": f"{type(exc).__name__}: {exc}"}

    broken = []
    for name, result in results.items():
        if "error" in result:
            broken.append(f"{name}: {result['error']}")
        elif result.get("caught") is False:
            broken.append(f"{name}: the planted fault was not caught")
        elif result.get("control_clean") is False:
            broken.append(f"{name}: the control also fired, so the task measures nothing")

    print(json.dumps({"results": results, "broken": broken,
                      "verdict": "all-mechanisms-fire" if not broken else "review-required"},
                     indent=2, sort_keys=True))
    if arguments.json:
        target = Path(arguments.json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
