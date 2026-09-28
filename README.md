# Site-Scan
CS 4094

M1: A user enters a URL, Site Scan checks that single page, saves the results, and displays them.

Site Scan is a planned full-stack application for non-intrusive website performance, accessibility, and security checks. Deterministic checks will produce findings; optional LLM summaries will explain those findings.

## Current status

This repository contains the initial folder structure only. The frontend, API, database integration, and scanner are not implemented yet. There is no runnable application at this stage.

## Repository structure

```text
Site-Scan/
├── frontend/
├── backend/
├── docs/
├── .gitignore
├── .env.example
└── README.md
```

Each empty folder contains `.gitkeep` so Git includes it in the repository. Remove that placeholder when adding source files.

## Local setup for every teammate

1. Install Git, [Node.js 24 LTS](https://nodejs.org/en/download) with npm, [Python 3.13](https://www.python.org/downloads/), and VS Code. Use the latest patch release within these versions.
2. Clone the repository and open it in VS Code:

   ```sh
   git clone https://github.com/ayesha02025S/Site-Scan.git
   cd Site-Scan
   code .
   ```

   If `code` is unavailable, use **File > Open Folder** in VS Code and select `Site-Scan`.
3. Copy `.env.example` to `.env` at the repository root. On macOS/Linux:

   ```sh
   cp .env.example .env
   ```

   On Windows PowerShell:

   ```powershell
   Copy-Item .env.example .env
   ```

   Replace placeholders locally when the database is configured. The template does not provision PostgreSQL or automatically load environment variables. Backend initialization must add that loading behavior.

## Application initialization, once per team

Assign owners to initialize the applications and commit the generated source and dependency files before teammates use the startup commands below.

- Frontend owner: initialize Next.js with TypeScript inside `frontend/`, add an `npm run dev` script, and commit `package.json` and `package-lock.json`.
- Backend owner: create `backend/main.py` with a FastAPI instance named `app`, commit `backend/requirements.txt` including FastAPI and Uvicorn, and implement loading of the root `.env` file.
- Database owner: document PostgreSQL provisioning and migrations once storage is implemented. Redis and background workers will be added in a later milestone.

## Starting locally after initialization

These commands are the agreed startup convention; they will work only after the files described above have been implemented and committed.

Open two terminals in VS Code, starting from the repository root.

### Terminal 1: frontend

Create `frontend/.env.local` containing this public setting:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Then run:

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:3000. Run `npm ci` on first setup or when the lockfile changes.

### Terminal 2: backend

```sh
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

On Windows, use `py -3.13 -m venv .venv` and activate with `.\.venv\Scripts\Activate.ps1` instead. Create the virtual environment only once; activate it in each new terminal. Install requirements on first setup or when they change.

The API will be available at http://localhost:8000 and its FastAPI documentation at http://localhost:8000/docs. Configure backend CORS for the local frontend origin when connecting the two applications.

## Credentials and Git

- Commit `.env.example` with placeholders only. Never commit passwords, API keys, or real connection strings.
- `.env`, environment overrides such as `frontend/.env.local`, dependencies, and virtual environments are excluded by `.gitignore`.
- Variables starting with `NEXT_PUBLIC_` are public. Backend API keys must never use that prefix.
- Review `git diff --staged` before committing. Ignoring a file does not remove secrets already tracked by Git; revoke any accidentally committed credential.
