# Deployment Guide

This documents one practical, minimal-infrastructure deployment path. It
intentionally avoids Kubernetes — a single VM running two Docker containers
behind a reverse proxy is sufficient for this project's scope.

```
Browser
   │  HTTPS
   ▼
Reverse proxy (nginx / Caddy) — TLS termination, domain routing
   │
   ├──► frontend container (static files, port 80 internally)
   │
   └──► backend container (FastAPI/uvicorn, port 8000 internally)
             │
             ▼
      Search providers (DuckDuckGo, Tavily) + LLM provider (Groq/Gemini)
```

## 1. Server setup

- Any Linux VM with 1+ vCPU / 1GB+ RAM (e.g. a small DigitalOcean droplet,
  EC2 t3.micro, or similar) is sufficient — this system is I/O-bound
  (waiting on external APIs), not compute-heavy.
- Install Docker Engine and the Docker Compose plugin:
  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo apt-get install -y docker-compose-plugin
  ```

## 2. Firewall / security considerations

- Only expose ports 80/443 (reverse proxy) publicly. Keep backend port
  8000 and frontend port 80 bound to `127.0.0.1` or a private Docker
  network, not the public interface.
- Run containers as non-root (already configured in `backend/Dockerfile`).
- Keep `ALLOW_PRIVATE_NETWORK_FETCH=false` in production — this is the
  SSRF-mitigation setting for the content fetcher.

## 3. Environment configuration and secrets

- Copy `.env.example` to `.env` on the server (never commit `.env`).
- Fill in `TAVILY_API_KEY`, and either `GROQ_API_KEY` or `GEMINI_API_KEY`.
- For anything beyond a single trusted operator, prefer your platform's
  secret manager (e.g. Docker secrets, AWS Secrets Manager, systemd
  credentials) over a plain `.env` file on disk.

## 4. Reverse proxy + HTTPS

Example nginx site config in front of both containers:

```nginx
server {
    listen 443 ssl;
    server_name research.example.com;

    ssl_certificate     /etc/letsencrypt/live/research.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/research.example.com/privkey.pem;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }

    location / {
        proxy_pass http://127.0.0.1:5173/;
    }
}
```

Use `certbot --nginx` (Let's Encrypt) for free TLS certificates.

## 5. Domain

Point an A/AAAA record at the server's IP, then issue the certificate above
for that hostname.

## 6. Health checks, logging, monitoring

- Both `docker-compose.yml` services already define container-level
  `healthcheck`s hitting `/health` (backend) and `/` (frontend).
- The backend emits structured JSON logs to stdout (see
  `app/observability/logging.py`); in production, ship these to your
  platform's log aggregator (e.g. `docker logs`, or a driver like
  `json-file` with log rotation, or forward to a hosted log service).
- `app/observability/metrics.py` is an in-process counter/histogram store
  with no external exporter wired up — a real deployment would swap this
  for a Prometheus client or similar (documented as a known limitation).

## 7. Restart policy

`docker-compose.yml` sets `restart: unless-stopped` on both services so
they recover automatically after a crash or host reboot.

## 8. Scaling

- The backend is stateless (no database, no in-process session state) so
  it can be horizontally scaled by running multiple backend containers
  behind the reverse proxy — with one caveat: the in-memory rate limiter
  and circuit breaker (see `app/reliability/`) are per-process, so with
  multiple replicas each replica tracks its own provider health
  independently. For a small number of replicas this is an acceptable
  trade-off; at larger scale, back these with Redis.

## 9. Provider rate limits

- DuckDuckGo HTML search has no published rate limit — this integration
  applies its own conservative client-side pacing (`TokenBucketRateLimiter`,
  ~1 request/second) to avoid triggering scraping defenses.
- Tavily enforces a plan-based monthly quota; monitor usage via the Tavily
  dashboard and consider caching or reducing `MAX_SUBQUERIES` /
  `MAX_RESULTS_PER_PROVIDER` if approaching the limit.

## 10. Resource limits

Add `deploy.resources.limits` to `docker-compose.yml` (or platform
equivalent) if running on constrained infrastructure, e.g.:

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 512M
```

## 11. Updating deployments / rollback

```bash
git pull
docker compose build
docker compose up -d
```

Rollback: `git checkout <previous-tag>` then repeat the build/up steps, or
keep the previous image tagged (`docker compose build --pull` with a
version tag) and `docker compose up -d` with the prior tag if a regression
is discovered.

## 12. CORS

Set `CORS_ALLOWED_ORIGINS` in `.env` to the exact production frontend
origin (e.g. `https://research.example.com`) — never `*` in production.

## What "local Docker" validates (actually measured)

Running `docker compose up --build` locally validates:

- Both images build successfully (multi-stage, non-root runtime user)
- Both containers start and pass their container-level health checks (`/health` for backend, `/` for frontend)
- Backend serves the FastAPI app on port 8000 with `/health` returning the configured providers + LLM model
- Frontend serves the built React app via nginx on port 5173
- End-to-end request flow works: `POST /api/research` through the reverse-proxy network to the backend returns a valid `ResearchReport`

**Verified in this project** (2026-09-16):
- `docker compose build` → both images built
- `docker compose up -d` → `backend` healthy immediately, `frontend` healthy within ~10s
- `curl http://localhost:8000/health` → `{"status":"ok",...,"llm":{"provider":"groq","model":"openai/gpt-oss-20b","configured":true}}`
- `curl http://localhost:5173` → HTTP 200, HTML served
- `POST http://localhost:8000/api/research` with real question → 200, valid report with real sources

What local Docker does **not** guarantee (unchanged): TLS, DNS, firewall, log aggregation, secret management, production load behavior.
