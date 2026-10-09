# Aletheia Engine

> Fully offline, self-hosted RAG orchestration — ingest, retrieve, synthesize, judge, self-correct. No cloud dependency. No API keys required.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org)
[![uv](https://img.shields.io/badge/package%20manager-uv-orange)](https://docs.astral.sh/uv)

---

## What is Aletheia?

Most RAG tools retrieve documents and generate an answer. Aletheia goes further — every generated answer is evaluated for faithfulness against its source context by a judge worker, and if it fails, a self-correction loop fires automatically. The entire pipeline runs offline on your own hardware.

```
Document upload
  → Extract (text/PDF/HTML) → Chunk (token-aware) → Embed (BGE) → Qdrant

Query
  → Embed → Retrieve (Qdrant ANN) → Rerank (cross-encoder)
  → Generate (Ollama/Groq) → Judge (faithfulness 0.0–1.0)
  → Self-correct if score < 0.7
```

All of this runs as **five independent microservices** — gateway, inference, ingestion worker, synthesis worker, judge worker — each on its own Celery queue, each independently scalable.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   api-gateway :8000                  │
│  FastAPI · JWT auth · REST endpoints · SSE stream   │
└──────┬──────────────────────────────────┬───────────┘
       │ HTTP                             │ Celery tasks
       ▼                                  ▼
┌─────────────┐              ┌────────────────────────┐
│  inference  │              │         Redis           │
│  service    │              │   (broker + results)   │
│  :8100      │              └───┬────────┬───────────┘
│             │                  ▼        ▼
│ /embed      │     ┌────────────────┐  ┌──────────────┐
│ /rerank     │◄────┤ingestion-worker│  │synthesis-    │
│ /generate   │     │(queue:ingest)  │  │worker        │
│             │◄────┤                │  │(queue:synth) │
└─────────────┘     └───────┬────────┘  └──────┬───────┘
                             │                  │
                    ┌────────▼──────────────────▼──────┐
                    │         judge-worker              │
                    │        (queue: judge)             │
                    └──────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
        ┌──────────┐                ┌──────────────┐
        │ Postgres │                │    Qdrant    │
        │ (records)│                │  (vectors)   │
        └──────────┘                └──────────────┘
```

---

## What makes it different

| Feature | Aletheia | Typical RAG tool |
|---|---|---|
| Offline by default | ✅ Zero internet required | ❌ Cloud API required |
| Faithfulness judging | ✅ 0.0–1.0 score per answer | ❌ Not evaluated |
| Self-correction loop | ✅ Auto-retry if score < 0.7 | ❌ One-shot generation |
| Independent workers | ✅ 3 separate Celery queues | ❌ Single process |
| Second-machine scaling | ✅ Point REDIS_URL, done | ❌ Requires orchestration |
| JWT multi-user auth | ✅ Built-in from day 1 | ❌ Usually bolted on later |
| SSE token streaming | ✅ Real-time output | ❌ Blocking wait |

---

## Tech Stack

**Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Celery, Redis  
**Vector:** Qdrant, BGE (`BAAI/bge-small-en-v1.5`), cross-encoder reranker  
**LLM:** Ollama (default, offline) or Groq (opt-in, cloud)  
**Infra:** Docker Compose, PostgreSQL, uv workspace monorepo  
**Auth:** JWT (access + refresh tokens, bcrypt passwords, token rotation)

---

## Quickstart

### Prerequisites
- Docker + Docker Compose
- Python 3.12
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

### 1. Clone and configure

```bash
git clone https://github.com/Aryaneviloo/aletheia
cd aletheia
cp .env.example .env
```

Edit `.env` — the defaults work for local dev, just change passwords if needed.

### 2. Install dependencies

```bash
uv sync --all-packages --group dev
```

### 3. Start infrastructure

```bash
docker compose up -d postgres redis qdrant ollama
```

### 4. Pull a model

```bash
docker exec aletheia-ollama ollama pull llama3.2:3b
```

Update `OLLAMA_MODEL=llama3.2:3b` in `.env`.

### 5. Run migrations

```bash
cd libs/aletheia_core && alembic upgrade head && cd ../..
```

### 6. Start services (6 terminals)

```bash
# Inference service
cd services/inference-service && uv run uvicorn app.main:app --port 8100

# API gateway
cd services/api-gateway && uv run uvicorn app.main:app --port 8000 --reload

# Workers
cd services/ingestion-worker && PYTHONPATH=. uv run celery -A app.celery_worker worker -Q ingestion -c 2 --loglevel=info
cd services/synthesis-worker && PYTHONPATH=. uv run celery -A app.celery_worker worker -Q synthesis -c 1 --loglevel=info
cd services/judge-worker     && PYTHONPATH=. uv run celery -A app.celery_worker worker -Q judge -c 2 --loglevel=info
```

### 7. Use it

```bash
# Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}'

# Login
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Create a collection
curl -X POST http://localhost:8000/collections \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Notes"}'

# Ingest a document (returns job_id immediately)
curl -X POST http://localhost:8000/ingestion \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"collection_id": "<id>", "content": "Your text here...", "source_name": "My Doc"}'

# Ask a question (async, poll /jobs/{id} for answer)
curl -X POST http://localhost:8000/synthesis \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "What does the document say about X?", "collection_ids": ["<id>"]}'

# Or stream tokens in real-time
curl -X POST http://localhost:8000/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "Explain X", "collection_ids": ["<id>"]}'
```

Interactive API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Project Structure

```
aletheia/
├── libs/aletheia_core/     # Shared library: config, DB, security, vector, queue
├── services/
│   ├── api-gateway/        # FastAPI HTTP layer, JWT auth, all endpoints
│   ├── inference-service/  # BGE embedder, reranker, Ollama/Groq proxy
│   ├── ingestion-worker/   # Extract → chunk → embed → store
│   ├── synthesis-worker/   # Retrieve → rerank → generate → save
│   └── judge-worker/       # Faithfulness scoring + self-correction dispatch
├── tests/                  # Unit + integration tests
└── docker-compose.yml      # Postgres, Redis, Qdrant, Ollama
```

---

## Configuration

All config lives in `.env`. Key options:

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_MODEL` | `llama3.2:1b` | Model to use. `3b` or `7b` recommended for better quality |
| `LLM_PROVIDER` | `ollama` | `ollama` (offline) or `groq` (cloud) |
| `GROQ_API_KEY` | — | Required if `LLM_PROVIDER=groq` |
| `EMBEDDING_MODEL_NAME` | `BAAI/bge-small-en-v1.5` | BGE embedding model |
| `CHUNK_SIZE_TOKENS` | `400` | Max tokens per chunk |
| `CHUNK_OVERLAP_TOKENS` | `60` | Overlap between chunks |

---

## Scaling

**Run a worker on a second machine:**
```bash
# On the second machine, pointing at the primary's Redis:
REDIS_URL=redis://<primary-ip>:6379/0 \
PYTHONPATH=. celery -A app.celery_worker worker -Q ingestion -c 4
```

No code changes. The worker joins the swarm automatically.

---

## Roadmap

- [x] Ingestion pipeline (text, PDF, HTML)
- [x] Vector search + cross-encoder reranking
- [x] LLM synthesis via Ollama / Groq
- [x] Faithfulness judge + self-correction loop
- [x] JWT multi-user auth
- [x] SSE token streaming
- [x] REST API with OpenAPI docs
- [ ] Dockerfiles + production docker-compose
- [ ] **Galaxy UI** — 3D visualization of your knowledge as a star system ([aletheia-ui](https://github.com/Aryaneviloo/aletheia-ui))
- [ ] Auto hardware detection (picks best model for your GPU/CPU)
- [ ] DOCX, EPUB, YouTube transcript extractors
- [ ] Spaced repetition layer
- [ ] Concept graph extraction

---

## License

MIT — see [LICENSE](LICENSE).

---

Built by [Aryan](https://github.com/Aryaneviloo) · Contributions welcome