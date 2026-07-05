# Performance & Scaling — Mudir / ORCHESTRA

Guidance for sizing, benchmarking, tuning and load-testing a self-hosted Mudir
deployment. Treat the numbers below as **planning estimates** — always benchmark
on your own hardware and models.

---

## 1. What drives performance

The dominant cost is **self-hosted AI inference**, not the web tier:

- **LLM (Ollama)** — intent understanding and workflow learning. Latency depends
  heavily on model size and GPU vs CPU.
- **Whisper** — voice-note transcription; scales with audio length.
- **Embeddings/translation/sentiment** — short, cheap once the model is loaded;
  the first call pays a model-load cost.
- **Backend/API and PostgreSQL** — negligible compared with inference for typical
  coordination traffic.

---

## 2. Benchmark profile (indicative)

Order-of-magnitude expectations; measure to confirm.

| Operation | GPU (RTX 3060+, 12 GB) | CPU-only (8+ cores) |
| --- | --- | --- |
| LLM intent classification (short prompt) | ~0.3–1.5 s | ~3–15 s |
| Workflow learning (longer prompt) | ~1–4 s | ~10–40 s |
| Whisper transcription (~10 s clip) | ~1–3 s | ~5–20 s |
| Embedding a short text (warm model) | ~10–50 ms | ~50–200 ms |
| REST `/api/*` query | < 50 ms | < 50 ms |

**Takeaway:** a GPU roughly delivers an order-of-magnitude lower latency for LLM
and Whisper. CPU-only is viable for low volumes and smaller models.

---

## 3. Sizing recommendations

| Load | Guidance |
| --- | --- |
| **Pilot / small** (a few concurrent projects) | CPU-only, 8 cores, 32 GB RAM, smaller Ollama model + Whisper base |
| **Production** (many active projects) | GPU (12 GB+ VRAM), 8+ cores, 32 GB+ RAM, SSD |
| **High volume** | Multiple GPU inference workers, PostgreSQL read replicas, Redis for shared state, CDN for the dashboard |

Disk: allow **60–100 GB+** for models, vectors and database growth. Models alone
can be several GB each.

---

## 4. Optimisation guide

**AI tier**
- Prefer a **GPU** for LLM + Whisper; it's the single biggest win.
- Choose the **smallest model** that meets quality needs (e.g. Phi-3 vs Llama 3).
- **Pre-load / keep models warm** so requests don't pay cold-start cost.
- Batch embeddings where possible (`batch_generate_embeddings`).
- Cache repeated LLM results (e.g. identical intent prompts) where correctness
  allows.

**Web / data tier**
- The **backend is stateless** — scale horizontally (`--scale backend=N`); nginx
  load-balances. Move in-memory voice-confirmation state to **Redis** first.
- Add **PostgreSQL indexes** for hot queries (the schema already indexes status,
  company and workflow foreign keys) and use **read replicas** for read-heavy
  analytics.
- Tune the async DB **connection pool** (`pool_size`, `max_overflow`,
  `pool_recycle`) to match worker concurrency.
- Front the frontend with a **CDN**; enable gzip/caching (configured in nginx).

**Edge**
- Keep rate limits sane to shed abusive load early.
- Enable HTTP keep-alive and gzip (configured) to reduce overhead.

---

## 5. Load testing

- **Web/API:** use `k6`, `wrk` or `autocannon` against `/health` and `/api/*` to
  validate the stateless tier and pool sizing.
- **Webhook path:** replay signed webhook payloads at target QPS; watch queueing
  and inference latency (the real bottleneck).
- **AI tier:** benchmark Ollama/Whisper directly at expected concurrency to find
  the per-GPU throughput ceiling, then size worker count accordingly.
- Measure **p50/p95/p99** latency and error rate, not just averages, and test at
  and beyond expected peak.

Example (API smoke load):
```bash
# 50 virtual users for 30s against the projects endpoint
k6 run --vus 50 --duration 30s script.js
```

---

## 6. Monitoring

Enable the optional **Prometheus + Grafana** stack (see [DEPLOYMENT.md](../DEPLOYMENT.md) §3):

- **System** — CPU, RAM, GPU utilisation/VRAM, disk, network.
- **Model performance** — inference latency and throughput per service.
- **Application** — request rate/latency/errors, project + WhatsApp metrics.

Set alerts on: GPU/CPU saturation, rising inference latency (p95), error-rate
spikes, low disk, and DB connection saturation. Use these signals to decide when
to add inference workers, replicas or caching.
