# NetSage AI

**Network troubleshooting copilot for Cisco Packet Tracer labs. Built with a hard rule: it can never touch your devices.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141.1-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com/)
[![MCP](https://img.shields.io/badge/MCP-2.x%20Streamable%20HTTP-8A2BE2.svg)](https://modelcontextprotocol.io/)
[![Tests](https://img.shields.io/badge/tests-pytest%20passing-success.svg?logo=pytest)](https://docs.pytest.org/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## What this actually is

Junior network engineers can recite IOS commands in their sleep. What trips them up is the gap between *"PC can't reach the web server in VLAN 30"* and figuring out which of the twelve things that could cause that is actually broken.

NetSage reads your `show` command output, cross-references it against a rule engine and an LLM, and tells you where to look next. It does **not** fix anything. It cannot. There's no write access to any control plane — by design, not by accident.

Every diagnosis it produces requires a human to explicitly approve, edit, or reject it before it goes anywhere. That's not a feature checkbox. It's the entire point.

---

## The non-negotiables

Before anything else: here's what the system will never do, regardless of what you ask it.

- Issue `configure terminal`, `write memory`, `reload`, or any other write command
- Invent facts that aren't in the `show` output you gave it
- Let a remediation step execute without a named reviewer signing off
- Suggest "read-only next steps" that are actually disruptive

Rejected and edited suggestions get logged to `data/responsible_ai_log.csv` with the reason. That log is how you catch the model hallucinating and improve prompts over time.

---

## How it works

```
Symptom + show outputs
        │
        ▼
Deterministic rule check (regex, no LLM)
        │
        ▼
Multi-tier LLM diagnosis
  ├─ Tier 1: Hugging Face (Llama-3.2-3B-Instruct)
  ├─ Tier 2: Local Ollama (air-gapped fallback)
  └─ Tier 3: CiscoRuleChecker (zero deps, always works)
        │
        ▼
NIST SP 800-53 / CIS benchmark security check
        │
        ▼
Human reviewer: Accept / Edit / Reject
        │
        ▼
Approved verification steps only
```

The deterministic checker runs first, every time. If it catches the problem (gateway mismatch, missing OSPF network statement, etc.), you get an answer immediately. The LLM is for the cases that don't pattern-match cleanly.

---

## Getting started

**Requirements:** Python 3.10+. Ollama and a HF token are optional — the deterministic fallback works without either.

```bash
git clone https://github.com/your-org/netsage-ai.git
cd netsage-ai

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — set HF_API_TOKEN if you want cloud inference
# Set AI_BACKEND=fallback if you just want the rule engine

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`. That's it.

**`.env` options:**

```ini
# AI_BACKEND: auto | huggingface | ollama | fallback
AI_BACKEND=auto

HF_API_TOKEN=hf_...
HF_MODEL=meta-llama/Llama-3.2-3B-Instruct

OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2:latest

ALLOWED_ORIGINS=http://localhost:8000
```

---

## The benchmark dataset

32 Packet Tracer lab cases in `data/cases.csv`. Hand-curated, ground-truth validated, covering OSI Layers 1–7. Not generated.

| Domain | Cases | What's actually in there |
|---|:---:|---|
| VLAN & Trunking | 5 | Native VLAN mismatch, missing access VLAN, VTP domain errors |
| Gateway & Subnetting | 4 | /24 vs /25 masks, SVI/gateway mismatches, HSRP misconfig |
| Routing Protocols | 5 | Bad static routes, OSPF network statements, passive interface bugs |
| ACL & Security | 4 | Implicit deny, wrong ACL direction, port security violations |
| DHCP | 4 | Pool exhaustion, missing exclusions, relay agent missing |
| DNS | 2 | Typo in server IP, unreachable server route |
| NAT / PAT | 3 | Missing `ip nat inside`, missing `overload`, bad ACL filter |
| Wireless & Isolation | 3 | Guest leakage, SSID-to-VLAN mapping, WPA2 PSK mismatch |
| Physical / Interface | 2 | Admin shutdown, line protocol down |

Run the checker headless against all 32:

```bash
python checker.py
# CASE-001: missing_route (High)
# CASE-002: acl_blocks_traffic (High)
# ...
```

---

## Human review log — the cases where the AI was wrong

These are documented, not buried. This is the responsible AI log in action:

| Case | What the AI said | What was actually wrong | Outcome |
|---|---|---|:---:|
| CASE-002 | Missing route | ACL blocking traffic at Layer 4 — routing table was fine | Edited |
| CASE-006 | DHCP server down | Client had a valid lease; gateway was wrong (`.1` vs `.254`) | Edited |
| CASE-012 | DNS daemon crashed | DHCP was handing out a typo'd DNS IP (`10.0.90.99` vs `.10`) | Edited |
| CASE-020 | Add broad `permit` ACL | That would have exposed internal subnets to guest Wi-Fi | **Rejected** |
| CASE-030 | OSPF routing failure | MTU mismatch — small pings worked, jumbo pings dropped | Edited |

CASE-020 is the important one. The AI proposed `permit ip any any` as a fix. A reviewer caught it, rejected it, and logged why. That's the loop working correctly.

---

## MCP integration

NetSage runs a native MCP 2.x Streamable HTTP server at `/mcp`. Works with Claude Desktop, Cursor, or any MCP-compatible agent.

**Tool exposed:**

```json
{
  "name": "validate_network_evidence",
  "description": "Deterministic inspection of Cisco show outputs for misconfigurations.",
  "inputSchema": {
    "required": ["case_id", "symptom", "show_outputs"]
  }
}
```

**Claude Desktop config:**

```json
{
  "mcpServers": {
    "netsage-ai": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

---

## API

| Method | Endpoint | What it does |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/cases` | All 32 lab cases |
| POST | `/api/diagnose` | Run AI diagnosis on a case |
| GET | `/api/cases/{id}/validate` | Deterministic rule check only |
| POST | `/api/cases/{id}/review` | Submit Accept / Edit / Reject |
| POST | `/api/chat` | Conversational assistant (ticket-aware) |
| GET | `/api/ai/status` | Which backend is active right now |
| GET | `/api/dashboard` | Summary stats across all cases |
| GET | `/api/security/validate/{id}` | NIST + CIS compliance check |

---

## Tests

```bash
pytest -v
pytest --cov=app tests/   # with coverage
```

Four test suites: API contracts, deterministic rule engine, AI fallback behavior, chat assistant.

---

## Project structure

```
netsage-ai/
├── app/
│   ├── api/routes.py                  # REST endpoints
│   ├── application/
│   │   ├── rules.py                   # CiscoRuleChecker — the always-on fallback
│   │   ├── service.py                 # Orchestration
│   │   ├── prompt_library.py          # Prompts + few-shot examples
│   │   ├── security_service.py        # NIST/CIS bridge
│   │   └── fallback_chat.py           # Deterministic chat path
│   ├── domain/models.py               # Case, Review, Diagnosis types
│   ├── infrastructure/
│   │   ├── live_providers.py          # HF + Ollama adapters
│   │   ├── fallback_provider.py       # Rule-based diagnosis
│   │   ├── llm_client.py              # HTTP client for both LLM backends
│   │   ├── file_repositories.py       # CSV / JSON persistence
│   │   └── security_validator_mcp.py  # Compliance validator
│   ├── mcp_server.py                  # MCP 2.x server
│   └── main.py                        # App factory + lifespan
├── data/
│   ├── cases.csv                      # 32 benchmark cases
│   ├── diagnosis_comparison.csv       # Model vs ground truth
│   ├── responsible_ai_log.csv         # Every rejection and edit, with reasons
│   └── reviews.json                   # Full audit trail
├── prompts/
│   ├── diagnose_prompt.md             # Strict JSON diagnostic prompt, 3 worked examples
│   └── chat_prompt.md                 # Conversational tutor prompt
├── scripts/
│   └── generate_diagnosis_comparison.py
├── static/                            # SPA frontend
├── tests/
├── checker.py                         # Headless CLI rule runner
└── requirements.txt
```

---

## License

MIT. All scenarios are for educational use in Packet Tracer and virtual lab environments — not for production networks.
