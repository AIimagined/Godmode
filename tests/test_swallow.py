"""Silent/swallowed-error scanner: catch/except shapes that discard failure.

Each detector gets a red case (the planted defect shape) beside an adjacent
innocent green case (the shape a reader would mistake it for, or the fix a
reader would apply) - an empty except beside one that logs, a bound name
beside one that is referenced, a destructure that drops `error` beside one
that checks it, an unannotated site beside one carrying a reason. The
ratchet tests pin the tighten-only contract directly: a stored baseline can
shrink freely but `--update-baseline` can never be used to raise it back
after a real regression.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import contextmanager

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_swallow import (  # noqa: E402
    BASELINE_FILENAME,
    _js_findings,
    _python_findings,
    scan_project,
    update_baseline,
)
from test_godmode_runtime import isolated_project  # noqa: E402


@contextmanager
def temp_project():
    with tempfile.TemporaryDirectory() as temporary:
        yield Path(temporary)


def _checks(findings: list[dict]) -> list[str]:
    return [f["check"] for f in findings]


class PythonEmptyExceptTests(unittest.TestCase):
    def test_pass_only_except_is_flagged(self) -> None:
        findings, exemptions, reason = _python_findings(
            "a.py",
            "try:\n"
            "    do_thing()\n"
            "except Exception:\n"
            "    pass\n",
        )
        self.assertIsNone(reason)
        self.assertEqual(_checks(findings), ["empty-except"])
        self.assertEqual(exemptions, [])

    def test_comment_only_except_is_flagged(self) -> None:
        # A pure `#` comment leaves no AST node at all - the only way a
        # Python except body can be textually comment-only and still parse
        # is a docstring-shaped bare string, which is what this plants.
        findings, _, _ = _python_findings(
            "a.py",
            "try:\n"
            "    do_thing()\n"
            "except Exception:\n"
            "    'silently ignored, see ticket 42'\n",
        )
        self.assertEqual(_checks(findings), ["empty-except"])

    def test_ellipsis_only_except_is_flagged(self) -> None:
        findings, _, _ = _python_findings(
            "a.py",
            "try:\n    do_thing()\nexcept Exception:\n    ...\n",
        )
        self.assertEqual(_checks(findings), ["empty-except"])

    def test_except_that_logs_is_not_empty(self) -> None:
        findings, _, _ = _python_findings(
            "a.py",
            "import logging\n"
            "try:\n"
            "    do_thing()\n"
            "except Exception:\n"
            "    logging.exception('do_thing failed')\n",
        )
        self.assertEqual(findings, [])

    def test_except_that_handles_the_error_is_not_empty(self) -> None:
        findings, _, _ = _python_findings(
            "a.py",
            "try:\n    do_thing()\nexcept Exception:\n    fallback()\n",
        )
        self.assertEqual(findings, [])


class PythonUnusedExceptionNameTests(unittest.TestCase):
    def test_bound_name_never_referenced_is_flagged(self) -> None:
        findings, _, _ = _python_findings(
            "a.py",
            "try:\n"
            "    do_thing()\n"
            "except Exception as exc:\n"
            "    record_failure()\n",
        )
        self.assertEqual(_checks(findings), ["unused-exception-name"])

    def test_bound_name_referenced_passes(self) -> None:
        findings, _, _ = _python_findings(
            "a.py",
            "try:\n"
            "    do_thing()\n"
            "except Exception as exc:\n"
            "    record_failure(str(exc))\n",
        )
        self.assertEqual(findings, [])

    def test_bare_reraise_without_using_the_name_passes(self) -> None:
        # `except Exception as exc: raise` is the standard re-raise idiom -
        # the failure still propagates, so this is not a swallow at all.
        findings, _, _ = _python_findings(
            "a.py",
            "try:\n    do_thing()\nexcept Exception as exc:\n    raise\n",
        )
        self.assertEqual(findings, [])

    def test_reraise_as_a_different_error_without_using_the_name_passes(self) -> None:
        findings, _, _ = _python_findings(
            "a.py",
            "try:\n"
            "    do_thing()\n"
            "except Exception as exc:\n"
            "    raise RuntimeError('wrapped') from exc\n",
        )
        self.assertEqual(findings, [])


class PythonSuccessOnlyLogTests(unittest.TestCase):
    def test_try_logs_and_except_is_silent(self) -> None:
        findings, _, _ = _python_findings(
            "a.py",
            "import logging\n"
            "try:\n"
            "    logging.info('starting')\n"
            "    do_thing()\n"
            "except Exception:\n"
            "    cleanup()\n",
        )
        self.assertEqual(_checks(findings), ["success-only-log"])

    def test_both_branches_log_passes(self) -> None:
        findings, _, _ = _python_findings(
            "a.py",
            "import logging\n"
            "try:\n"
            "    logging.info('starting')\n"
            "    do_thing()\n"
            "except Exception:\n"
            "    logging.error('do_thing failed')\n",
        )
        self.assertEqual(findings, [])

    def test_except_that_reraises_is_not_success_only(self) -> None:
        findings, _, _ = _python_findings(
            "a.py",
            "import logging\n"
            "try:\n"
            "    logging.info('starting')\n"
            "    do_thing()\n"
            "except Exception:\n"
            "    raise\n",
        )
        self.assertEqual(findings, [])

    def test_try_without_logging_is_not_flagged(self) -> None:
        findings, _, _ = _python_findings(
            "a.py",
            "try:\n    do_thing()\nexcept Exception:\n    cleanup()\n",
        )
        self.assertEqual(findings, [])


class JsEmptyCatchTests(unittest.TestCase):
    def test_empty_catch_is_flagged(self) -> None:
        findings, exemptions = _js_findings(
            "a.ts", "try {\n  doThing();\n} catch (e) {\n}\n"
        )
        self.assertEqual(_checks(findings), ["empty-catch"])
        self.assertEqual(exemptions, [])

    def test_comment_only_catch_is_flagged(self) -> None:
        findings, _ = _js_findings(
            "a.ts",
            "try {\n  doThing();\n} catch (e) {\n  // ignored on purpose\n}\n",
        )
        self.assertEqual(_checks(findings), ["empty-catch"])

    def test_catch_that_handles_it_passes(self) -> None:
        findings, _ = _js_findings(
            "a.ts",
            "try {\n  doThing();\n} catch (e) {\n  reportFailure(e);\n}\n",
        )
        self.assertEqual(findings, [])


class JsUnusedCatchBindingTests(unittest.TestCase):
    def test_unused_binding_is_flagged(self) -> None:
        findings, _ = _js_findings(
            "a.ts",
            "try {\n  doThing();\n} catch (e) {\n  console.log('failed');\n}\n",
        )
        self.assertEqual(_checks(findings), ["unused-catch-binding"])

    def test_referenced_binding_passes(self) -> None:
        findings, _ = _js_findings(
            "a.ts",
            "try {\n  doThing();\n} catch (e) {\n  console.log(e.message);\n}\n",
        )
        self.assertEqual(findings, [])

    def test_typed_binding_is_still_checked(self) -> None:
        findings, _ = _js_findings(
            "a.ts",
            "try {\n  doThing();\n} catch (e: unknown) {\n  console.log('failed');\n}\n",
        )
        self.assertEqual(_checks(findings), ["unused-catch-binding"])

    def test_destructured_param_is_not_treated_as_an_unused_binding(self) -> None:
        # There is no single name to check for use here - only empty-catch
        # applies to a destructured catch parameter.
        findings, _ = _js_findings(
            "a.ts",
            "try {\n  doThing();\n} catch ({ message }) {\n  report(message);\n}\n",
        )
        self.assertEqual(findings, [])


class JsUnusedErrorDestructureTests(unittest.TestCase):
    def test_dropped_error_is_flagged(self) -> None:
        findings, _ = _js_findings(
            "a.ts",
            "const { data, error } = await client.query();\n"
            "render(data);\n",
        )
        self.assertEqual(_checks(findings), ["unused-error-destructure"])

    def test_error_destructured_and_used_passes(self) -> None:
        findings, _ = _js_findings(
            "a.ts",
            "const { data, error } = await client.query();\n"
            "if (error) {\n"
            "  throw error;\n"
            "}\n"
            "render(data);\n",
        )
        self.assertEqual(findings, [])


class AnnotationEscapeTests(unittest.TestCase):
    def test_annotation_with_reason_exempts_and_is_surfaced(self) -> None:
        findings, exemptions, _ = _python_findings(
            "a.py",
            "try:\n"
            "    do_thing()\n"
            "except Exception:  # godmode: swallow-ok best-effort, see ADR-9\n"
            "    pass\n",
        )
        self.assertEqual(findings, [])
        self.assertEqual(len(exemptions), 1)
        self.assertEqual(exemptions[0]["reason"], "best-effort, see ADR-9")
        self.assertEqual(exemptions[0]["check"], "empty-except")

    def test_annotation_without_reason_still_flags(self) -> None:
        findings, exemptions, _ = _python_findings(
            "a.py",
            "try:\n"
            "    do_thing()\n"
            "except Exception:  # godmode: swallow-ok\n"
            "    pass\n",
        )
        self.assertEqual(exemptions, [])
        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0]["annotation_without_reason"])

    def test_js_annotation_with_reason_exempts(self) -> None:
        findings, exemptions = _js_findings(
            "a.ts",
            "try {\n  doThing();\n} catch (e) { // godmode: swallow-ok cosmetic only\n}\n",
        )
        self.assertEqual(findings, [])
        self.assertEqual(exemptions[0]["reason"], "cosmetic only")


class SyntaxErrorHandlingTests(unittest.TestCase):
    def test_unparseable_python_is_reported_not_silently_skipped(self) -> None:
        findings, exemptions, reason = _python_findings("broken.py", "def (:\n")
        self.assertEqual(findings, [])
        self.assertEqual(exemptions, [])
        self.assertIsNotNone(reason)


class ScanProjectAndRatchetTests(unittest.TestCase):
    def test_no_baseline_reports_findings_without_a_regression(self) -> None:
        with temp_project() as project:
            (project / "a.py").write_text(
                "try:\n    do_thing()\nexcept Exception:\n    pass\n",
                encoding="utf-8",
            )
            report = scan_project(project)
            self.assertFalse(report["baseline_exists"])
            self.assertEqual(report["regressions"], [])
            self.assertEqual(report["verdict"], "findings")
            self.assertEqual(report["counts"], {"a.py": 1})

    def test_clean_tree_with_no_baseline_verdict_is_clean(self) -> None:
        with temp_project() as project:
            (project / "a.py").write_text("def add(a, b):\n    return a + b\n",
                                           encoding="utf-8")
            report = scan_project(project)
            self.assertEqual(report["verdict"], "clean")

    def test_update_baseline_then_clean_scan(self) -> None:
        with temp_project() as project:
            (project / "a.py").write_text(
                "try:\n    do_thing()\nexcept Exception:\n    pass\n",
                encoding="utf-8",
            )
            first = scan_project(project)
            update_baseline(project, first["counts"])
            second = scan_project(project)
            self.assertTrue(second["baseline_exists"])
            self.assertEqual(second["regressions"], [])
            self.assertEqual(second["baseline"], {"a.py": 1})

    def test_new_site_over_baseline_is_a_regression_naming_file_and_line(self) -> None:
        with temp_project() as project:
            (project / "a.py").write_text(
                "try:\n    do_thing()\nexcept Exception:\n    pass\n",
                encoding="utf-8",
            )
            update_baseline(project, scan_project(project)["counts"])
            # A second swallow site lands in the same file.
            (project / "a.py").write_text(
                "try:\n    do_thing()\nexcept Exception:\n    pass\n"
                "try:\n    do_other()\nexcept Exception:\n    pass\n",
                encoding="utf-8",
            )
            report = scan_project(project)
            self.assertEqual(report["verdict"], "regression")
            self.assertEqual(len(report["regressions"]), 1)
            self.assertEqual(report["regressions"][0]["path"], "a.py")
            self.assertEqual(report["regressions"][0]["current"], 2)
            self.assertEqual(report["regressions"][0]["baseline"], 1)

    def test_update_baseline_cannot_rescue_a_regression(self) -> None:
        """The tighten-only contract: re-running --update-baseline after a
        count grows must not raise the stored ceiling back up to match it."""
        with temp_project() as project:
            (project / "a.py").write_text(
                "try:\n    do_thing()\nexcept Exception:\n    pass\n",
                encoding="utf-8",
            )
            update_baseline(project, scan_project(project)["counts"])
            (project / "a.py").write_text(
                "try:\n    do_thing()\nexcept Exception:\n    pass\n"
                "try:\n    do_other()\nexcept Exception:\n    pass\n",
                encoding="utf-8",
            )
            grown = scan_project(project)
            self.assertEqual(grown["verdict"], "regression")
            # An operator runs --update-baseline hoping to accept the grown
            # count; the stored ceiling must stay at the old, lower value.
            written = update_baseline(project, grown["counts"])
            self.assertEqual(written["a.py"], 1)
            still = scan_project(project)
            self.assertEqual(still["verdict"], "regression")

    def test_plain_scan_auto_tightens_the_ceiling_downward(self) -> None:
        """RULING B3-3-1: shrinking never needs `--update-baseline`."""
        with temp_project() as project:
            (project / "a.py").write_text(
                "try:\n    do_thing()\nexcept Exception:\n    pass\n"
                "try:\n    do_other()\nexcept Exception:\n    pass\n",
                encoding="utf-8",
            )
            update_baseline(project, scan_project(project)["counts"])  # ceiling {a.py: 2}
            # Fix one of the two sites, WITHOUT running --update-baseline.
            (project / "a.py").write_text(
                "try:\n    do_thing()\nexcept Exception:\n    pass\n"
                "try:\n    do_other()\nexcept Exception:\n    cleanup()\n",
                encoding="utf-8",
            )
            after_fix = scan_project(project)
            self.assertEqual(after_fix["counts"], {"a.py": 1})
            self.assertEqual(after_fix["verdict"], "findings")
            # The plain scan itself wrote the ceiling down - no operator act.
            self.assertEqual(after_fix["baseline"], {"a.py": 1})
            # Persisted to disk, not just returned in-memory: a fresh scan
            # (no code change in between) still reports the tightened value.
            self.assertEqual(scan_project(project)["baseline"], {"a.py": 1})

    def test_creep_back_is_closed_the_reviewers_exact_probe(self) -> None:
        """RULING B3-3-1's own falsification probe: fix one of two sites
        with no `--update-baseline`, then land a brand-new, unrelated third
        site in the same file. Before the fix, this passed through
        completely undetected (`verdict: "findings"`, `regressions: []`) -
        the auto-tightened ceiling from the first fix must not leave the
        old count's headroom lying around for the new site to spend."""
        with temp_project() as project:
            (project / "a.py").write_text(
                "try:\n    do_thing()\nexcept Exception:\n    pass\n"
                "try:\n    do_other()\nexcept Exception:\n    pass\n",
                encoding="utf-8",
            )
            update_baseline(project, scan_project(project)["counts"])  # ceiling {a.py: 2}
            # Fix one site (count drops to 1); no --update-baseline run.
            (project / "a.py").write_text(
                "try:\n    do_thing()\nexcept Exception:\n    pass\n"
                "try:\n    do_other()\nexcept Exception:\n    cleanup()\n",
                encoding="utf-8",
            )
            scan_project(project)  # the plain scan that auto-tightens to 1
            # A brand-new, unrelated third site lands in the same file,
            # bringing the count back to the OLD ceiling (2).
            (project / "a.py").write_text(
                "try:\n    do_thing()\nexcept Exception:\n    pass\n"
                "try:\n    do_other()\nexcept Exception:\n    cleanup()\n"
                "try:\n    do_third()\nexcept Exception:\n    pass\n",
                encoding="utf-8",
            )
            report = scan_project(project)
            self.assertEqual(report["verdict"], "regression")
            self.assertEqual(
                report["regressions"],
                [{"path": "a.py", "current": 2, "baseline": 1}],
            )

    def test_new_unbaselined_site_is_never_auto_adopted_by_a_plain_scan(self) -> None:
        """Auto-tightening only ever moves an EXISTING ceiling down; it must
        never add a path that was never in the baseline at all - that would
        let a plain scan quietly adopt a brand-new defect as though it had
        always been budgeted."""
        with temp_project() as project:
            (project / "a.py").write_text(
                "try:\n    do_thing()\nexcept Exception:\n    pass\n",
                encoding="utf-8",
            )
            update_baseline(project, scan_project(project)["counts"])  # {a.py: 1}
            (project / "b.py").write_text(
                "try:\n    do_new()\nexcept Exception:\n    pass\n",
                encoding="utf-8",
            )
            report = scan_project(project)
            self.assertEqual(report["verdict"], "regression")
            self.assertEqual(
                report["regressions"],
                [{"path": "b.py", "current": 1, "baseline": 0}],
            )
            self.assertNotIn("b.py", report["baseline"])

    def test_baseline_shrinks_when_a_site_is_fixed(self) -> None:
        with temp_project() as project:
            (project / "a.py").write_text(
                "try:\n    do_thing()\nexcept Exception:\n    pass\n"
                "try:\n    do_other()\nexcept Exception:\n    pass\n",
                encoding="utf-8",
            )
            update_baseline(project, scan_project(project)["counts"])
            (project / "a.py").write_text(
                "try:\n    do_thing()\nexcept Exception:\n    pass\n",
                encoding="utf-8",
            )
            fixed = scan_project(project)
            written = update_baseline(project, fixed["counts"])
            self.assertEqual(written["a.py"], 1)
            self.assertEqual(scan_project(project)["verdict"], "findings")

    def test_annotated_site_is_excluded_from_the_ratchet_count(self) -> None:
        with temp_project() as project:
            (project / "a.py").write_text(
                "try:\n"
                "    do_thing()\n"
                "except Exception:  # godmode: swallow-ok best-effort logging path\n"
                "    pass\n",
                encoding="utf-8",
            )
            report = scan_project(project)
            self.assertEqual(report["counts"], {})
            self.assertEqual(report["verdict"], "clean")
            self.assertEqual(len(report["exemptions"]), 1)
            self.assertEqual(
                report["exemptions"][0]["reason"], "best-effort logging path"
            )

    def test_unparsed_files_are_named_in_the_verdict_not_only_the_sibling_field(self) -> None:
        with temp_project() as project:
            (project / "broken.py").write_text("def (:\n", encoding="utf-8")
            report = scan_project(project)
            self.assertEqual(len(report["unparsed"]), 1)
            self.assertEqual(report["verdict"], "clean, 1 files unparsed")

    def test_malformed_baseline_file_is_reported_not_silently_ignored(self) -> None:
        with temp_project() as project:
            (project / "a.py").write_text("def add(a, b):\n    return a + b\n",
                                           encoding="utf-8")
            (project / BASELINE_FILENAME).write_text("not json", encoding="utf-8")
            report = scan_project(project)
            self.assertFalse(report["baseline_exists"])
            self.assertIsNotNone(report["baseline_error"])

    def test_truncation_is_loud_not_a_silent_partial_clean(self) -> None:
        with temp_project() as project:
            (project / "a.py").write_text("def add(a, b):\n    return a + b\n",
                                           encoding="utf-8")
            (project / "b.py").write_text("def sub(a, b):\n    return a - b\n",
                                           encoding="utf-8")
            report = scan_project(project, limit=1)
            self.assertTrue(report["truncated"])
            self.assertEqual(report["candidates"], 2)
            self.assertEqual(report["scanned"], 1)
            self.assertEqual(report["verdict"], "truncated")

    def test_ignored_directories_are_never_scanned(self) -> None:
        with temp_project() as project:
            vendor = project / "node_modules" / "pkg"
            vendor.mkdir(parents=True)
            (vendor / "index.js").write_text(
                "try {\n  x();\n} catch (e) {\n}\n", encoding="utf-8"
            )
            report = scan_project(project)
            self.assertEqual(report["scanned"], 0)
            self.assertEqual(report["verdict"], "clean")


