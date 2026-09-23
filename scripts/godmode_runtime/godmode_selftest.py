"""Name every CLI verb missing a test, a public doc, or a skill mention.

A verb the parser accepts but nothing else names ships untested and
unfindable: no test exercises it, no doc tells an operator it exists, no
skill routes an agent to it at the moment of demand. `verb_coverage` measures
all three so `selftest` can fail the verdict on the exact list rather than a
bare count.

The check is always about Godmode's OWN shipped surface, never the caller's
project: `PLUGIN_ROOT` is derived from this file's own location, not from
whatever directory a host happened to invoke `selftest` against. A verb
named nowhere in this project's own tests/docs/skills is a real gap in what
ships; the same verb absent from some unrelated downstream project's docs
would not be.
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess

# scripts/godmode_runtime/godmode_selftest.py -> parents[0]=scripts/godmode_runtime,
# [1]=scripts, [2]=the repository root this file ships from.
PLUGIN_ROOT = Path(__file__).resolve().parents[2]

# Doc segments that are never public command reference: an archived
# evaluation's own past release notes. A gitignored working-documents
# archive needs no entry here at all - the corpus is built from tracked
# files only (see `_tracked_paths`), so an untracked directory is excluded
# by construction rather than by naming it.
_EXCLUDED_DOC_SEGMENTS = ("releases",)


def looks_like_godmode_source_tree(root: Path) -> bool:
    """Whether `root` is a real Godmode checkout the verb-coverage control can
    read, rather than an install shape that dropped its own tests or source -
    the check would otherwise silently report every verb as an orphan."""
    return (root / "scripts" / "godmode_runtime").is_dir() and (root / "tests").is_dir()


_COMMAND_REFERENCE_ROW = re.compile(r"^\| `([\w-]+)` \|")


def _verbs_from_command_reference(root: Path) -> tuple[str, ...]:
    """The top-level verbs the CLI accepts, read from the committed,
    generated `docs/COMMAND-REFERENCE.md` rather than the live parser.

    The parser itself lives in `godmode_console`, which imports `selftest`
    from `godmode_assess` at module load; `godmode_assess.selftest` calls
    into this module's `verb_coverage`, so an import of `godmode_console`
    HERE - even a lazily-called one - would close console -> assess ->
    selftest -> console, exactly the cycle `godmode_atlas.cycles()` exists
    to catch (`tests.test_godmode_runtime.AtlasTests
    .test_godmode_runtime_has_no_import_cycle`). The doc is generated
    FROM that same live parser and kept in sync with it by
    `tests/test_command_reference_drift.py`, so reading it back is exact,
    not approximate - and it is a leaf artifact, not a module, so reading
    it closes nothing.

    An empty tuple - never a crash - when the doc is absent, e.g. an
    install shape that dropped it, or a project this check runs against
    that is not Godmode's own tree.
    """
    path = root / "docs" / "COMMAND-REFERENCE.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ()
    return tuple(sorted({match.group(1) for line in text.splitlines()
                        if (match := _COMMAND_REFERENCE_ROW.match(line))}))


def _excluded(relative: Path, exclude: tuple[str, ...]) -> bool:
    """Segment-scoped: only `relative`'s own parts count, never the parent
    the caller resolved `root` from. A checkout sitting under a directory
    that happens to be named like an excluded segment must not lose its own
    docs corpus to a substring match on the wrong path."""
    if not exclude:
        return False
    posix = relative.as_posix()
    return any(re.search(r"(^|/)" + re.escape(name) + r"(/|$)", posix) for name in exclude)


def _bare_word(verb: str, text: str) -> bool:
    """The loose rule: `verb` appears anywhere as its own word. Kept for the
    tests corpus, where a verb is named as a plain string literal
    (`"ceilings"`), never backticked or `godmode`-prefixed."""
    return re.search(r"(?<![\w-])" + re.escape(verb) + r"(?![\w-])", text) is not None


def _named_as_a_command(verb: str, text: str) -> bool:
    """The strict rule for docs/skills: bare English prose that happens to
    contain the verb's spelling ("watch it get checked") does not document
    the command - only a backticked token (`` `verb` `` alone, or `verb` as
    the FIRST token inside a longer span such as `` `docs --lint` `` or
    `` `release-notes check` ``) or a `godmode <verb>` mention (backticked
    or in a fenced shell line, "godmode" matched case-insensitively) does."""
    boundary = r"(?<![\w-])" + re.escape(verb) + r"(?![\w-])"
    if re.search(r"`" + re.escape(verb) + r"(?![\w-])(?:`| )", text):
        return True
    return re.search(r"(?i:godmode)[ \t]+" + boundary, text) is not None


def _tracked_paths(root: Path, *dirs: str) -> list[Path] | None:
    """Every git-tracked path at or under `dirs`, resolved under `root`.
    None when git is unavailable (no repository here, or the binary is
    missing) so the caller falls back to a plain glob - a fresh
    non-git checkout must not silently corpus as empty.

    Reading TRACKED files only is what excludes a gitignored
    working-documents archive from the corpus - by construction, never
    by spelling out its directory name."""
    try:
        done = subprocess.run(["git", "ls-files", "--", *dirs], cwd=root,
                              capture_output=True, text=True, timeout=30)
    except OSError:
        return None
    if done.returncode != 0:
        return None
    return [root / line for line in done.stdout.splitlines() if line.strip()]


def verb_coverage(root: Path, verbs: tuple[str, ...] | None = None) -> dict[str, list[str]]:
    """Name every verb no test, no public doc, or no skill/command surface mentions."""
    if verbs is None:
        verbs = _verbs_from_command_reference(root)

    def glob_corpus(patterns: tuple[str, ...], exclude: tuple[str, ...] = ()) -> str:
        chunks = []
        for pattern in patterns:
            for path in root.glob(pattern):
                if _excluded(path.relative_to(root), exclude):
                    continue
                try:
                    chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
                except OSError:
                    continue
        return "\n".join(chunks)

    def tracked_corpus(paths: list[Path], exclude: tuple[str, ...] = ()) -> str:
        chunks = []
        for path in paths:
            if path.suffix != ".md":
                continue
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            if _excluded(relative, exclude):
                continue
            try:
                chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
        return "\n".join(chunks)

    tests = glob_corpus(("tests/**/test_*.py",))

    tracked_docs = _tracked_paths(root, "docs", "README.md")
    if tracked_docs is None:
        docs = glob_corpus(("docs/**/*.md", "README.md"), exclude=_EXCLUDED_DOC_SEGMENTS)
    else:
        docs = tracked_corpus(tracked_docs, exclude=_EXCLUDED_DOC_SEGMENTS)

    tracked_skills = _tracked_paths(root, "skills")
    if tracked_skills is None:
        skills = glob_corpus(("skills/**/*.md",))
    else:
        skills = tracked_corpus(tracked_skills)

    return {
        "untested": [v for v in verbs if not _bare_word(v, tests)],
        "undocumented": [v for v in verbs if not _named_as_a_command(v, docs)],
        "unrouted": [v for v in verbs if not _named_as_a_command(v, skills)],
    }


def _self_check() -> None:
    import shutil
    import tempfile

    made: list[Path] = []

    def _mkdtemp(prefix: str | None = None) -> Path:
        path = Path(tempfile.mkdtemp(prefix=prefix))
        made.append(path)
        return path

    try:
        _self_check_body(_mkdtemp)
    finally:
        for path in made:
            shutil.rmtree(path, ignore_errors=True)


def _self_check_body(_mkdtemp) -> None:
    assert looks_like_godmode_source_tree(PLUGIN_ROOT), PLUGIN_ROOT
    assert not looks_like_godmode_source_tree(_mkdtemp())

    root = _mkdtemp()
    (root / "tests").mkdir()
    (root / "docs").mkdir()
    (root / "skills").mkdir()
    (root / "tests" / "test_probe.py").write_text("alpha\n", encoding="utf-8")
    (root / "docs" / "guide.md").write_text("`alpha` does the thing.\n", encoding="utf-8")
    (root / "skills" / "probe.md").write_text("run `godmode alpha` first.\n", encoding="utf-8")
    report = verb_coverage(root, verbs=("alpha", "beta"))
    assert report == {
        "untested": ["beta"],
        "undocumented": ["beta"],
        "unrouted": ["beta"],
    }, report

    # Bare English prose containing the verb's spelling must not count as
    # documenting it - the exact loophole this rule closes.
    prose_only = _mkdtemp()
    (prose_only / "tests").mkdir()
    (prose_only / "docs").mkdir()
    (prose_only / "skills").mkdir()
    (prose_only / "docs" / "guide.md").write_text(
        "alpha appears here only as ordinary prose, never backticked.\n", encoding="utf-8"
    )
    prose_report = verb_coverage(prose_only, verbs=("alpha",))
    assert prose_report["undocumented"] == ["alpha"], prose_report

    # A root directory whose own name contains an excluded segment must not
    # lose its own docs corpus - only a path segment UNDER root counts.
    named_root = _mkdtemp(prefix="sp-lab-releases-")
    (named_root / "tests").mkdir()
    (named_root / "docs").mkdir()
    (named_root / "skills").mkdir()
    (named_root / "README.md").write_text("`alpha`\n", encoding="utf-8")
    named_report = verb_coverage(named_root, verbs=("alpha",))
    assert "alpha" not in named_report["undocumented"], named_report

    # The verb as the first token inside a longer backticked span (a
    # subcommand form, e.g. `` `docs --lint` `` or `` `release-notes
    # check` ``) counts - not only the bare `` `verb` `` span.
    assert _named_as_a_command("docs", "run `docs --lint` before shipping.")
    assert _named_as_a_command("release-notes", "then `release-notes check` it.")
    # A verb elsewhere in a longer span, not as the first token, still does
    # not count - "release" is not the first token of "release-notes".
    assert not _named_as_a_command("release", "then `release-notes check` it.")

    # `godmode <verb>` is matched case-insensitively on the word "godmode"
    # only - the verb itself still matches its own exact spelling.
    assert _named_as_a_command("alpha", "Run `Godmode alpha` first.")
    assert _named_as_a_command("alpha", "GODMODE alpha at a sentence start.")

    verbs = _verbs_from_command_reference(PLUGIN_ROOT)
    assert isinstance(verbs, tuple) and len(verbs) > 0, verbs
    assert verbs == tuple(sorted(verbs)), "verbs must come back sorted"

    print("godmode_selftest self-check OK")


if __name__ == "__main__":
    _self_check()
