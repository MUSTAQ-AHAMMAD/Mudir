# Deployment Guide — Mudir / ORCHESTRA

Production deployment documentation for the self-hosted Mudir stack (Node.js
API + React dashboard + ORCHESTRA self-hosted AI services), orchestrated with
Docker Compose behind an nginx reverse proxy.

---

## 1. System requirements

| Profile | CPU | RAM | Disk | GPU |
| --- | --- | --- | --- | --- |
| **GPU** (recommended) | 8+ cores | 32 GB+ | 100 GB+ SSD | NVIDIA RTX 3060+ (12 GB VRAM) |
| **CPU-only** | 8+ cores | 32 GB+ | 60 GB+ SSD | — |

Software:
- Ubuntu 22.04 LTS
- Docker Engine + Docker Compose v2
- Git
- For GPU: NVIDIA drivers + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

Open firewall ports: **80** and **443** (public). Internal service ports
(3000, 5432, 8000, 9000, 11434) are **not** published to the host — they are
reached only over the private compose network.

---

## 2. File layout

```
docker/
  Dockerfile.backend      Multi-stage Node.js API image (non-root, healthcheck)
  Dockerfile.frontend     Vite build → nginx static server
  Dockerfile.ollama       Ollama + model pre-loading entrypoint
  frontend-nginx.conf     Per-container SPA/gzip/cache config
  ollama-entrypoint.sh    Boots ollama + pulls OLLAMA_MODELS
docker-compose.yml         Base production stack
docker-compose.gpu.yml     GPU overlay (NVIDIA runtime, larger limits)
docker-compose.cpu.yml     CPU overlay (lightweight models)
docker-compose.monitoring.yml  Prometheus + Grafana + exporters (optional)
scripts/
  deploy.sh   backup.sh   update.sh   monitor.sh   ssl-renew.sh
nginx/nginx.conf           Edge reverse proxy (TLS, routing, rate limiting)
nginx/ssl/README.md        Let's Encrypt issuance + auto-renewal
monitoring/                Prometheus config, alert rules, Grafana dashboards
k8s/deployment.yaml        Optional Kubernetes manifests
.github/workflows/deploy.yml   CI/CD (test → build images → SSH deploy)
.env.production / .env.staging Environment templates
```

---

## 3. Step-by-step deployment

```bash
# 1. Clone the repository onto the server
git clone https://github.com/MUSTAQ-AHAMMAD/Mudir.git /opt/mudir
cd /opt/mudir

# 2. Configure the environment
cp .env.production .env
#   Edit .env: set POSTGRES_PASSWORD, WATI/Twilio + Supabase creds, PUBLIC_URL,
#   OLLAMA_MODELS, GRAFANA_ADMIN_PASSWORD, etc.
nano .env

# 3. Point your domain's DNS A/AAAA records at the server, then issue TLS certs
#    (see nginx/ssl/README.md). Update the server_name in nginx/nginx.conf.

# 4. Deploy (GPU host)
./scripts/deploy.sh gpu
#    …or CPU-only
./scripts/deploy.sh cpu

# 5. Verify
./scripts/monitor.sh
```

Manual equivalent of `deploy.sh`:

```bash
# GPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
# CPU
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d
```

Enable monitoring (optional):

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml \
               -f docker-compose.monitoring.yml up -d
# Grafana → http://<host>:3001  (admin / GRAFANA_ADMIN_PASSWORD)
```

---

## 4. Operations

| Task | Command |
| --- | --- |
| Health snapshot | `./scripts/monitor.sh` |
| Back up DB + ChromaDB | `./scripts/backup.sh` |
| Zero-downtime update | `./scripts/update.sh gpu` |
| Renew TLS certs | `./scripts/ssl-renew.sh` |
| View logs | `docker compose logs -f backend` |
| Scale the API | `docker compose up -d --scale backend=3` |

**Daily backups** — add a cron entry:

```cron
0 2 * * * cd /opt/mudir && ./scripts/backup.sh >> /var/log/mudir-backup.log 2>&1
```

---

## 5. Security

- All secrets live in `.env` (git-ignored) or a secrets manager — never in code.
- HTTPS only; HTTP redirects to HTTPS (HSTS enabled).
- Rate limiting on `/webhook` and `/api` at the edge.
- WhatsApp webhook signature validation (`TWILIO_VALIDATE_SIGNATURE` / WATI secret).
- Data services are not published to the host — private compose network only.
- Enable PostgreSQL encryption at rest at the volume/host level (e.g. LUKS).
- Keep the host and images patched; rebuild regularly to pick up base-image CVEs.

---

## 6. Scaling

- **Backend** is stateless — scale horizontally (`--scale backend=N`); nginx
  load-balances across replicas.
- **Database** — add read replicas and point read-heavy queries at them.
- **Caching** — add Redis for voice-note confirmation state (currently in-memory)
  to support multiple backend instances.
- **Static assets** — front the frontend with a CDN.
- **Kubernetes** — use `k8s/deployment.yaml` for multi-node scaling with an
  Ingress controller and cert-manager.

---

## 7. Troubleshooting

| Symptom | Check |
| --- | --- |
| Service stuck `unhealthy` | `docker compose ps`, then `docker compose logs <svc>` |
| GPU not used | `docker info | grep -i nvidia`; ensure NVIDIA Container Toolkit; use `gpu` profile |
| Ollama slow first response | Model still downloading — watch `docker compose logs ollama` |
| 502 from nginx | Backend not healthy yet, or wrong upstream name — check `/health` |
| TLS errors | Certs not issued/renewed — see `nginx/ssl/README.md` |
| DB connection refused | `POSTGRES_PASSWORD`/`DATABASE_URL` mismatch in `.env` |

---

## 8. Configuration reference

See [`.env.production`](.env.production) for the full, commented list of
environment variables (runtime, database, self-hosted AI services, WATI/Twilio,
Supabase, business rules, rate limiting, feature flags, monitoring).