class CliExitCodeTests(unittest.TestCase):
    """Against the real CLI (`godmode_console.main`), not just `scan_project`
    - RULING B3-3-2 is a `cmd_swallow` defect, not a module-level one."""

    def test_a_live_regression_fails_every_invocation_including_update_baseline(self) -> None:
        from godmode_runtime.godmode_console import main

        with isolated_project() as (project, _state, _anchor, _archive):
            (project / "a.py").write_text(
                "try:\n    do_thing()\nexcept Exception:\n    pass\n",
                encoding="utf-8",
            )
            self.assertEqual(
                main(["--project", str(project), "--json", "swallow", "--update-baseline"]),
                0,
            )
            # Regress: a second, unrelated site lands in the same file.
            (project / "a.py").write_text(
                "try:\n    do_thing()\nexcept Exception:\n    pass\n"
                "try:\n    do_other()\nexcept Exception:\n    pass\n",
                encoding="utf-8",
            )
            self.assertEqual(main(["--project", str(project), "--json", "swallow"]), 1)
            # The reviewer's exact probe: --update-baseline right after an
            # un-rescued regression must ALSO exit nonzero. The min()
            # protection genuinely holds the ceiling at 1 (not baselined
            # away), but a 0 exit code here would say "clean" over a live
            # regression - the collapsed observable this scanner exists to
            # catch elsewhere in the codebase.
            self.assertEqual(
                main(["--project", str(project), "--json", "swallow", "--update-baseline"]),
                1,
            )


if __name__ == "__main__":
    unittest.main()
