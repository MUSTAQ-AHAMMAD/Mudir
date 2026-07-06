#!/usr/bin/env bash
# deploy.sh — helper to deploy the Mudir backend.
#
# Usage:
#   ./deploy.sh render     # push to Render (via the render.yaml blueprint)
#   ./deploy.sh railway    # deploy with the Railway CLI
#   ./deploy.sh docker     # build + run locally with docker compose
#
# Prerequisites:
#   - render:  connect the repo in the Render dashboard (uses render.yaml)
#   - railway: `npm i -g @railway/cli` and `railway login`
#   - docker:  Docker + docker compose installed, backend/.env populated
set -euo pipefail

TARGET="${1:-}"

case "$TARGET" in
  render)
    echo "Render deploys automatically from render.yaml on push to the connected branch."
    echo "Ensure secret env vars are set in the Render dashboard, then: git push."
    ;;
  railway)
    command -v railway >/dev/null 2>&1 || { echo "Install the Railway CLI first: npm i -g @railway/cli"; exit 1; }
    railway up
    ;;
  docker)
    docker compose up --build -d
    echo "Backend running at http://localhost:3000/health"
    ;;
  *)
    echo "Usage: $0 {render|railway|docker}" >&2
    exit 1
    ;;
esac
