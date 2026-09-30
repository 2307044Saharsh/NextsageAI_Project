"""Generate AI-vs-ground-truth comparison for all cases using the local fallback provider."""

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.application.rules import CiscoRuleChecker
from app.infrastructure.fallback_provider import FallbackDiagnosisProvider
from app.infrastructure.file_repositories import CsvCaseRepository


def matches_expected(expected: str, actual: str) -> bool:
    expected_lower = expected.lower()
    actual_lower = actual.lower()
    if expected_lower in actual_lower or actual_lower in expected_lower:
        return True
    stop = {"is", "the", "a", "an", "or", "and", "to", "on", "at", "in", "for", "of"}
    keywords = [word for word in re.findall(r"[a-z0-9]+", expected_lower) if word not in stop and len(word) > 2]
    if not keywords:
        return False
    matched = sum(1 for word in keywords if word in actual_lower)
    return matched / len(keywords) >= 0.5


def main() -> None:
    base_dir = ROOT
    cases = CsvCaseRepository(str(base_dir / "data" / "cases.csv")).list_cases()
    provider = FallbackDiagnosisProvider(CiscoRuleChecker())
    output_path = base_dir / "data" / "diagnosis_comparison.csv"

    rows = []
    for case in cases:
        diagnosis = provider.diagnose(case.diagnosis_input())
        rows.append(
            {
                "case_id": case.case_id,
                "expected_fault": case.expected_fault,
                "ai_root_cause": diagnosis.root_cause,
                "osi_layer": diagnosis.osi_layer,
                "confidence": diagnosis.confidence,
                "source": diagnosis.source,
                "matches_expected": matches_expected(case.expected_fault, diagnosis.root_cause),
            }
        )

    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    matched = sum(1 for row in rows if row["matches_expected"])
    print(f"Wrote {output_path} ({matched}/{len(rows)} aligned with expected fault)")


if __name__ == "__main__":
    main()
