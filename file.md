# STRIDE – Intelligent Complaint Resolution System

---

## Problem Statement

Footwear companies often face high volumes of customer complaints related to returns, repairs, replacements, or refunds. Managing these requests manually is time-consuming, error-prone, and inconsistent across outlets. STRIDE requires a **policy-aware, automated complaint handling system** that can enforce warranty rules, detect eligibility, and assist staff in decision-making while maintaining complete auditability.

---

## Project Overview

This project implements a **Retrieval-Augmented Generation (RAG) pipeline** for STRIDE's complaint management, combining:

* **Semantic analysis:** Detects complaint intent from customer messages.
* **Policy retrieval:** Identifies applicable rules based on purchase date, warranty, and product type.
* **Decision engine:** Determines eligibility, enforces policy, and generates actionable outcomes.
* **Ticketing system:** Creates, updates, and tracks complaint tickets in PostgreSQL.
* **Audit logging:** Immutable logging of all staff actions for compliance.
* **LLM integration:** Uses Mistral-7B-Instruct for generating human-readable responses to customers.

The system ensures **strict adherence to company policy**, automates repetitive checks, and provides staff with clear next steps.

---

## Key Features

### 1. RAG Pipeline

* **Retriever:** Maps natural language complaints to structured policy chunks.
* **Decision Engine:** Applies strict window-based rules (returns, replacements, repairs, paid repairs).
* **Arbitration:** Resolves conflicting signals from multiple system components.
* **Ticket Handling:** Generates tickets for manual inspection or approved store visits.

### 2. Policy Management

* Policies stored in Markdown (`policies/stride_customer_complaint_policies.md`).
* Deterministic retrieval ensures accurate policy application.
* Supports updates and versioning through `ingest/ingest_policies.py`.

### 3. Complaint Categories

* **Return / Refund** (within 7 days, unused products).
* **Replacement** (manufacturing defects, inventory available).
* **Repair** (warranty and paid repair post-warranty).
* **Inspection** (ambiguous complaints, missing data).
* **Reject** (policy violation, misuse, expired warranty).

### 4. Staff & Admin APIs

* Staff login, ticket assignment, status updates.
* Admin audit logs with immutable staff actions.
* Outlet-based filtering and reporting.

### 5. Logging & Observability

* General and error logging (`Logs/llama.log`, `Logs/error.log`).
* Staff actions logged via `db/staff_audit.py`.
* Exception-safe database operations with logging.

### 6. LLM Response Generation

* Professional, polite system messages built via `Services/prompt_builder.py`.
* Ensures consistent tone, avoids liability or promises.
* Supports conversation turn limits to avoid indefinite dialogue loops.

---

## Architecture

```plaintext
                 +-------------------+
                 | Customer Message  |
                 +---------+---------+
                           |
                           v
                  +-------------------+
                  | Semantic Analyzer | <--- INTENT Detection
                  +---------+---------+
                           |
                           v
                 +--------------------+
                 | Policy Retriever   | <--- Fetch relevant policy chunk
                 +---------+----------+
                           |
                           v
                 +--------------------+
                 | Decision Engine    | <--- Enforce policy rules
                 +---------+----------+
                           |
               +-----------+-----------+
               |                       |
               v                       v
      +----------------+       +------------------+
      | APPROVED / REJECT |     | MANUAL REVIEW   |
      +--------+---------+     +--------+---------+
               |                        |
               v                        v
         Staff Notification         Ticket Created
               |                        |
               +-----------+------------+
                           v
                   Customer Response
```

---

## Project Structure

```plaintext
./
├── api/               # FastAPI routers (chat, staff, admin)
├── db/                # PostgreSQL interactions, staff audit, tickets
├── ingest/            # Policy ingestion scripts
├── Logs/              # General and error logs
├── main.py            # FastAPI entry point
├── Models/            # LLM models
├── policies/          # Policy documents
├── rag/               # RAG pipeline components
├── Scripts/           # Model initialization, utilities
├── Services/          # Prompt builder, embedder, pipeline, logger config
└── Web/               # Placeholder for frontend if needed
```

