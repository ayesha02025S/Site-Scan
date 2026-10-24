FROM node:22-bookworm-slim AS axe
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    MAX_CONCURRENT_SCANS=1 \
    PORT=8000
WORKDIR /app/backend
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt \
    && python -m playwright install --with-deps chromium \
    && useradd --create-home --uid 10001 sitescan \
    && mkdir -p /app/backend \
    && chown -R sitescan:sitescan /app /ms-playwright
COPY --from=axe /build/node_modules ./node_modules
COPY --chown=sitescan:sitescan *.py ./
USER sitescan
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
