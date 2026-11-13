# Multi-Agent HR Assistant (v1)

A multi-tenant HR assistant for companies. Employees ask questions in chat; a LangGraph router sends each message to a specialist: **policy Q&A** (RAG over the company's own documents) or **leave management** (tool calls against the database). Every company only ever sees its own data.

> Status: v1 backend MVP. Works locally against Supabase Postgres. Not deployed yet, no frontend yet.

## What it does

- **Auth and tenancy:** company signup, login, `/me` returning `tenant_id`, `user_id`, `role`.
- **Policy Q&A (RAG):** answers from the company's uploaded policy documents, with citations. Refuses when retrieval finds nothing relevant above the score threshold.
- **Leave management:** check balance, propose a request, confirm it, list requests, decline.
- **Router:** classifies each message to the policy or leave path.
- **Document upload:** `.md`, `.txt`, `.pdf`, `.docx`; list uploaded documents.
- **Tenant isolation:** Postgres Row-Level Security (restricted `app_user` role, `tenant_id` on every table) and tenant + role filters on Qdrant retrieval.
- **Rate limiting:** login, signup, per-user chat, and a per-company daily cap with usage records.

## Architecture

```
Client
  |
FastAPI  --(JWT: tenant_id, user_id, role)-->  Auth
  |
/chat --> LangGraph
            |-- Router (openai/gpt-oss-20b)
            |-- Policy node: Qdrant retrieval (tenant + role filter) -> answer with citations (openai/gpt-oss-120b)
            |-- Leave node: tools -> Postgres (RLS enforced)
  |
Postgres (Supabase, Alembic migrations)     Qdrant (vectors, all-MiniLM-L6-v2)
```

## Tech stack

| Layer | Choice |
|---|---|
| API | FastAPI, Python 3.12 |
| Orchestration | LangGraph / LangChain |
| LLM | Groq-hosted `openai/gpt-oss-20b` (router), `openai/gpt-oss-120b` (answers) |
| Embeddings | HuggingFace `all-MiniLM-L6-v2` (English) |
| Vector store | Qdrant (local for development) |
| Database | Postgres (Supabase), SQLAlchemy (sync, psycopg2) |
| Migrations | Alembic |
| Rate limiting | slowapi |
| Tests | pytest |

## Project structure

```
MVP/BACKEND/
  app/            # API routes, services, agents, config
  alembic/        # migrations (baseline schema, RLS policies/grants)
  scripts/
    evaluate.py   # retrieval/answer evaluation script
  tests/          # unit, API and isolation tests
```

(Adjust folder names to match the repo.)

## Setup

```bash
git clone https://github.com/Samad296/Multi_Agent_HR-.git
cd Multi_Agent_HR-/MVP/BACKEND

conda create -n eka python=3.12 -y
conda activate eka
pip install -r requirements.txt

cp .env.example .env      # fill in values below
alembic upgrade head
uvicorn app.main:app --reload
```

### Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string (`postgresql+psycopg2://...`), connecting as the restricted `app_user` role |
| `GROQ_API_KEY` | Groq API key |
| `QDRANT_URL` | Qdrant endpoint (local in development) |
| `QDRANT_API_KEY` | Only if using Qdrant Cloud |
| `JWT_SECRET` | Secret for signing tokens |
| `RETRIEVAL_MIN_SCORE` | Minimum retrieval score; currently `0.25` |

(Match these names to `config.py`. Never commit `.env`.)

## Running tests

```bash
pytest
```

Currently 18 tests: auth, leave, rate limiting, tenant isolation (database and retrieval), and RLS guard tests.

## Design decisions

- **Router + specialists, not a free-roaming agent.** Two well-defined tasks don't need autonomy; a router is cheaper, faster and easier to test.
- **Shared database with RLS** rather than a database per company: cheap to run, with isolation enforced by the database itself, not just application code.
- **Threshold-based refusal.** `RETRIEVAL_MIN_SCORE = 0.25` was calibrated on the current evaluation set.
- **Confirm-before-write for leave.** The agent proposes a request and only writes it after confirmation.

## Known limitations

- Not deployed; no frontend.
- Evaluation so far used the same set that informed threshold tuning. A held-out evaluation is still to be done, so no accuracy figures are claimed here.
- English documents only (MiniLM is an English model).
- Development uses local Qdrant; Qdrant Cloud timed out from the development network.
- Recruiting and other HR workflows are not implemented.
- Groq free-tier limits apply to throughput.

## Roadmap

1. Held-out evaluation and published results
2. Deployment (free tier)
3. Minimal frontend (login, chat, admin upload)
4. Additional HR agents (e.g. recruiting)

