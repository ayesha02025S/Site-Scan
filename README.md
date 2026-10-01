# Site-Scan

CS 4094

M1: A user enters a URL, Site Scan checks that single page, saves the results, and displays them.

Site Scan is a full-stack website auditing application with a minimal dark interface. M1 implements 12 deterministic performance, accessibility, and security checks, persistent scan history, category scores, expandable findings, and JSON report export.

## Stack

- Next.js 16, React, and TypeScript frontend
- Python 3.13 and FastAPI backend
- SQLAlchemy with SQLite by default; PostgreSQL is supported through `DATABASE_URL`
- aiohttp for bounded HTTP requests and Beautiful Soup for static HTML checks

## Run locally

Install Git, Node.js 24 LTS with npm, and Python 3.13. Use the latest patch releases in those versions. Open the repository folder in VS Code.

```sh
git clone https://github.com/ayesha02025S/Site-Scan.git
cd Site-Scan
cp .env.example .env
cp frontend/.env.example frontend/.env.local
```

No database server or API key is needed for the default local setup. Run the backend and frontend in two terminals.

### Backend

```sh
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

The API runs at http://localhost:8000. Interactive API documentation is at http://localhost:8000/docs.

### Frontend

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:3000, enter a public URL, and select **Run assessment**. Results appear automatically. Select **Scan history** to reopen a saved assessment. Use the category filters and **Issues only** checkbox to narrow findings, expand a check for evidence and remediation, or select **Export JSON** to download the report.

On subsequent runs, activate the existing Python environment and start both servers. Repeat dependency installation when a lockfile changes.

### Windows PowerShell

Use `Copy-Item .env.example .env` and `Copy-Item frontend/.env.example frontend/.env.local` for the configuration files. In `backend`, create the environment with `py -3.13 -m venv .venv`, then activate it with `.\.venv\Scripts\Activate.ps1`. The pip, Uvicorn, and npm commands are the same.

## Configuration

The backend loads `.env` from the repository root. Existing shell variables take precedence. The frontend loads `frontend/.env.local`.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Defaults to SQLite; relative SQLite paths are resolved inside `backend/`. |
| `FRONTEND_ORIGIN` | Frontend origin allowed by API CORS; defaults to `http://localhost:3000`. |
| `NEXT_PUBLIC_API_BASE_URL` | API address for the frontend; defaults to `http://localhost:8000`. |
| `OPENAI_API_KEY` | Reserved for a future milestone. Not used or required by M1. |

To use PostgreSQL, create a database and database user, then set `DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/sitescan` in your local `.env`. The backend creates the initial scans table on startup. Schema migrations are not implemented yet. Restart the backend after changing its configuration; restart or rebuild the frontend after changing its public API URL.

Local environment files, database files, dependencies, and generated builds are excluded from Git. Keep real credentials out of `.env.example` and never put a secret in a `NEXT_PUBLIC_` variable.

## Checks and scoring

- Performance: successful HTTP response, HTML fetch time ≤ 1,500 ms, decoded HTML size ≤ 300 KB.
- Accessibility: non-empty page title and language, image alt attributes, detectable form labels.
- Security: HTTPS from the submitted URL through the final page, CSP presence, positive HSTS max-age on HTTPS, `nosniff`, and Referrer-Policy presence.

Checks have weights of 3 (high), 2 (medium), or 1 (low). A category score is the percentage of its available weight earned by passed checks. Overall health is the rounded mean of the three category scores. Missing images or supported form controls pass their respective checks because no matching issues were found.

These are basic project heuristics, not a Lighthouse score, WCAG certification, or a complete security audit. Fetch time measures server-side HTML retrieval including redirects, not browser rendering or Core Web Vitals. Static HTML checks cannot assess JavaScript-rendered content, contrast, keyboard navigation, or the quality of labels and alt text. Header presence checks do not validate complete policies.

## API

| Method | Endpoint | Result |
| --- | --- | --- |
| `GET` | `/health` | API availability |
| `POST` | `/scans` | Accepts `{"url":"https://example.com"}`, saves a queued scan, and returns HTTP 202 with its ID |
| `GET` | `/scans/{id}` | Scan status, results, or failure reason |
| `GET` | `/scans` | Latest 100 scans, newest first |
| `GET` | `/scans/{id}/export` | Download a saved scan as JSON |

Scans move through `queued`, `running`, and `completed` or `failed`. Each scan is saved in the database. Up to three scans run concurrently, with at most 12 pending tasks in one API process. Tasks run in-process for M1; run one Uvicorn worker. On restart, unfinished scans are marked failed with an explanation. Completed history survives restarts.

## Validation

From `backend/` with the virtual environment activated:

```sh
python -m pytest -q
```

From `frontend/`:

```sh
npm run typecheck
npm run build
```

Tests cover known HTML defects and passing fixtures, scoring, unsafe URLs, DNS resolution, redirect limits, response limits, API errors, persistence, and restart recovery. Tests use temporary databases and controlled responses; they do not depend on public websites.

If your Mac reports `EMFILE` watcher errors, start the frontend with `WATCHPACK_POLLING=true npm run dev`. For a production-mode local preview, run `npm run build` followed by `npm start`.

## M1 boundaries

The scanner fetches one page, follows at most five redirects, accepts HTTP/HTTPS on ports 80 and 443, limits decoded HTML to 2 MB, and times out after 25 seconds. It validates public IP addresses during DNS resolution and checks every redirect destination. TLS verification stays enabled. It does not execute scripts, submit forms, follow links, send credentials, or retain fetched HTML.

M1 is a local prototype without authentication or per-user scan isolation. Before public deployment, add access controls, per-user rate limits, database migrations, and durable background workers. Crawling, broken-link checks, rendered accessibility tests, scan comparisons, and LLM summaries are later milestones.

## Repository structure

```text
Site-Scan/
├── frontend/
│   ├── app/
│   ├── package.json
│   └── package-lock.json
├── backend/
│   ├── main.py
│   ├── scanner.py
│   ├── database.py
│   ├── tests/
│   ├── requirements.txt
│   └── requirements.lock.txt
├── docs/
│   └── architecture.md
├── .env.example
└── README.md
```
