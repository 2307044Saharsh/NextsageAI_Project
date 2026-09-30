"""
Cybersecurity Validator MCP Server
Validates network configurations against security best practices and NIST/CIS standards.
"""

import json
import re
from typing import Any
from dataclasses import dataclass


@dataclass
class SecurityFinding:
    """Security validation finding"""
    issue_type: str  # vulnerability, misconfiguration, best_practice, standard_violation
    severity: str    # critical, high, medium, low, info
    title: str
    description: str
    affected_component: str
    recommendation: str
    standard: str    # NIST, CIS, RFC, IANA


class CiscoSecurityValidator:
    """Validates Cisco configurations for security issues"""

    def __init__(self):
        self.findings: list[SecurityFinding] = []

    def validate_acl(self, acl_config: str, direction: str = "inbound") -> list[SecurityFinding]:
        """Check ACL for security issues"""
        findings = []

        # Check for overly permissive ACLs
        if "permit ip any any" in acl_config.lower():
            findings.append(SecurityFinding(
                issue_type="misconfiguration",
                severity="critical",
                title="Overly Permissive ACL Rule",
                description="ACL contains 'permit ip any any' which allows all traffic",
                affected_component="ACL",
                recommendation="Replace with specific permit rules; use least-privilege principle",
                standard="CIS Cisco IOS 15 Benchmarks"
            ))

        # Check for unlogged deny rules
        if "deny" in acl_config.lower() and "log" not in acl_config.lower():
            findings.append(SecurityFinding(
                issue_type="best_practice",
                severity="medium",
                title="Deny Rules Not Logged",
                description="Denied traffic should be logged for security monitoring",
                affected_component="ACL",
                recommendation="Add 'log' keyword to deny rules for audit trail",
                standard="NIST SP 800-41 Guidelines on Firewalls and Firewall Policy"
            ))

        return findings

    def validate_nat(self, nat_config: str) -> list[SecurityFinding]:
        """Check NAT configuration for security issues"""
        findings = []

        # Check for missing inside/outside designation
        if "lacks ip nat inside" in nat_config.lower() or "missing ip nat inside" in nat_config.lower():
            findings.append(SecurityFinding(
                issue_type="misconfiguration",
                severity="high",
                title="Missing NAT Inside Designation",
                description="Internal network not properly designated with 'inside' keyword",
                affected_component="NAT",
                recommendation="Configure 'ip nat inside' on internal interfaces",
                standard="RFC 1918 Private IP Space Usage"
            ))

        if "lacks ip nat outside" in nat_config.lower() or "missing ip nat outside" in nat_config.lower():
            findings.append(SecurityFinding(
                issue_type="misconfiguration",
                severity="high",
                title="Missing NAT Outside Designation",
                description="External network not properly designated with 'outside' keyword",
                affected_component="NAT",
                recommendation="Configure 'ip nat outside' on external interfaces",
                standard="RFC 1918 Private IP Space Usage"
            ))

        # Check for dynamic NAT overload
        if "ip nat inside source" in nat_config.lower() and "no overload" in nat_config.lower():
            findings.append(SecurityFinding(
                issue_type="best_practice",
                severity="medium",
                title="Consider NAT Overload",
                description="Static NAT exposes internal IP structure; dynamic PAT better hides topology",
                affected_component="NAT",
                recommendation="Use 'ip nat inside source list X pool Y overload' for better anonymization",
                standard="NIST SP 800-41 Network Address Translation Guidelines"
            ))

        return findings

    def validate_vlan(self, vlan_config: dict) -> list[SecurityFinding]:
        """Check VLAN configuration for security issues"""
        findings = []

        # Check for default VLAN usage
        if vlan_config.get("vlan_id") == 1:
            findings.append(SecurityFinding(
                issue_type="best_practice",
                severity="high",
                title="Using Default VLAN 1",
                description="Default VLAN 1 should not be used for user traffic or management",
                affected_component="VLAN 1",
                recommendation="Segregate traffic into dedicated VLANs; disable VLAN 1 where possible",
                standard="CIS Cisco IOS 15 Benchmarks"
            ))

        # Check for VLAN trunks on access ports
        if vlan_config.get("mode") == "access" and vlan_config.get("allowed_vlans"):
            findings.append(SecurityFinding(
                issue_type="misconfiguration",
                severity="high",
                title="Access Port Configured as Trunk",
                description="Access port should only belong to one VLAN; trunk mode allows multi-VLAN",
                affected_component=f"Interface {vlan_config.get('interface', 'unknown')}",
                recommendation="Use 'switchport mode access' and 'switchport access vlan X'",
                standard="CIS Cisco IOS 15 Benchmarks"
            ))

        # Check for native VLAN mismatch (VLAN hopping vulnerability)
        if vlan_config.get("native_vlan_mismatch"):
            findings.append(SecurityFinding(
                issue_type="vulnerability",
                severity="critical",
                title="Native VLAN Mismatch - Potential VLAN Hopping",
                description="Native VLAN mismatch between switches allows unauthorized VLAN access",
                affected_component="Trunk Port",
                recommendation="Ensure native VLAN is consistent across trunk links; consider changing from default",
                standard="NIST SP 800-41 VLAN Hopping Prevention"
            ))

        return findings

    def validate_interface_security(self, interface_config: dict) -> list[SecurityFinding]:
        """Check interface security settings"""
        findings = []

        # Check for port security
        if interface_config.get("switchport_mode") == "access":
            if interface_config.get("port_security") is False:
                findings.append(SecurityFinding(
                    issue_type="best_practice",
                    severity="medium",
                    title="Port Security Not Enabled",
                    description="Access port lacks port security to prevent MAC address spoofing",
                    affected_component=f"Interface {interface_config.get('name', 'unknown')}",
                    recommendation="Enable 'switchport port-security' with appropriate MAC limits",
                    standard="CIS Cisco IOS 15 Benchmarks"
                ))

        # Check for CDP/LLDP on untrusted interfaces
        if interface_config.get("external") and not interface_config.get("cdp_disabled"):
            findings.append(SecurityFinding(
                issue_type="best_practice",
                severity="medium",
                title="CDP/LLDP Enabled on External Interface",
                description="Device discovery protocols can leak topology information to attackers",
                affected_component=f"Interface {interface_config.get('name', 'unknown')}",
                recommendation="Disable CDP/LLDP on external interfaces: 'no cdp enable'",
                standard="NIST SP 800-41 Network Device Hardening"
            ))

        return findings

    def validate_routing_security(self, routing_config: dict) -> list[SecurityFinding]:
        """Check routing configuration for security issues"""
        findings = []

        # Check for routing protocol authentication
        protocol = routing_config.get("protocol", "").lower()
        if protocol in ["ospf", "bgp", "eigrp"]:
            if not routing_config.get("authentication"):
                findings.append(SecurityFinding(
                    issue_type="vulnerability",
                    severity="high",
                    title=f"Routing Protocol {protocol.upper()} Without Authentication",
                    description=f"{protocol.upper()} updates can be spoofed without authentication",
                    affected_component=f"Routing Protocol: {protocol.upper()}",
                    recommendation=f"Enable authentication: 'ip ospf authentication-key' or MD5 authentication",
                    standard="RFC 2154 OSPF Authentication, RFC 4271 BGP-4"
                ))

        # Check for route filtering
        if not routing_config.get("inbound_filter") and not routing_config.get("outbound_filter"):
            findings.append(SecurityFinding(
                issue_type="best_practice",
                severity="medium",
                title="No Route Filtering Configured",
                description="Routes not filtered; can receive unexpected/malicious routes",
                affected_component=f"Routing: {protocol.upper()}",
                recommendation="Implement inbound and outbound route filters/prefix lists",
                standard="NIST SP 800-41 BGP Route Filtering Best Practices"
            ))

        return findings

    def validate_fix_steps(self, original_issue: str, fix_steps: list[str]) -> list[SecurityFinding]:
        """Validate proposed fix steps for security implications"""
        findings = []
        fix_text = "\n".join(fix_steps).lower()

        # Check if fix involves disabling security features
        if any(term in fix_text for term in ["disable", "remove", "delete", "no access-list", "no ip access-group"]):
            # Only flag if it's removing security features
            if any(sec_term in fix_text for sec_term in ["acl", "access", "security", "port-security"]):
                findings.append(SecurityFinding(
                    issue_type="best_practice",
                    severity="high",
                    title="Fix May Reduce Security Posture",
                    description="Proposed fix involves disabling or removing security controls",
                    affected_component="Configuration Change",
                    recommendation="Verify security impact before applying; consider alternatives that maintain security",
                    standard="Change Management Best Practices"
                ))

        # Check if fix opens new network paths without ACLs
        if "remove acl" in fix_text or "delete access-list" in fix_text:
            findings.append(SecurityFinding(
                issue_type="best_practice",
                severity="high",
                title="ACL Removal Requires Mitigation",
                description="Removing an ACL without replacement leaves path unprotected",
                affected_component="Access Control",
                recommendation="Replace removed ACL with alternative security control or verify network isolation",
                standard="Defense in Depth Principle"
            ))

        return findings

    def validate_case(self, case_data: dict) -> dict:
        """Comprehensive validation of a network troubleshooting case"""
        all_findings = []

        # Analyze show outputs for security issues
        show_outputs = case_data.get("show_outputs", "").lower()

        # Check ACLs in output
        if "access-list" in show_outputs or "acl" in show_outputs:
            all_findings.extend(self.validate_acl(show_outputs))

        # Check NAT configuration
        if "nat" in show_outputs:
            all_findings.extend(self.validate_nat(show_outputs))

        # Check VLAN configuration only where a specific VLAN ID is evidenced.
        vlan_id = self._extract_vlan_id(show_outputs)
        if vlan_id is not None:
            all_findings.extend(self.validate_vlan({"vlan_id": vlan_id}))

        # Do not infer missing port security merely because output mentions an interface.
        if "port-security disabled" in show_outputs:
            all_findings.extend(self.validate_interface_security({"name": "unknown", "switchport_mode": "access", "port_security": False}))

        # Validate fix steps
        fix_steps = case_data.get("fix_steps", []) if isinstance(case_data.get("fix_steps"), list) else []
        all_findings.extend(self.validate_fix_steps(case_data.get("expected_fault", ""), fix_steps))

        result = {
            "case_id": case_data.get("case_id"),
            "security_findings": [
                {
                    "issue_type": f.issue_type,
                    "severity": f.severity,
                    "title": f.title,
                    "description": f.description,
                    "affected_component": f.affected_component,
                    "recommendation": f.recommendation,
                    "standard": f.standard,
                }
                for f in all_findings
            ],
            "severity_summary": self._summarize_severities(all_findings),
            "compliance_status": self._check_compliance(all_findings),
        }
        result["overall_risk"] = self._calculate_risk(result, {"diagnosis_severity_summary": {}})
        return result

    def _extract_vlan_id(self, text: str) -> int | None:
        """Extract VLAN ID from text"""
        match = re.search(r"vlan\s+(\d+)", text)
        return int(match.group(1)) if match else None

    def _summarize_severities(self, findings: list) -> dict:
        """Count findings by severity"""
        summary = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for finding in findings:
            if finding.severity in summary:
                summary[finding.severity] += 1
        return summary

    def _check_compliance(self, findings: list) -> dict:
        """Check compliance status"""
        has_critical = any(f.severity == "critical" for f in findings)
        has_high = any(f.severity == "high" for f in findings)

        return {
            "compliant": not (has_critical or has_high),
            "compliant_with_exceptions": not has_critical,
            "standards_referenced": list(set(f.standard for f in findings)),
        }
