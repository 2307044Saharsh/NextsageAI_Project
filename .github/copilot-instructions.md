# NetSage AI

- Use Python 3.11+, FastAPI, Pydantic, and httpx.
- Keep domain models independent from infrastructure and HTTP concerns.
- Hugging Face access must use `HF_API_TOKEN` from `.env`; never hard-code secrets.
- Diagnoses are advisory. A human review is mandatory before accepting any fix.
- Never execute Cisco configuration commands from the application.
- Keep deterministic checks in `app/application/rules.py` and external adapters in `app/infrastructure/`.
- Run `pytest -q` before submitting changes.
