# CheckoutPilot as ONE web service: Azure App Service (docs/deploy_azure.md) or Render (docs/deploy_render.md).
# The service serves the dashboard, the API and the two example stores from one URL.
#
#   docker build -t checkoutpilot .
#   docker run -p 10000:10000 --env-file .env checkoutpilot      # then open http://localhost:10000

# ---- 1. Build the dashboard as static files (served by the backend) ----
FROM node:22-bookworm-slim AS dashboard
WORKDIR /app/frontend-react
COPY frontend-react/package.json frontend-react/package-lock.json frontend-react/.npmrc ./
RUN npm ci --no-audit --no-fund
COPY frontend-react/ ./
# "same-origin" = the dashboard calls the backend at its own address.
ENV CHECKOUTPILOT_STATIC=1 VITE_API_BASE_URL=same-origin
RUN npm run build

# ---- 2. Backend + scanner + verifier (Chromium comes with this image) ----
# The image version must match the playwright pip version below.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble
LABEL org.opencontainers.image.source="https://github.com/shravanisy2006/CheckoutPilot" \
      org.opencontainers.image.description="CheckoutPilot: find, rank, fix and prove PayPal checkout upgrades" \
      org.opencontainers.image.licenses="MIT"
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app

COPY requirements.txt ./
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt "playwright==1.63.0"

COPY . .
COPY --from=dashboard /app/frontend-react/dist/client /app/dashboard

# Hosted defaults (secrets such as PayPal / Gemini keys are set in Azure or Render, never baked in).
ENV APP_ENV=production \
    PORT=10000 \
    DASHBOARD_DIR=/app/dashboard \
    START_DEMO_STORES=true \
    ALLOW_LOCALHOST_SCANS=true \
    VERIFY_HEADLESS=true \
    RATE_LIMIT_PER_HOUR=30 \
    OUTPUTS_MAX_AGE_HOURS=24 \
    ASYNC_JOBS=true

EXPOSE 10000
# One worker on purpose: scans, fixes and proofs are kept in memory.
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips='*'"]
