import re

from app.domain.models import ChatContext, ChatResponse, ChatTurn


class FallbackChatProvider:
    """Local reasoning engine for open networking conversations."""

    def chat(self, message: str, history: list[ChatTurn], context: ChatContext | None = None) -> ChatResponse:
        text = message.lower()
        reasoning: list[str] = []
        layers: list[str] = []
        commands: list[str] = []
        follow_ups: list[str] = []

        if context and context.case_evidence:
            reasoning.append(
                f"I also have lab ticket {context.case_id} in view: {context.case_title}. I'll weave that in if it helps."
            )

        if self._mentions(text, "dhcp", "api pa", "no ip", "lease"):
            layers = ["Layer 3", "Layer 7"]
            commands = ["show ip dhcp pool", "show ip dhcp binding", "ipconfig /all"]
            reasoning.extend([
                "DHCP problems usually split into 'no address at all' vs 'bad options'.",
                "If the client has APIPA (169.254.x.x), the request likely never reached a server or the pool is empty.",
                "If the client has an address but the wrong gateway or DNS, the scope or relay is misconfigured.",
            ])
            reply = (
                "For DHCP, I'd first check whether the client got any lease at all, then whether the gateway and DNS "
                "options match the VLAN design. A missing helper address on a remote SVI is a classic Packet Tracer gotcha."
            )
            follow_ups = ["Can the client ping its default gateway?", "Is this a local pool or a relayed VLAN?"]
        elif self._mentions(text, "dns", "nslookup", "name resolution", "hostname"):
            layers = ["Layer 7", "Layer 3"]
            commands = ["nslookup <name>", "ipconfig /all", "ping <dns-server-ip>"]
            reasoning.extend([
                "Name resolution fails when DNS is wrong, unreachable, or the underlying IP path is broken.",
                "If ping to the DNS server IP fails, fix reachability before touching DNS records.",
                "If ping works but nslookup fails, suspect the configured DNS address or the record itself.",
            ])
            reply = (
                "DNS issues are often a red herring — I like to ping the DNS server's IP first. "
                "If that works, compare the client's configured DNS with what DHCP or static settings should provide."
            )
            follow_ups = ["Does ping to the DNS IP work?", "What DNS address does the client show?"]
        elif self._mentions(text, "vlan", "trunk", "native vlan", "inter-vlan", "inter vlan"):
            layers = ["Layer 2", "Layer 3"]
            commands = ["show vlan brief", "show interfaces trunk", "show ip route"]
            reasoning.extend([
                "VLAN faults sit at Layer 2 (wrong access port, missing VLAN, trunk mismatch) or Layer 3 (no route between SVIs).",
                "Symptom pattern matters: same-VLAN works but cross-VLAN fails often points to routing or ACL, not the access port.",
                "Trunk issues show up as intermittent or one-directional VLAN failures.",
            ])
            reply = (
                "Tell me whether hosts in the same VLAN can talk. If yes but cross-VLAN fails, I'd look at inter-VLAN "
                "routing and ACLs next. If same-VLAN fails, start with `show vlan brief` and the access-port assignment."
            )
            follow_ups = ["Can hosts in the same VLAN reach each other?", "Is there a router-on-a-stick or L3 switch?"]
        elif self._mentions(text, "acl", "access-list", "access list", "firewall", "deny"):
            layers = ["Layer 4", "Layer 3"]
            commands = ["show access-lists", "show running-config interface vlan <id>"]
            reasoning.extend([
                "ACL symptoms often look like routing problems — traffic reaches the gateway then disappears.",
                "Check both the ACE itself and the direction the ACL is applied (in vs out).",
                "Return traffic failing while forward traffic works is a classic wrong-direction symptom.",
            ])
            reply = (
                "ACL debugging is about mapping the flow: source, destination, protocol, and which interface filters it. "
                "I'd pull `show access-lists` and verify direction on the SVI or interface where traffic should enter."
            )
            follow_ups = ["Does the problem affect all traffic or one protocol?", "Is there an extended ACL on the path?"]
        elif self._mentions(text, "nat", "pat", "overload", "internet", "browse", "public ip"):
            layers = ["Layer 3", "Layer 4"]
            commands = ["show ip nat translations", "show access-lists", "show running-config | include ip nat"]
            reasoning.extend([
                "NAT needs inside/outside roles, a matching ACL, and usually overload for many clients.",
                "Empty translation table with working routing suggests NAT config, not ISP issues.",
                "Wrong ACL subnet is a common lab mistake when only one VLAN cannot browse.",
            ])
            reply = (
                "For NAT I'd verify inside/outside interfaces, the ACL that selects traffic, and whether overload is configured. "
                "`show ip nat translations` after a test ping tells you quickly if translations are being created."
            )
        elif self._mentions(text, "ospf", "eigrp", "routing protocol", "neighbor", "adjacency"):
            layers = ["Layer 3"]
            commands = ["show ip ospf neighbor", "show ip protocols", "show ip route ospf"]
            reasoning.extend([
                "Routing protocol issues split into neighbor formation vs route advertisement.",
                "Passive-interface on a transit link prevents adjacency even when OSPF is enabled.",
                "Missing network statements show up as neighbors up but routes absent for one subnet.",
            ])
            reply = (
                "I'd check neighbors first (`show ip ospf neighbor`), then whether the subnet appears in the routing table. "
                "No neighbor usually means interface down, wrong subnet, passive-interface, or ACL blocking multicast."
            )
        elif self._mentions(text, "wireless", "wifi", "wi-fi", "ssid", "wpa", "access point", "ap "):
            layers = ["Layer 2", "Layer 3"]
            commands = ["show vlan brief", "show interfaces trunk", "show access-lists"]
            reasoning.extend([
                "Wireless issues in labs are often VLAN mapping or guest isolation, not RF magic.",
                "SSID-to-VLAN mismatch gives clients the wrong subnet or no DHCP scope.",
                "Guest reaching internal servers is a policy failure — check VLAN and ACL together.",
            ])
            reply = (
                "In Packet Tracer wireless labs, I usually verify SSID VLAN mapping on the AP trunk, then DHCP scope for that VLAN. "
                "For guest networks, confirm internal destinations are denied by ACL — not just hidden by routing."
            )
        elif self._mentions(text, "gateway", "default route", "hsrp", "svi"):
            layers = ["Layer 3"]
            commands = ["show ip interface brief", "show standby brief", "ping <gateway-ip>"]
            reasoning.extend([
                "Gateway problems show up as 'same subnet works, nothing beyond' or 'can't ping default gateway'.",
                "Compare the client gateway with the active SVI or HSRP virtual IP.",
                "DHCP option 3 (default-router) mismatches are extremely common in labs.",
            ])
            reply = (
                "Compare what the client thinks its gateway is with what the router actually owns on that VLAN. "
                "If HSRP is in play, clients must use the virtual IP — not one router's physical interface."
            )
            follow_ups = ["Can the client ping its configured gateway?", "Is the gateway from DHCP or static config?"]
        elif self._mentions(text, "ping", "reach", "unreachable", "can't connect", "cannot connect", "no connectivity"):
            layers = ["Layer 1", "Layer 2", "Layer 3", "Layer 7"]
            commands = ["ping <gateway>", "ping <destination>", "traceroute <destination>", "show ip interface brief"]
            reasoning.extend([
                "I use a divide-and-conquer path: link up → same subnet → gateway → remote subnet → application (DNS/HTTP).",
                "Getting an IP but failing beyond the gateway usually means routing, ACL, or wrong gateway — not DHCP.",
                "Failing only on large packets can indicate MTU mismatch rather than a total outage.",
            ])
            reply = (
                "Walk the path in order: Can you ping the gateway? A host on the same subnet? The remote subnet? "
                "Each 'yes' narrows the fault domain. Tell me where the first ping fails and we'll reason from there."
            )
            follow_ups = [
                "Does the client have a valid IP and mask?",
                "Where does ping first fail — gateway, remote host, or only by name?",
            ]
        elif self._mentions(text, "osi", "layer", "troubleshoot", "methodology", "approach", "how do i"):
            layers = ["Layer 1", "Layer 2", "Layer 3", "Layer 4", "Layer 7"]
            commands = ["show ip interface brief", "show vlan brief", "show ip route", "show access-lists"]
            reasoning.extend([
                "Good troubleshooting moves down the stack only after ruling out the layer above.",
                "Physical/link (L1) → switching/VLAN (L2) → IP/routing (L3) → ACL/firewall (L4) → apps/DNS (L7).",
                "Collect one show command at a time; each result should confirm or eliminate a hypothesis.",
            ])
            reply = (
                "My go-to flow: confirm interface status, then VLAN membership, then routing, then ACLs, then DNS/apps. "
                "Ask me about any step — or paste show output and we'll interpret it together."
            )
        else:
            layers = ["Layer 2", "Layer 3", "Layer 7"]
            commands = ["show ip interface brief", "show vlan brief", "show ip route"]
            reasoning.extend([
                "The question isn't tied to a single lab ticket, so I'm using general Cisco troubleshooting patterns.",
                "I'll narrow hypotheses once I know symptoms, topology, and any show output you have.",
                "Nothing here changes your devices — this is reasoning only until a human approves a fix.",
            ])
            reply = (
                "I'm not limited to the 32 lab tickets — ask me about VLANs, routing, DHCP, DNS, NAT, ACLs, wireless, "
                "or paste your own symptoms and show output. What are you trying to fix or understand?"
            )
            follow_ups = [
                "What symptom are you seeing?",
                "Do you have any show command output to share?",
                "Is this a Packet Tracer lab or a real design question?",
            ]

        if context and context.case_evidence and context.case_id:
            reply += f" (I'm also aware of {context.case_id} if you want to tie this back to that ticket.)"

        return ChatResponse(
            reply=reply,
            reasoning=reasoning,
            likely_layers=layers,
            suggested_commands=commands,
            follow_up_questions=follow_ups,
            case_context_used=bool(context and context.case_evidence),
            source="fallback",
            safety_note="This is advisory reasoning only. A named human must review before any configuration change.",
        )

    @staticmethod
    def _mentions(text: str, *keywords: str) -> bool:
        return any(keyword in text for keyword in keywords)
