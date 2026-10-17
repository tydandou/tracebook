"""Fixed retrieval evaluation set: per-case contracts plus a printed baseline.

Cases live in tests/fixtures/retrieval_eval/. Metrics describe deterministic
retrieval on a synthetic corpus; they are not an Agent recall score. A
`known_gap` case documents a current limitation and fails once it passes, so
the fixture never silently overstates or understates today's behavior.
"""

from datetime import date
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import unittest

from plugins.tracebook.skills.tracebook.scripts.capture import CaptureRequest
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import (
    capture, read_context, read_context_for_path, resolve,
)


FIXTURES = Path(__file__).parent / "fixtures" / "retrieval_eval"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _body(page):
    repeat = page.get("body_repeat")
    if repeat is None:
        return page["body"]
    return repeat["text"] * repeat["times"] + page["body_tail"]


class RetrievalEvalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        temporary = TemporaryDirectory(prefix="tbe-")
        cls.addClassCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        cls.root = base / "kb"
        cls.repos, contexts = {}, {}
        for name in ("target", "sibling"):
            cls.repos[name] = base / name
            cls.repos[name].mkdir()
            contexts[name] = resolve(cls.root, cls.repos[name])
        cls.project_ids = {name: context.record.project_id for name, context in contexts.items()}
        for page in _load("corpus.json")["pages"]:
            context = contexts[page.get("project", "target")]
            values = dict(operation="create", scope=page.get("scope", "project"),
                          kind=page.get("kind", "decision"), knowledge_id=page["id"],
                          title=page["title"], body=_body(page),
                          evidence=tuple(page["evidence"]), status=page.get("status", "current"))
            capture(context, CaptureRequest(**values), date(2026, 9, 1))
            revise = page.get("revise")
            if revise is not None:
                values.update(operation="revise", expected_version=1, body=revise["body"])
                capture(context, CaptureRequest(**values), date(2026, 9, revise["day"]))

    def _label(self, item):
        source = item.get("source_project", {}).get("project_id")
        return item["knowledge_id"] + ("@sibling" if source == self.project_ids["sibling"] else "")

    def _read(self, case):
        options = dict(case.get("options", {}))
        if "evidence_paths" in options:
            options["evidence_paths"] = tuple(options["evidence_paths"])
        query = case.get("query", "")
        if case.get("project") == "both":
            return read_context(self.root, tuple(self.project_ids.values()), query, **options)
        return read_context_for_path(self.root, self.repos["target"], query, **options)

    @staticmethod
    def _failures(case, result, labels):
        failures = []
        missing = [value for value in case.get("must_hit", ()) if value not in labels]
        if missing:
            failures.append(f"missing {missing}")
        if "top1" in case and labels[:1] != [case["top1"]]:
            failures.append(f"top1 {labels[:1]} != {case['top1']}")
        noise = [value for value in case.get("must_not_hit", ()) if value in labels]
        if noise:
            failures.append(f"noise {noise}")
        if case.get("expect_empty") and labels:
            failures.append(f"expected empty, got {labels}")
        for field, expected in case.get("expect_fields", {}).items():
            if result.get(field) != expected:
                failures.append(f"{field} {result.get(field)!r} != {expected!r}")
        return failures

    def test_fixed_cases_and_baseline(self):
        cases = _load("cases.json")["cases"]
        totals = dict(hit=0, hit_total=0, top1=0, top1_total=0, noise=0, gaps=0, chars=0)
        elapsed = 0.0
        for case in cases:
            with self.subTest(case=case["id"]):
                started = time.perf_counter()
                result = self._read(case)
                elapsed += time.perf_counter() - started
                labels = [self._label(item) for item in result["current_context"]]
                totals["hit"] += sum(value in labels for value in case.get("must_hit", ()))
                totals["hit_total"] += len(case.get("must_hit", ()))
                if "top1" in case:
                    totals["top1_total"] += 1
                    totals["top1"] += labels[:1] == [case["top1"]]
                totals["noise"] += sum(value in labels for value in case.get("must_not_hit", ()))
                totals["chars"] += result["budget_chars_used"]
                failures = self._failures(case, result, labels)
                if case.get("status") == "known_gap":
                    totals["gaps"] += 1
                    self.assertTrue(failures, f"known_gap now passes; mark it pass: {case['reason']}")
                else:
                    self.assertEqual([], failures, f"query={case.get('query')!r} labels={labels}")
        count = len(cases)
        print(
            f"\nretrieval-eval: {count} cases, "
            f"recall {totals['hit']}/{totals['hit_total']}, "
            f"top1 {totals['top1']}/{totals['top1_total']}, "
            f"noise {totals['noise']}, known_gap {totals['gaps']}, "
            f"avg_chars {totals['chars'] // count}, avg_ms {elapsed * 1000 / count:.1f}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    unittest.main()
