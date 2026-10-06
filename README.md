# Site-Scan

CS 4094

M1: A user enters a URL, Site Scan checks that single page, saves the results, and displays them.

Site Scan is a full-stack website auditing application with a minimal dark interface. Site Scan includes 13 static/link checks plus 9 rendered accessibility rules using Playwright Chromium and axe-core, persistent scan history, comparison with the previous scan of the same URL, category scores, expandable findings, and JSON report export.

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
npm ci
python install_browser.py
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

The browser installer stores Chromium in the ignored `backend/.browsers/` directory. To install Chromium system dependencies on Linux, use `python install_browser.py --with-deps`. Run the service as a non-root user with Chromium sandbox support. If the browser cannot start, static results remain available and browser rules are labeled inconclusive.

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

Use `Copy-Item .env.example .env` and `Copy-Item frontend/.env.example frontend/.env.local` for the configuration files. In `backend`, create the environment with `py -3.13 -m venv .venv`, then activate it with `.\.venv\Scripts\Activate.ps1`. The pip, browser installation, Uvicorn, and npm commands are the same.

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

- Performance: successful HTTP response, HTML fetch time ≤ 1,500 ms, decoded HTML size ≤ 300 KB, and up to 20 unique HTTP/HTTPS links checked for 404, 410, or server errors. Malformed/private links are skipped. Timeouts, connection failures, authentication restrictions, and rate limits are inconclusive. Counts distinguish discovered, checked, skipped, and inconclusive links.
- Accessibility: non-empty page title and language, image alt attributes, and detectable form labels in static HTML. Chromium also renders the page and runs nine axe-core rules for color contrast, accessible button names, and ARIA attributes, values, roles, and relationships. Expand a finding to see affected CSS selectors, HTML snippets, and specific fixes. At most 20 affected elements per rule are saved; the total count remains visible.
- Security: HTTPS from the submitted URL through the final page, CSP presence, positive HSTS max-age on HTTPS, `nosniff`, and Referrer-Policy presence.

Checks have weights of 3 (high), 2 (medium), or 1 (low). A category score is the percentage of evaluated weight earned by passed checks. Inconclusive and not-applicable checks receive no credit and are excluded from the denominator. A partial report can therefore have a high score; review the coverage notice as well as the score. Overall health is the rounded mean of the three category scores. Missing images or supported form controls pass their static checks because no matching issues were found. Rendered rules without applicable elements and pages without links are marked not applicable. Browser/resource failures never turn into passing results.

These are basic project heuristics, not a Lighthouse score, WCAG certification, or a complete security audit. Fetch time measures server-side HTML retrieval including redirects, not browser rendering or Core Web Vitals. The browser audit checks a desktop snapshot at 1280 × 900 after load and a short settling interval. It does not certify every interaction, responsive breakpoint, embedded frame, keyboard behavior, or the quality of labels and alt text. Restricted or failed resources, page script errors, and embedded frames mark coverage partial; confirmed violations are retained and other rendered rules become inconclusive. Header presence checks do not validate complete policies.

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
npm test
npm run typecheck
npm run build
```

Tests cover malformed links, partial scoring, URL normalization, version-aware comparisons, unsafe destinations and redirects, response limits, API persistence, and restart recovery. A real Chromium integration test detects contrast, a JavaScript-created unnamed button, and invalid ARIA in a controlled fixture, then verifies the corrected fixture passes. Tests use temporary databases and controlled responses. Install Chromium and axe-core before running the complete suite; `python -m pytest -q -m "not browser"` runs the backend unit tests alone.

If your Mac reports `EMFILE` watcher errors, start the frontend with `WATCHPACK_POLLING=true npm run dev`. For a production-mode local preview, run `npm run build` followed by `npm start`.

## M1 boundaries

The scanner fetches one page, follows at most five redirects, accepts HTTP/HTTPS on ports 80 and 443, and limits decoded HTML to 2 MB. Page fetching has a 25-second deadline, link checks an 8-second budget, and the browser phase a separate 35-second deadline. Static/link results remain available if the browser fails.

Browser HTTP requests are intercepted and fetched through the same public-only DNS resolver, pinning validated addresses to the connection. Every redirect is validated. Browser traffic that bypasses interception is sent to a local deny proxy; WebSockets and service workers are blocked. Resource requests are limited to GET, 80 requests, 3 MB per resource, and 15 MB total. No user cookies or credentials are forwarded; TLS checks remain enabled. Fetched page scripts execute in an isolated, sandboxed Chromium instance that is closed after each audit. Embedded frames and interaction-dependent states are outside this audit's coverage. Use container-level egress restrictions and resource limits before production deployment.

Reports store scanner/scoring versions. Comparison matches normalized URLs and compares only compatible versions. Score deltas require the same evaluated check set. New rules and previously inconclusive rules are not counted as newly introduced issues. Older reports remain readable but cannot be treated as a comparable baseline; run two new scans for a valid comparison. Comparison currently uses the latest 100 saved records and operates at the check/rule level.

This is a local prototype without authentication or per-user isolation. Before public deployment, add access controls, per-user rate limits, migrations, and durable workers. Full crawling, deeper browser coverage, and LLM summaries remain later milestones.

## Repository structure

```text
Site-Scan/
├── frontend/
│   ├── app/
│   ├── package.json
│   └── package-lock.json
├── backend/
│   ├── main.py
│   ├── accessibility.py
│   ├── network.py
│   ├── install_browser.py
│   ├── package-lock.json
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
