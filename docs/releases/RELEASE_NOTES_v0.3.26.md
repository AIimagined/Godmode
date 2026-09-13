# Godmode v0.3.26

## Added

- **Uninstall leaves nothing behind - and touches nothing else.** Every file
  the host writers create is recorded in a per-plugin install manifest.
  Uninstall reads only that manifest, validates every entry before anything
  moves, requires real containment inside the install root, and moves
  artifacts into a timestamped archive instead of deleting them. Another
  plugin's files, and your own files in the same directory, are left alone.
- **Frozen regions.** Mark the editable parts of a file with a marker pair.
  The editor is shown only those parts, with a visible marker where text was
  withheld, and an edit whose span reaches frozen text is refused at the
  pre-tool boundary with the offsets and the ranges it could have used. A
  file with no markers is unaffected.
- **Text that hides what it says.** The instruction scanner now reports
  bidirectional controls, invisible code points and stray control characters
  separately, naming the code point, and still catches a directive split
  across a shell line continuation. Every finding carries a remedy.
- **A constraint credited to someone else is flagged before it is changed.**
  When an edited line says a value is required by an outside authority, the
  post-edit hook advises reading that authority first.
- **A compaction leaves a record.** The pre-compact hook writes the trigger
  the host declared and the archive position, so a session can tell that it
  compacted.
- **Load-bearing assumptions.** `remember` can mark an assumption as the one
  a plan rests on, and marking it requires naming what fails without it.
- **A false-green rate that says how much it saw.** The calibration digest
  reports `verified_unresolved` and `coverage` beside the rate, so a zero over
  one resolved claim reads as unmeasured, not clean.
- **Publication checks.** `quality/checks/prepublication.py` answers "is this
  tree ready to be public by its own policy" with an exit code: names from a
  runtime-supplied deny list, citation markers, tracked paths under declared
  unpublishable prefixes, and links to files that are no longer tracked.

## Fixed

- **The gate reads what a script does.** Running a project script is
  classified by the commands written literally in it, and the refusal names
  the file. Bounded on purpose: files inside the project, one level deep,
  literals only - a command assembled at runtime inside an interpreter is
  beyond what any hook can see.
- **`find -exec` is judged by the command it runs.** Counting lines is a
  read; an unknown or shell command stays protected; `-delete`, `-ok` and
  `-okdir` keep their verdicts.
- **A quoted heredoc body is data.** Backticks and `$(...)` inside
  `<<'EOF'` no longer read as commands. Unquoted and interpreter-fed heredocs
  are scanned as before.
- **A cited check runs as written or is refused.** A `cmd:` citation carrying
  `&&`, `|` or a redirect is refused at record time instead of running as
  literal arguments and grading a claim whose later conditions never ran.
- **A retired lesson stops pinning its surface.** Lesson status is read
  newest-record-wins, so retirement is reachable.
- **Faster session start.** The manifest-desync check no longer lists every
  directory in the plugin cache, and the database inventory prunes ignored
  directories instead of walking into them; on a cache holding many cloned
  plugins the session-start hook went from tens of seconds to a few.
- **The Cursor end-to-end fixture sends Cursor's own tool name**, so the
  force-push scenario reads `deny` on every host.
- Local and CI gates agree again: the untrusted-content scan uses the shared
  ignore list, the Claude manifest's experimental key is generated from
  source, and archived documents are not linted.

## Limits

- The gate reads literal commands in a project script, one level deep. A
  command a script builds at runtime is not visible to any pre-tool hook.
- Frozen regions are opt-in per file; nothing is frozen until a file
  declares its markers.
- A session keeps the plugin it started with; the faster session start
  applies from the first session after the plugin is updated.

## Verifying

- `python -m unittest tests.test_install_manifest tests.test_install_remove
  tests.test_install_manifest_end_to_end`: the manifest, contained and
  reversible removal, and an install-then-uninstall that leaves a foreign
  file untouched.
- `python -m unittest tests.test_mutable_regions tests.test_patch_containment
  tests.test_frozen_region_edit_verdict`: the redacted view, the refused
  patch, and the refusal at the edit boundary.
- `python -m unittest tests.test_script_body_escalation
  tests.test_find_exec_classification tests.test_quoted_heredoc_substitution
  tests.test_citation_shell_grammar tests.test_lesson_retirement`: the five
  gate and claim fixes.
- `python -m unittest tests.test_concealed_text_scan
  tests.test_directive_continuations tests.test_attributed_constraints
  tests.test_compaction_record tests.test_load_bearing_assumption
  tests.test_false_green_coverage`: the scanner, the advisory, and the
  records.
- `python -m unittest tests.e2e.test_host_e2e`: force-push reads `deny` on
  every host dialect, Cursor included.
