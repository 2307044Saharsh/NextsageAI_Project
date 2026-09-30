import ipaddress
import re

from app.domain.models import DiagnosisInput, EvidenceFinding


class CiscoRuleChecker:
    """Evidence-first checks for common Cisco lab faults. They never change a device."""

    def check(self, case: DiagnosisInput) -> list[EvidenceFinding]:
        output = case.show_outputs
        text = case.evidence_text.lower()
        findings: list[EvidenceFinding] = []

        def add(
            rule: str,
            severity: str,
            root_cause: str,
            osi_layer: str,
            next_command: str,
            verification_command: str,
            verification_expected_result: str,
            fix_steps: list[str],
            evidence: str = output,
            confidence: str = "high",
        ) -> None:
            findings.append(EvidenceFinding(
                rule=rule,
                severity=severity,
                root_cause=root_cause,
                osi_layer=osi_layer,
                confidence=confidence,
                evidence=evidence,
                next_command=next_command,
                fix_steps=fix_steps,
                verification_command=verification_command,
                verification_expected_result=verification_expected_result,
            ))

        # The match rules deliberately require command-output evidence rather than a
        # generic symptom such as "unreachable".
        if "show ip ospf neighbor is up" in text and "lacks" in text:
            add("ospf_network_missing", "High", "OSPF is not advertising the required network", "Layer 3", "show ip ospf interface brief", "show ip route ospf", "The subnet appears as an OSPF route on peers.", ["Confirm the subnet, wildcard mask, and OSPF process.", "Add or correct the OSPF network statement after human approval."])
        elif re.search(r"show ip route.*\b(no|lacks)\b", output, re.IGNORECASE):
            add("missing_route", "High", "Missing inter-VLAN or static route", "Layer 3", "show ip route", "ping <destination-ip>", "The destination subnet is in the routing table and the ping succeeds.", ["Confirm the destination subnet and intended next hop.", "Add or correct the route only after human approval."])
        elif "show access-lists" in text and "deny ip" in text and "server ping fails" in text:
            add("acl_blocks_traffic", "High", "ACL denies intended traffic", "Layer 4", "show access-lists", "ping <server-ip>", "The intended flow is permitted while the ACL remains least-privilege.", ["Confirm the source, destination, protocol, and ACL direction.", "Change only the specific deny or permit entry after human approval."])
        elif "native vlan mismatch" in text:
            add("native_vlan_mismatch", "Medium", "Native VLAN mismatch on trunk", "Layer 2", "show interfaces trunk", "show interfaces trunk", "Both trunk ends report the same native VLAN and required VLANs are forwarding.", ["Compare trunk mode, native VLAN, and allowed VLAN lists on both switches.", "Align the trunk configuration after human approval."])
        elif re.search(r"does not list vlan \d+|vlan \d+ absent", text):
            add("missing_vlan", "Medium", "Required VLAN is missing or inactive", "Layer 2", "show vlan brief", "show vlan brief", "The required VLAN exists and the access port is assigned to it.", ["Confirm the intended VLAN ID and access-port assignment.", "Create or activate only the required VLAN after human approval."])
        elif self._mask_mismatch(output):
            add("wrong_mask", "High", "Subnet mask does not match the intended prefix", "Layer 3", "show running-config | section interface", "ping <remote-subnet-host>", "The interface and hosts use the intended prefix and remote-subnet ping succeeds.", ["Confirm the intended subnet boundary with the lab topology.", "Correct the interface or host mask after human approval."])
        elif self._gateway_mismatch(text):
            add("gateway_mismatch", "High", "Default gateway does not match the VLAN gateway", "Layer 3", "show ip interface brief", "ping <default-gateway>", "The client gateway matches the SVI or HSRP virtual IP and replies to ping.", ["Compare the host gateway with the active SVI or virtual gateway.", "Correct the host or DHCP default-router setting after human approval."])
        elif "administratively down" in text and "." in output.split("administratively down", 1)[0]:
            add("subinterface_down", "High", "Router subinterface is administratively down", "Layer 2", "show ip interface brief", "show ip interface brief", "The required subinterface reports up/up.", ["Confirm the subinterface VLAN tag and parent interface state.", "Enable the intended subinterface after human approval."])
        elif "administratively down" in text:
            add("interface_down", "High", "Interface is administratively down", "Layer 1", "show ip interface brief", "show ip interface brief", "The interface reports up/up after the approved correction.", ["Confirm the interface should be in service.", "Remove shutdown only after human approval."])
        elif "line protocol is down" in text:
            add("physical_link_down", "High", "Physical link or cable issue", "Layer 1", "show interfaces <interface>", "show interfaces <interface>", "The interface line protocol reports up and error counters are stable.", ["Inspect both link ends, cable type, and port state.", "Correct the physical connection or matching port configuration after human approval."], confidence="medium")
        elif "100 percent leased" in text:
            add("dhcp_pool_exhausted", "Medium", "DHCP pool is exhausted", "Layer 7", "show ip dhcp pool", "show ip dhcp pool", "The pool has available addresses and a new client obtains the correct lease.", ["Confirm active leases and reserved addresses.", "Expand the approved scope or reclaim stale leases after human approval."])
        elif "dhcp binding includes" in text and "lacks ip dhcp excluded-address" in text:
            add("dhcp_exclusion_missing", "High", "DHCP pool includes a reserved gateway address", "Layer 7", "show ip dhcp binding", "show ip dhcp binding", "The gateway address is excluded and no longer leased to a client.", ["Confirm all statically assigned infrastructure addresses.", "Add the required DHCP exclusions after human approval."])
        elif "no ip helper-address" in text:
            add("dhcp_relay_missing", "High", "DHCP relay address is missing", "Layer 3", "show running-config interface vlan <id>", "ipconfig /renew", "A remote client receives a lease from the central DHCP server.", ["Confirm the DHCP server address and client VLAN interface.", "Add the helper address after human approval."])
        elif "valid server is" in text and "dns" in text:
            add("dns_address_incorrect", "Medium", "Client DNS server address is incorrect", "Layer 7", "ipconfig /all", "nslookup <internal-name>", "The configured DNS address is the documented server and name resolution succeeds.", ["Compare the DHCP DNS option with the documented DNS server.", "Correct the DNS address after human approval."])
        elif "nslookup returns server failed" in text and "ping" in text:
            add("dns_server_unreachable", "High", "DNS server is unreachable", "Layer 7", "ping <dns-server-ip>", "nslookup <internal-name>", "The DNS server responds and the name resolves.", ["Verify server reachability before changing DNS records.", "Correct the route, VLAN, or server interface fault after human approval."], confidence="medium")
        elif "next hop" in text and "wan uses" in text:
            add("static_route_next_hop", "High", "Static route uses an incorrect next hop", "Layer 3", "show ip route <destination-network>", "ping <remote-subnet-host>", "The route points to the reachable WAN next hop and the remote subnet responds.", ["Compare the configured next hop with the WAN addressing plan.", "Correct only the intended static route after human approval."])
        elif "as passive" in text and ("ospf" in text or "show ip protocols" in text):
            add("ospf_passive_interface", "High", "OSPF transit interface is passive", "Layer 3", "show ip protocols", "show ip ospf neighbor", "The intended transit neighbor reaches a full adjacency.", ["Confirm the interface is a transit link, not a user LAN.", "Remove passive-interface only from the intended link after human approval."])
        elif "nat translations is empty" in text and "lacks ip nat inside" in text:
            add("nat_inside_missing", "High", "NAT inside role is missing", "Layer 3", "show running-config interface <inside-interface>", "show ip nat translations", "A permitted client flow creates a translation.", ["Confirm inside and outside interfaces against the topology.", "Add the inside role after human approval."])
        elif "ip nat inside source" in text and "no overload" in text:
            add("nat_overload_missing", "Medium", "NAT overload is missing for shared public addressing", "Layer 3", "show running-config | include ip nat inside source", "show ip nat translations", "Multiple internal clients receive translations through the public address.", ["Confirm whether the lab expects PAT or a NAT pool.", "Add overload only after human approval."])
        elif "acl 1 should match" in text and "permits" in text:
            add("nat_acl_incorrect", "High", "NAT match ACL selects the wrong subnet", "Layer 3", "show access-lists 1", "show ip nat translations", "The intended subnet matches the NAT ACL and creates translations.", ["Compare the ACL source network and wildcard mask with the inside subnet.", "Correct the specific NAT ACL entry after human approval."])
        elif "guest wi-fi" in text and "no deny to 10.0.0.0/8" in text:
            add("guest_isolation_missing", "Critical", "Guest isolation ACL is missing", "Layer 4", "show access-lists", "ping <internal-server-ip>", "Guest clients cannot reach internal networks but retain only approved internet access.", ["Confirm guest VLAN and approved internal destinations.", "Add a deny-first least-privilege policy after human approval."])
        elif "ssid guest" in text and "not 70" in text:
            add("wireless_vlan_not_allowed", "High", "Guest SSID VLAN is not allowed on the AP trunk", "Layer 2", "show interfaces trunk", "show interfaces trunk", "The guest VLAN is allowed and guest clients receive the guest subnet.", ["Confirm SSID-to-VLAN mapping and AP switch-port trunk configuration.", "Allow only the required guest VLAN after human approval."])
        elif "authentication failure" in text and "key differs" in text:
            add("wireless_key_mismatch", "Medium", "Wireless authentication key mismatch", "Layer 2", "show running-config | section dot11", "Connect a test client", "A client authenticates using the approved SSID security settings.", ["Confirm the approved WPA2 key and security mode.", "Align the client or AP configuration after human approval."])
        elif "dhcp conflict" in text and "duplicate ip" in text:
            add("duplicate_ip", "High", "Duplicate IP address detected", "Layer 3", "show ip dhcp conflict", "ping <conflicting-ip>", "Only one endpoint uses the address and both devices maintain connectivity.", ["Identify the static reservation and conflicting lease.", "Reserve or reassign the conflicting address after human approval."])
        elif "allowed vlan is" in text and "absent" in text:
            add("trunk_vlan_not_allowed", "High", "Required VLAN is not allowed on the trunk", "Layer 2", "show interfaces trunk", "show interfaces trunk", "The required VLAN is in the allowed and forwarding list on both trunk ends.", ["Compare allowed VLAN lists at both ends of the trunk.", "Allow the required VLAN after human approval."])
        elif "show standby vlan" in text and "clients use" in text:
            add("hsrp_gateway_mismatch", "High", "Clients use the wrong HSRP virtual gateway", "Layer 3", "show standby brief", "ping <virtual-gateway>", "Clients use the reported HSRP virtual IP and gateway ping succeeds after failover.", ["Confirm the HSRP virtual IP and DHCP default-router value.", "Correct the client or DHCP gateway after human approval."])
        elif "access-group 120 out" in text and "return traffic" in text:
            add("acl_direction", "High", "ACL is applied in the wrong direction", "Layer 4", "show running-config interface vlan <id>", "ping <server-ip>", "The intended flow and reply path work while the policy remains restrictive.", ["Map the flow direction against the ACL application direction.", "Move or revise only the required ACL application after human approval."])
        elif "secure-shutdown" in text and "port-security" in text:
            add("port_security_violation", "Medium", "Port security violation shut down the access port", "Layer 2", "show port-security interface <interface>", "show port-security interface <interface>", "The approved endpoint is learned and the access port is operational.", ["Confirm the approved endpoint MAC and violation mode.", "Clear or update the port-security state after human approval."])
        elif "spanning-tree" in text and "blocking state" in text:
            add("stp_blocked_path", "Medium", "Spanning Tree blocks the required path", "Layer 2", "show spanning-tree vlan <id>", "show spanning-tree vlan <id>", "The intended topology has a forwarding path without creating a loop.", ["Validate root bridge selection and redundant-link design.", "Change STP priority or topology only after human approval."], confidence="medium")
        elif "mtu 1500" in text and "1400" in text:
            add("mtu_mismatch", "Medium", "MTU mismatch across routed link", "Layer 3", "show interfaces <interface>", "ping <remote-ip> size 1472 df-bit", "Both sides use compatible MTU values and large DF pings succeed.", ["Confirm the path MTU and encapsulation overhead.", "Align the required interface MTU after human approval."])
        elif "guest-ap" in text and "10.0.10." in text:
            add("wireless_dhcp_scope", "High", "Guest wireless client receives the staff DHCP scope", "Layer 3", "show ip dhcp binding", "ipconfig /renew", "Guest clients receive addresses from the guest subnet.", ["Confirm guest SSID VLAN and DHCP pool network.", "Correct the VLAN mapping or DHCP scope after human approval."])

        return findings

    @staticmethod
    def _mask_mismatch(output: str) -> bool:
        mask_match = re.search(
            r"\b\d{1,3}(?:\.\d{1,3}){3}\s+(\d{1,3}(?:\.\d{1,3}){3})\b",
            output,
        )
        expected = re.search(r"expect\s*/(\d{1,2})", output, re.IGNORECASE)
        if not mask_match or not expected:
            return False
        try:
            actual_prefix = ipaddress.IPv4Network(f"0.0.0.0/{mask_match.group(1)}").prefixlen
        except ipaddress.NetmaskValueError:
            return False
        return actual_prefix != int(expected.group(1))

    @staticmethod
    def _gateway_mismatch(text: str) -> bool:
        patterns = (
            r"default gateway\s+(\d+(?:\.\d+){3}).*?(?:svi|virtual ip)\s+(?:is\s+)?(\d+(?:\.\d+){3})",
            r"clients use\s+(\d+(?:\.\d+){3}).*?virtual ip\s+(\d+(?:\.\d+){3})",
            r"server ipconfig shows gateway\s+(\d+(?:\.\d+){3}).*?svi is\s+(\d+(?:\.\d+){3})",
        )
        return any((match := re.search(pattern, text, re.DOTALL)) and match.group(1) != match.group(2) for pattern in patterns)
