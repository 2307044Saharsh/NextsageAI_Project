from app.application.rules import CiscoRuleChecker
from app.domain.models import Diagnosis, DiagnosisInput


class FallbackDiagnosisProvider:
    """Deterministic, evidence-only fallback used when a model is unavailable."""

    def __init__(self, checker: CiscoRuleChecker):
        self.checker = checker

    def diagnose(self, case: DiagnosisInput) -> Diagnosis:
        findings = self.checker.check(case)
        if findings:
            finding = findings[0]
            alternatives = [item.root_cause for item in findings[1:4]]
            return Diagnosis(
                root_cause=finding.root_cause,
                osi_layer=finding.osi_layer,
                confidence=finding.confidence,
                evidence=[finding.evidence],
                next_command=finding.next_command,
                fix_steps=finding.fix_steps,
                alternative_hypotheses=alternatives,
                verification_command=finding.verification_command,
                verification_expected_result=finding.verification_expected_result,
                source="fallback",
            )

        return Diagnosis(
            root_cause="Insufficient command evidence for a safe diagnosis",
            osi_layer="Unknown",
            confidence="low",
            evidence=[case.show_outputs],
            next_command="show running-config | section interface",
            fix_steps=[
                "Collect the requested command output before changing configuration.",
                "Have a named reviewer compare the evidence with the lab topology.",
            ],
            alternative_hypotheses=[],
            verification_command="ping <known-reachable-endpoint>",
            verification_expected_result="Use the result as additional evidence; do not apply a fix until review is complete.",
            source="fallback",
        )
