"""Local MCP tools for evidence-only network troubleshooting assistance."""

from mcp.server import MCPServer

from app.application.rules import CiscoRuleChecker
from app.domain.models import DiagnosisInput

mcp = MCPServer(
    "NetSage Evidence Tools",
    instructions="These tools inspect supplied lab evidence only. They never connect to or change network devices.",
)
checker = CiscoRuleChecker()


@mcp.tool()
def validate_network_evidence(
    case_id: str,
    title: str,
    symptom: str,
    topology_note: str,
    show_outputs: str,
) -> dict:
    """Return deterministic, evidence-backed findings for a Cisco-style lab case."""
    case = DiagnosisInput(
        case_id=case_id,
        title=title,
        symptom=symptom,
        topology_note=topology_note,
        show_outputs=show_outputs,
    )
    findings = checker.check(case)
    return {
        "tool": "validate_network_evidence",
        "case_id": case_id,
        "finding_count": len(findings),
        "findings": [finding.model_dump() for finding in findings],
        "safety_note": "Findings are advisory. A named human must approve any configuration change and verify the result.",
    }


@mcp.resource("netsage://safety-policy")
def safety_policy() -> str:
    """Return NetSage's human-oversight policy."""
    return (
        "NetSage tools are read-only and evidence-based. They do not apply network configuration. "
        "A named human reviewer must accept, edit, or reject each diagnosis before a lab fix is applied."
    )
