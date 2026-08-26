# Aletheia Engine

> Fully offline RAG orchestration system — ingest, retrieve, synthesize, and
> self-correct via a faithfulness-judging loop, with no cloud dependency.

**Status: active rebuild.** This is a from-scratch, production-grade rewrite
of an earlier prototype — moving from a single monolithic service to an
isolated microservice swarm (FastAPI gateway, Celery workers, Qdrant vector
store, Postgres system-of-record) built with a uv workspace monorepo.

## Architecture

- `libs/aletheia_core` — shared config, DB models, security, vector client,
  logging, and Celery app factory used by every service
- `services/api-gateway` — FastAPI HTTP layer, JWT auth, routing
- `services/inference-service` — embedder, reranker, and Ollama proxy
- `services/ingestion-worker` — document extraction and chunking
- `services/synthesis-worker` — retrieval + generation
- `services/judge-worker` — faithfulness scoring on generated answers

## Status

## Status

Phase 8 of 12 — active development.

- ✅ aletheia_core — config, DB models, migrations, security, vector client, Celery
- ✅ inference-service — BGE embedder (cuda), cross-encoder reranker, Ollama/Groq abstraction  
- ✅ api-gateway — JWT auth fully verified end-to-end (register → login → /me)
- 🔄 Remaining gateway routers (collections, ingestion, search, jobs) — next
- ⬜ ingestion-worker, synthesis-worker, judge-worker
- ⬜ Tests, Dockerfiles, docker-compose final
- ⬜ Constellation UI data contracts
## License

MIT — see [LICENSE](LICENSE).