"""Check: `trust` reports a local authorization policy that downgrades categories.

A 2026-08-08 acceptance criterion says a declared downgrade must appear as a
`trust` finding, "since the off-switch being visible is the whole point".

This project carries `.godmode-authorization-policy.json` downgrading six
protected categories to ask-only, and `trust` reports `no-configuration-present`
with zero findings. The off-switch is invisible in the surface built to show it.

This check FAILS today. It is the reproduction, and it passes when the gap closes.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / ".godmode-authorization-policy.json"

if not POLICY.exists():
    print("no local authorization policy present; nothing to report")
    raise SystemExit(0)

policy = json.loads(POLICY.read_text(encoding="utf-8"))
downgraded = sorted(policy.get("ask_only", []))
assert downgraded, "policy present but declares no downgrade; check is moot"

out = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "godmode.py"), "--project", str(ROOT), "trust"],
    capture_output=True, text=True, timeout=180,
)
report = json.loads(out.stdout)

print(f"policy downgrades {len(downgraded)} categories: {', '.join(downgraded)}")
print(f"trust verdict: {report.get('verdict')}  findings: {len(report.get('findings', []))}"
      f"  declarations: {report.get('declarations')}")

named = json.dumps(report).lower()
missing = [c for c in downgraded if c.lower() not in named]

assert report.get("verdict") != "no-configuration-present", (
    "trust reports no configuration while an authorization policy is present"
)
assert not missing, f"trust does not name these downgraded categories: {missing}"
print("ok: trust reports every declared downgrade")
