from app.application.rules import CiscoRuleChecker
from app.domain.models import Case


def test_checker_detects_interface_down():
    case = Case(
        case_id="T1",
        title="test",
        symptom="server unreachable",
        topology_note="",
        show_outputs="GigabitEthernet0/1 is administratively down",
        expected_fault="",
        osi_layer="Layer 1",
        concept="Interface",
        severity="High",
    )
    rules = {finding.rule for finding in CiscoRuleChecker().check(case.diagnosis_input())}
    assert "interface_down" in rules


def test_checker_detects_missing_route():
    case = Case(
        case_id="T2",
        title="test",
        symptom="cannot reach server",
        topology_note="",
        show_outputs="show ip route has no 10.10.40.0/24 route",
        expected_fault="",
        osi_layer="Layer 3",
        concept="Routing",
        severity="High",
    )
    rules = {finding.rule for finding in CiscoRuleChecker().check(case.diagnosis_input())}
    assert "missing_route" in rules


def test_checker_detects_gateway_mismatch():
    case = Case(
        case_id="T3",
        title="test",
        symptom="cannot ping gateway",
        topology_note="",
        show_outputs="ipconfig shows default gateway 192.168.50.1; SVI is 192.168.50.254",
        expected_fault="",
        osi_layer="Layer 3",
        concept="Gateway",
        severity="High",
    )
    rules = {finding.rule for finding in CiscoRuleChecker().check(case.diagnosis_input())}
    assert "gateway_mismatch" in rules
