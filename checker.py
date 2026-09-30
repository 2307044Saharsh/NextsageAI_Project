import sys
from pathlib import Path

from app.application.rules import CiscoRuleChecker
from app.infrastructure.file_repositories import CsvCaseRepository


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/cases.csv")
    checker = CiscoRuleChecker()
    for case in CsvCaseRepository(str(path)).list_cases():
        findings = checker.check(case.diagnosis_input())
        print(f"{case.case_id}: " + ("; ".join(f"{item.rule} ({item.severity})" for item in findings) or "no deterministic finding"))
