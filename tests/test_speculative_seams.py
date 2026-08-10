"""A seam that serves one caller, which is a guess about the future.

"One adapter means a hypothetical seam. Two adapters means a real one." The
graph can check the practical form of that: a module whose symbols are used by
exactly one other file is an abstraction with a single consumer. It may be
right — a module can be young, or genuinely deep — but it is the shape a
speculative interface takes, and nothing here looks for it.

Reported, never refused, and deliberately not automatic. The deletion test that
accompanies this rule in its source — delete the module, and see whether
complexity vanishes or reappears across N callers — is not computable from an
import graph, so it is asked as a question rather than pretended at.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_atlas import build, speculative_seams  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class SeamTests(unittest.TestCase):
    def test_a_module_with_one_consumer_is_reported(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / "gateway.py").write_text("def send():\n    return 1\n", encoding="utf-8")
            (project / "orders.py").write_text("import gateway\n\ngateway.send()\n",
                                               encoding="utf-8")
            report = speculative_seams(build(project))
        self.assertIn("gateway.py", {f["module"] for f in report["findings"]})

    def test_a_module_with_two_consumers_is_a_real_seam(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / "gateway.py").write_text("def send():\n    return 1\n", encoding="utf-8")
            (project / "orders.py").write_text("import gateway\n\ngateway.send()\n",
                                               encoding="utf-8")
            (project / "refunds.py").write_text("import gateway\n\ngateway.send()\n",
                                                encoding="utf-8")
            report = speculative_seams(build(project))
        self.assertNotIn("gateway.py", {f["module"] for f in report["findings"]})

    def test_a_module_nobody_imports_is_not_a_seam_at_all(self) -> None:
        """Zero consumers is what `atlas orphans` already answers, and a
        finding reported by two surfaces gets fixed by neither."""
        with isolated_project() as (project, _s, _a, _archive):
            (project / "lonely.py").write_text("def x():\n    return 1\n", encoding="utf-8")
            report = speculative_seams(build(project))
        self.assertEqual(report["findings"], [])

    def test_a_test_file_does_not_count_as_the_consumer(self) -> None:
        """Every module has a test importing it, so counting tests as
        consumers would make every real seam look real and every speculative
        one look justified."""
        with isolated_project() as (project, _s, _a, _archive):
            (project / "gateway.py").write_text("def send():\n    return 1\n", encoding="utf-8")
            (project / "orders.py").write_text("import gateway\n\ngateway.send()\n",
                                               encoding="utf-8")
            (project / "test_gateway.py").write_text("import gateway\n\ngateway.send()\n",
                                                     encoding="utf-8")
            report = speculative_seams(build(project))
        self.assertIn("gateway.py", {f["module"] for f in report["findings"]})

    def test_a_standard_library_import_is_not_a_seam_of_this_project(self) -> None:
        """`import base64` used once names a module this project does not own
        and cannot delete. Reporting it buries the findings that are actionable
        under a list of the standard library."""
        with isolated_project() as (project, _s, _a, _archive):
            (project / "orders.py").write_text(
                "import base64\nimport difflib\n\nbase64.b64encode(b'')\n", encoding="utf-8")
            report = speculative_seams(build(project))
        self.assertEqual(report["findings"], [], report)

    def test_each_finding_names_its_single_consumer(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / "gateway.py").write_text("def send():\n    return 1\n", encoding="utf-8")
            (project / "orders.py").write_text("import gateway\n\ngateway.send()\n",
                                               encoding="utf-8")
            report = speculative_seams(build(project))
        finding = next(f for f in report["findings"] if f["module"] == "gateway.py")
        self.assertEqual(finding["consumer"], "orders.py")

    def test_each_finding_asks_the_deletion_test(self) -> None:
        """The half a graph cannot answer, asked rather than pretended at."""
        with isolated_project() as (project, _s, _a, _archive):
            (project / "gateway.py").write_text("def send():\n    return 1\n", encoding="utf-8")
            (project / "orders.py").write_text("import gateway\n\ngateway.send()\n",
                                               encoding="utf-8")
            report = speculative_seams(build(project))
        self.assertIn("delete", report["findings"][0]["question"].lower())

    def test_the_report_states_what_it_examined(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / "gateway.py").write_text("def send():\n    return 1\n", encoding="utf-8")
            (project / "orders.py").write_text("import gateway\n\ngateway.send()\n",
                                               encoding="utf-8")
            report = speculative_seams(build(project))
        self.assertGreater(report["modules_examined"], 0)


if __name__ == "__main__":
    unittest.main()
