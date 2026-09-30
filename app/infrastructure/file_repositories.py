import csv
import json
from pathlib import Path

from app.domain.models import Case, Review


class CsvCaseRepository:
    def __init__(self, path: str):
        self.path = Path(path)

    def list_cases(self) -> list[Case]:
        with self.path.open(newline="", encoding="utf-8") as file:
            return [Case.model_validate(row) for row in csv.DictReader(file)]

    def get_case(self, case_id: str) -> Case | None:
        return next((case for case in self.list_cases() if case.case_id == case_id), None)


class JsonReviewRepository:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def list_reviews(self) -> list[Review]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return [Review.model_validate(item) for item in payload]

    def save_review(self, review: Review) -> Review:
        reviews = self.list_reviews()
        reviews.append(review)
        self.path.write_text(
            json.dumps([item.model_dump(mode="json") for item in reviews], indent=2),
            encoding="utf-8",
        )
        return review


class CsvResponsibleAiLog:
    """Read-only summary of the submitted corrected-AI examples."""

    def __init__(self, path: str):
        self.path = Path(path)

    def status_counts(self) -> dict[str, int]:
        if not self.path.exists():
            return {}
        with self.path.open(newline="", encoding="utf-8") as file:
            counts: dict[str, int] = {}
            for row in csv.DictReader(file):
                status = row["review_status"]
                counts[status] = counts.get(status, 0) + 1
            return counts
