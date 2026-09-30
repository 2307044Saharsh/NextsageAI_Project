from app.domain.models import Case, ChatContext, ChatResponse, ChatTurn, DashboardSummary, Diagnosis, EvidenceFinding, Review
from app.domain.ports import CaseRepository, ChatProvider, DiagnosisProvider, ReviewRepository


class TroubleshootingService:
    def __init__(
        self,
        cases: CaseRepository,
        reviews: ReviewRepository,
        provider: DiagnosisProvider,
        chat_provider: ChatProvider | None = None,
        responsible_ai_log=None,
    ):
        self.cases = cases
        self.reviews = reviews
        self.provider = provider
        self.chat_provider = chat_provider
        self.responsible_ai_log = responsible_ai_log
        self._last_diagnoses: dict[str, Diagnosis] = {}

    def list_cases(self) -> list[Case]:
        return self.cases.list_cases()

    def diagnose(self, case_id: str) -> Diagnosis:
        case = self.cases.get_case(case_id)
        if not case:
            raise KeyError(case_id)
        diagnosis = self.provider.diagnose(case.diagnosis_input())
        self._last_diagnoses[case_id] = diagnosis
        return diagnosis

    def validate(self, case_id: str) -> list[EvidenceFinding]:
        case = self.cases.get_case(case_id)
        if not case:
            raise KeyError(case_id)
        checker = getattr(self.provider, "checker", None)
        if not checker:
            return []
        return checker.check(case.diagnosis_input())

    def review(self, case_id: str, review: Review) -> Review:
        if not self.cases.get_case(case_id):
            raise KeyError(case_id)
        if review.case_id != case_id:
            raise ValueError("Review case does not match URL case")
        diagnosis = self._last_diagnoses.get(case_id)
        if not diagnosis:
            raise ValueError("Run a diagnosis before recording a human review")
        return self.reviews.save_review(review.model_copy(update={"diagnosis_snapshot": diagnosis}))

    def chat(self, message: str, history: list[ChatTurn], case_id: str | None = None, include_case_context: bool = True) -> ChatResponse:
        if not self.chat_provider:
            raise RuntimeError("Chat provider is not configured")
        context = None
        if case_id and include_case_context:
            case = self.cases.get_case(case_id)
            if case:
                context = ChatContext(
                    case_id=case.case_id,
                    case_title=case.title,
                    case_evidence=case.diagnosis_input().evidence_text,
                )
        return self.chat_provider.chat(message, history, context)

    def summary(self) -> DashboardSummary:
        cases = self.cases.list_cases()
        reviews = self.reviews.list_reviews()
        latest_reviews: dict[str, Review] = {}
        for review in reviews:
            previous = latest_reviews.get(review.case_id)
            if not previous or review.reviewed_at >= previous.reviewed_at:
                latest_reviews[review.case_id] = review
        status = {key: 0 for key in ("Pending", "Accepted", "Edited", "Rejected")}
        for review in latest_reviews.values():
            status[review.status] = status.get(review.status, 0) + 1
        status["Pending"] = max(0, len(cases) - len(latest_reviews))
        reviewed = [review for review in latest_reviews.values() if review.status != "Pending"]
        agreement = sum(review.status == "Accepted" for review in reviewed) / len(reviewed) if reviewed else 0.0
        correction_status = self.responsible_ai_log.status_counts() if self.responsible_ai_log else {}
        return DashboardSummary(
            total_cases=len(cases),
            reviewed_cases=len(reviewed),
            agreement_rate=round(agreement * 100, 1),
            by_concept=self._count(cases, "concept"),
            by_severity=self._count(cases, "severity"),
            review_status=status,
            responsible_ai_corrections=sum(correction_status.values()),
            correction_status=correction_status,
        )

    def get_spreadsheet(self) -> list[dict]:
        cases = self.cases.list_cases()
        reviews = self.reviews.list_reviews()
        latest_reviews: dict[str, Review] = {}
        for review in reviews:
            previous = latest_reviews.get(review.case_id)
            if not previous or review.reviewed_at >= previous.reviewed_at:
                latest_reviews[review.case_id] = review

        rows = []
        for case in cases:
            rev = latest_reviews.get(case.case_id)
            ai_diag = None
            if rev and rev.diagnosis_snapshot:
                ai_diag = rev.diagnosis_snapshot.root_cause
            elif case.case_id in self._last_diagnoses:
                ai_diag = self._last_diagnoses[case.case_id].root_cause
            else:
                ai_diag = "Pending diagnosis"

            rows.append({
                "case_id": case.case_id,
                "title": case.title,
                "concept": case.concept,
                "osi_layer": case.osi_layer,
                "severity": case.severity,
                "symptom": case.symptom,
                "expected_fault": case.expected_fault,
                "ai_diagnosis": ai_diag,
                "status": rev.status if rev else "Pending",
                "reviewer_name": rev.reviewer_name if rev else "—",
                "reviewed_at": rev.reviewed_at.isoformat() if rev else "—",
                "notes": (rev.reason or rev.corrected_diagnosis) if rev else "—",
            })
        return rows

    @staticmethod
    def _count(cases: list[Case], field: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for case in cases:
            value = getattr(case, field)
            counts[value] = counts.get(value, 0) + 1
        return counts

