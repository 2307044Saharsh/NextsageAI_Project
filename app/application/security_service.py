"""
Security validation service for network troubleshooting cases
"""

from app.domain.models import Case
from app.infrastructure.security_validator_mcp import CiscoSecurityValidator


class SecurityValidationService:
    """Service for validating network configurations against security standards"""

    def __init__(self):
        self.validator = CiscoSecurityValidator()

    def validate_case(self, case: Case) -> dict:
        """Validate a case for security issues"""
        case_dict = {
            "case_id": case.case_id,
            "title": case.title,
            "symptom": case.symptom,
            "show_outputs": case.show_outputs,
            "expected_fault": case.expected_fault,
            "fix_steps": [],
        }

        result = self.validator.validate_case(case_dict)

        # Add metadata
        result["title"] = case.title
        result["concept"] = case.concept
        result["severity"] = case.severity
        result["osi_layer"] = case.osi_layer

        return result

    def validate_diagnosis(self, case: Case, diagnosis: dict) -> dict:
        """Validate a diagnosis for security implications"""
        # Combine case validation with diagnosis-specific checks
        case_validation = self.validate_case(case)

        # Add diagnosis-specific security checks
        fix_steps = diagnosis.get("fix_steps", [])
        root_cause = diagnosis.get("root_cause", "")

        # Check if diagnosis introduces security risks
        diagnosis_findings = self.validator.validate_fix_steps(root_cause, fix_steps)

        diagnosis_validation = {
            "diagnosis_security_findings": [
                {
                    "issue_type": f.issue_type,
                    "severity": f.severity,
                    "title": f.title,
                    "description": f.description,
                    "recommendation": f.recommendation,
                    "standard": f.standard,
                }
                for f in diagnosis_findings
            ],
            "diagnosis_severity_summary": self.validator._summarize_severities(diagnosis_findings),
        }

        # Merge results
        return {
            **case_validation,
            **diagnosis_validation,
            "overall_risk": self._calculate_risk(case_validation, diagnosis_validation),
        }

    def _calculate_risk(self, case_val: dict, diagnosis_val: dict) -> str:
        """Calculate overall security risk"""
        case_critical = case_val["severity_summary"].get("critical", 0)
        case_high = case_val["severity_summary"].get("high", 0)
        diag_critical = diagnosis_val["diagnosis_severity_summary"].get("critical", 0)
        diag_high = diagnosis_val["diagnosis_severity_summary"].get("high", 0)

        total_critical = case_critical + diag_critical
        total_high = case_high + diag_high

        if total_critical > 0:
            return "CRITICAL"
        elif total_high > 2:
            return "HIGH"
        elif total_high > 0:
            return "MEDIUM"
        else:
            return "LOW"
