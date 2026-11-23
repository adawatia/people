#!/usr/bin/env bash
# ==============================================================================
# People HRMS — Automated EC2 Continuous Deployment Script
# Target Host: 16.179.29.185 (https://16-179-29-185.sslip.io)
# ==============================================================================
set -eo pipefail

export PATH="/home/ubuntu/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Target branch passed as $1 (defaults to currently checked-out branch, or 'uat')
TARGET_BRANCH="${1:-$(git -C /var/www/people rev-parse --abbrev-ref HEAD 2>/dev/null || echo "uat")}"

echo "=================================================="
echo "🚀 People HRMS Deployment Triggered"
echo "🌿 Target Branch: ${TARGET_BRANCH}"
echo "📅 Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "💻 Host: $(hostname)"
echo "=================================================="

# 1. Update Repository Code
echo "📥 [1/5] Fetching and pulling latest ${TARGET_BRANCH} branch..."
cd /var/www/people
git fetch origin "${TARGET_BRANCH}"
git checkout -f "${TARGET_BRANCH}"
git reset --hard "origin/${TARGET_BRANCH}"

# 2. Update Backend Runtime & Migrations
echo "⚙️ [2/5] Updating backend dependencies and database schema..."
cd /var/www/people/app/api
uv sync
uv run alembic upgrade head

# 3. Build Frontend SSR Bundle
echo "⚙️ [3/5] Installing frontend dependencies and compiling Nuxt..."
cd /var/www/people/app/web
pnpm install --frozen-lockfile || pnpm install
NODE_OPTIONS="--max-old-space-size=1536" pnpm build

# 4. Restart Background Daemons
echo "🔄 [4/5] Restarting backend and frontend daemons..."
sudo systemctl restart hrms-backend
sudo systemctl restart hrms-frontend

# 5. Smoke Test & Health Check
echo "🩺 [5/5] Running service health checks..."

# Check backend API with retry loop (FastAPI startup takes 5-10s on t3.small after build)
BACKEND_OK=false
for i in $(seq 1 10); do
    if curl -sf http://127.0.0.1:8000/health > /dev/null; then
        BACKEND_OK=true
        break
    fi
    echo "  ⏳ Waiting for backend API to initialize ($i/10)..."
    sleep 2
done

if [ "$BACKEND_OK" = true ]; then
    echo "  ✅ Backend API (FastAPI) is healthy!"
else
    echo "  ❌ Backend health check failed on http://127.0.0.1:8000/health"
    echo "  📋 Checking backend service status:"
    sudo systemctl status hrms-backend --no-pager || true
    echo "  📋 Recent backend system logs:"
    journalctl -u hrms-backend -n 30 --no-pager || true
    exit 1
fi

# Check frontend SSR with retry loop
FRONTEND_OK=false
for i in $(seq 1 8); do
    FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000 || echo "000")
    if [ "$FRONTEND_STATUS" = "200" ] || [ "$FRONTEND_STATUS" = "302" ]; then
        FRONTEND_OK=true
        break
    fi
    echo "  ⏳ Waiting for frontend SSR to initialize ($i/8)..."
    sleep 2
done

if [ "$FRONTEND_OK" = true ]; then
    echo "  ✅ Frontend Server (Nuxt Nitro) is healthy! (HTTP $FRONTEND_STATUS)"
else
    echo "  ❌ Frontend health check failed with HTTP $FRONTEND_STATUS"
    echo "  📋 Recent frontend system logs:"
    journalctl -u hrms-frontend -n 30 --no-pager || true
    exit 1
fi

echo "=================================================="
echo "🎉 Deployment successfully completed!"
echo "🌐 Live Application: https://16-179-29-185.sslip.io"
echo "📚 OpenAPI Documentation: https://16-179-29-185.sslip.io/docs"
echo "=================================================="
