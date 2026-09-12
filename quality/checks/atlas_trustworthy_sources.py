"""Check: atlas `trustworthy` is the absence of findings, and unparsed files
are only one of the five things that can produce one.

Fails if the finding sources change without this being revisited.
"""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from godmode_runtime.godmode_atlas import Atlas  # noqa: E402

src = inspect.getsource(Atlas.diagnose)
sources = src.count("findings.append")
assert sources == 5, f"expected 5 finding sources, found {sources}"
assert '"trustworthy": not findings' in src, "trustworthy is no longer 'not findings'"
assert "could not be parsed" in src, "the unparsed finding is gone"
print(f"ok: trustworthy = not findings; {sources} finding sources; unparsed is one of them")
