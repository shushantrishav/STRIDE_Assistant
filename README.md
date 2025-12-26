# STRIDE Assistant — Policy‑First Retail AI for Footwear Complaints (Backend + AI)

STRIDE Assistant is a **backend-first AI system** for a premium footwear brand that automates complaint triage (return/refund, replacement, repair, paid repair, inspection, reject) using a **policy‑first RAG pipeline**.  
It is designed to demonstrate production‑style backend engineering: clear service boundaries, deterministic decisioning, auditability, and safe LLM integration.

> **Core idea:** The LLM helps with *language understanding and customer communication*, while the *decision authority* remains deterministic and policy-driven.

---

## Why this project
Footwear complaint handling looks simple but isn’t: warranty windows, purchase dates, outlet constraints, stock availability, and misuse signals create a decision space where **speed + consistency + traceability** are hard requirements.

This project shows how to:
- Build a **reliable AI assistant** without hallucinated decisions.
- Combine **RAG retrieval** with a **deterministic decision engine**.
- Keep the system **auditable**, **safe**, and **maintainable**.

---

## Key features
- **Policy‑First RAG Pipeline**
  - Intent classification (LLM → structured JSON)
  - Policy retrieval using embeddings + eligibility filtering
  - Deterministic decision engine enforcing strict rules
  - Signal arbitration + inventory safety overrides
  - Turn limits + clarification flow to avoid infinite loops
- **Backend Engineering**
  - FastAPI service with modular routers (customer chat, staff, admin)
  - JWT-based auth patterns (customer session and staff access)
  - Redis caching for low-latency order/inventory access
  - Postgres persistence for tickets + staff audit logs
- **Operational Focus**
  - Structured logging and failure-safe fallbacks
  - Separation of concerns: retrieval ≠ decision ≠ language generation

---

## System diagram (end-to-end)
```plaintext
                         +------------------------+
                         | Customer / Chat UI     |
                         | (Web, WhatsApp-like)   |
                         +-----------+------------+
                                     |
                                     v
                         +------------------------+
                         | FastAPI Chat API       |
                         | /chat/auth,start,respond|
                         +-----------+------------+
                                     |
                                     v
                     +-----------------------------------+
                     | STRIDERAGPipeline (Orchestrator)  |
                     | - turn mgmt + signal arbitration  |
                     +-----------+-----------------------+
                                 |
                                 v
                      +----------------------------+
                      | Semantic Analyzer (LLM)    |
                      | Intent + misuse/accident   |
                      +-----------+----------------+
                                  |
                                  v
                  +------------------------------------+
                  | Policy Retriever (RAG)             |
                  | - eligible intents + day windows   |
                  | - semantic similarity over chunks  |
                  +----------------+-------------------+
                                   |
                                   v
                  +------------------------------------+
                  | Decision Engine (Deterministic)    |
                  | - returns/repairs/replacements     |
                  | - warranty + misuse handling       |
                  +------------------+-----------------+
                                     |
                                     v
                 +-------------------+-------------------+
                 |                                       |
                 v                                       v
   +---------------------------+                +--------+---------+
   | Auto Outcome  (Ticket)    |                |   Reject Signal  |
   | REPAIR / REPLACEMENT      |                |     GCD Token    |
   | PAID_REPAIR / REJECT      |                +--------+---------+
   |  INSPECTION / RETURN      |                         |
   | Manual / Inspection       |                         v
   +-------------+-------------+                +--------+---------+
                 |                              |   Close Chat     |
                 |                              +------------------+
                 |                         
                 |                         
                 |                         
                 |                                       
                 +---------------------+
                                       |
                                       v
                         +---------------------------+
                         | Ticket Created / Updated  |
                         | (Postgres)                |
                         +-------------+-------------+
                                       |
                                       v
                         +----------------------------+
                         | Prompt Builder (Safe UX)   |
                         | Policy-safe response text  |
                         +-------------+--------------+
                                       |
                                       v
                         +----------------------------+
                         | Ollama LLM (Streaming)     |
                         +-------------+--------------+
                                       |
                                       v
                         +----------------------------+
                         | Customer Response (SSE)    |
                         +----------------------------+

   Side services:
   - Redis: cached orders + inventory lookups
   - Postgres: tickets + staff audit logs + chat summaries
```
## Tech stack
- API: FastAPI (Python)
- LLM runtime: Ollama (local/private inference)
- Cache: Redis
- Database: PostgreSQL
- Policy RAG store: SQLite (policy chunks + embeddings) (can be upgraded to Postgres with versioning)
- Embeddings: SentenceTransformers (e.g., MiniLM family)
- Testing: pytest (unit tests + mocks)