---

## Database Setup

1. PostgreSQL required.
2. Run schema creation scripts in `db/`.
3. Create `.env` with:

```env
DB_HOST=localhost
DB_PORT=5432
DB_USER=stride_user
DB_PASS=yourpassword
DB_NAME=stride_db
```

4. Tables:

   * `sales_schema.tickets`
   * `staff_schema.staff`
   * `staff_schema.staff_action_log`
   * Inventory, orders, and sales tables

**Recommendation:** Use Alembic for production migrations.

---

## Quick Start

```bash
# Clone repository
git clone <repo_url>
cd stride_complaint_system

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Place LLM model
# Models/Mistral-7B-Instruct-v0.3-Q6_K.gguf

# Run FastAPI
uvicorn main:app --reload

# Health check
curl http://localhost:8000/
```

---

## Logging

* **General logs:** `Logs/llama.log`
* **Error logs:** `Logs/error.log`
* **Staff audit:** Immutable logs via `db/staff_audit.py`
* Uses `Services/logger_config.py` for consistent formatting and levels

---

## Error Handling & Observability

* All DB calls wrapped in try/except with logging.
* LLM exceptions captured and logged.
* Signal arbitration in RAG pipeline ensures fallback to manual inspection.

---

## Production Readiness Considerations

* **Thread-Safe LLM Access:** Store model in `app.state` for shared access; consider request queues.
* **Error Handling:** Centralized logging and exception capture.
* **Auditability:** Immutable staff action logs.
* **Configuration Management:** `.env` files and secrets management.
* **Rate Limiting & Auth:** JWT-based staff authentication.
* **Scalability:** Separate API routers, stateless endpoints, and database connection pooling.

---

## Deployment

### Docker

The application can be containerized using Docker for consistent local development and deployment environments.

#### Prerequisites

* Docker 20+
* Docker Compose (optional, recommended)

#### Build Image

```bash
docker build -t stride-complaint-system .
```

#### Run Container

```bash
docker run -d \
  --name stride-api \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/Models:/app/Models \
  stride-complaint-system
```

**Notes:**

* The LLM model (`.gguf`) is mounted as a volume to avoid baking large files into the image.
* PostgreSQL should be run as an external service or separate container.
* Logs are written to the `Logs/` directory inside the container.

#### Example Dockerfile (Reference)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Areas for Future Improvement

1. **Multi-Model Ensemble for Better Decision-Making**

   * Integrate multiple LLMs for intent detection, policy retrieval, and response generation.

2. **Enhanced Analytics & Insights**

   * Dashboards for complaint trends, staff performance, and product quality.

3. **Automated Policy Updates**

   * Versioned ingestion pipeline to automatically reflect updated company policies.

4. **Proactive Complaint Prevention**

   * ML models predicting potential issues and reducing complaint volume.

5. **Scalable Model Hosting**

   * GPU-backed inference or cloud endpoints to support high traffic.

6. **Intelligent Ticket Prioritization**

   * Prioritize tickets based on urgency, complaint type, and customer history.

7. **Unit & Integration Testing**

   * Pytest-based tests for RAG pipeline, API, and database interactions.

8. **Deployment & CI/CD**

   * Dockerized application with environment separation for staging and production.

---

## Contribution Guidelines

* Follow PEP8 and project structure.
* All database interactions should include proper exception handling.
* Add logging for any new module.
* All policy changes must be version-controlled and reviewed.

---

## License

This project is proprietary to STRIDE. Unauthorized use or distribution is prohibited.

---

## Contact

* Project Maintainer: STRIDE Internal AI Team
* Email: [ai-support@stride.com](mailto:ai-support@stride.com)
* Git Repository: `<internal_repo_url>`