## Repository structure
```text
├── api/                 # FastAPI routers (chat, staff, admin)
├── cache/               # Redis-backed cache helpers (orders/inventory)
├── db/                  # Postgres operations (tickets, audit, auth, chat)
├── ingest/              # Policy ingestion scripts
├── policies/            # Markdown policies (source of truth)
├── rag/                 # analyzer, retriever, decision engine
├── Services/            # prompt builder, logger, embedder utilities
├── Logs/                # log files
├── main.py              # FastAPI entrypoint
└── README.md
```
## How it works (decision philosophy)
This system intentionally splits responsibilities:
1) Semantic understanding (probabilistic)
- The LLM is used to:
   - interpret user text
   - output structured intent JSON
   - help produce professional customer messages

2) Policy enforcement (deterministic)
- The decision engine enforces:
   - time windows (return/refund limits)
   - warranty duration rules
   - misuse / accident routing
   - escalation when uncertain
   - safety overrides (example: replacement blocked if inventory is unavailable)

This architecture prevents “LLM as judge” failure modes and keeps outcomes explainable.
## Ticket types
The pipeline resolves requests into one of:
- RETURN
- REPLACEMENT
- REPAIR
- PAID_REPAIR
- INSPECTION
- REJECT
## APIs (high level)
1) Customer Chat
 - POST /chat/auth — verifies order + phone and creates a session token
 - POST /chat/start — begins conversation and streams response (SSE)
 - POST /chat/respond — continues conversation; persists ticket decision when resolved
2) Staff
 - Login + ticket update endpoints (role/outlet scope)
3) Admin
 - Audit visibility endpoints (read-only oversight patterns)
## Running locally (recommended: Docker Compose)
1) Create .env
```text
JWT_SECRET_KEY=change_me

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_USER=stride_admin
REDIS_PASSWORD=stride_password
REDIS_DB=0

# Postgres
DB_NAME=stride
DB_USER=stride
DB_PASSWORD=stride
DB_HOST=postgres
DB_PORT=5432
```
2) Start services
```bash
docker compose up --build
```
3) Verify API
```bash
curl http://localhost:8000/
```
## Policy ingestion (RAG data build)
Policies are authored in Markdown under policies/.
An ingestion script splits policies into chunks, embeds them, and stores them in a local policy DB (SQLite) for semantic retrieval.

Typical flow:

```bash
python ingest/ingest_policies.py
```

## Testing
The test strategy is intentionally backend‑centric:
 - unit tests for deterministic decision engine branches
 - tests for policy chunk parsing stability
 - retriever tests (eligibility filtering + similarity ranking)
 - pipeline tests with mocks to avoid external service dependency

Run:
```bash
pytest -q
```
Engineering highlights (what this project shows off)
 - Clean separation: API ↔ orchestration ↔ retrieval ↔ decision ↔ language UX
 - Deterministic enforcement prevents LLM hallucination from becoming an outcome
 - Audit-first approach: staff actions are tracked for accountability
 - Production-ready patterns: env config, service boundaries, observability, safe fallbacks

Roadmap
 - CI pipeline (ruff/pytest/coverage) on every PR
 - Versioned policy schema + migrations (Alembic)
 - Stricter classifier output validation (JSON schema + domain constraints)
 - Analytics dashboard: ticket outcomes, outlet performance, complaint trends
 - GPU-backed inference for higher throughput

Author
[Shushant Rishav](https://shushantrishav.in)
Project: [STRIDE Assistant](https://shushantrishav.in/STRIDE_Assistant/)