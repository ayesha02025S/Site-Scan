# Deployment

Deploy the Next.js frontend to Vercel and run the FastAPI scanner as a persistent container service. The scanner starts asynchronous jobs after returning HTTP 202; it is not configured for a serverless request lifecycle.

## Frontend on Vercel

Import the GitHub repository and select `frontend` as the Root Directory. Use the Next.js framework preset, `npm ci` for installation, and `npm run build` for the build command.

Set `NEXT_PUBLIC_API_BASE_URL` to the backend's public HTTPS URL, without a trailing slash. This value is embedded at build time; redeploy the frontend if it changes. Do not put database credentials or Gemini keys in frontend variables.

## Backend container

Build from the backend directory:

```sh
docker build -t sitescan-backend backend
```

The container includes Python dependencies, Chromium, its Linux dependencies, and axe-core. It runs as a non-root user with Chromium sandboxing enabled. The hosting environment must support Chromium's sandbox; verify a rendered accessibility scan after deployment. A successful `/health` response alone does not verify browser support.

Configure these runtime variables in the hosting dashboard:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | The persistent PostgreSQL connection URL supplied by the database host |
| `FRONTEND_ORIGIN` | The exact Vercel production origin, such as `https://your-project.vercel.app`, without a trailing slash |
| `GEMINI_API_KEY` | Optional, backend only |
| `GEMINI_MODEL` | Optional; see the root environment template |
| `MAX_CONCURRENT_SCANS` | Defaults to 1 in the container to reduce Chromium memory use |
| `PORT` | Assigned by the host; defaults to 8000 |

Use `/health` for the health check. Run one worker and one backend replica: jobs and concurrency limits are currently in memory, and startup marks interrupted jobs failed. Multiple replicas require a shared job queue before scaling. Use PostgreSQL for hosted storage; local SQLite files can disappear on ephemeral hosting.

## Verify before sharing

Open the Vercel URL from another device. Submit a scan and confirm that it completes, reports rendered accessibility results, and displays the page summaries. Reopen its history entry and export the report. Restart the backend and confirm completed reports remain available. Test AI explanations separately if a Gemini key is configured.

The current app has shared scan history and no user accounts. Everyone with access to the app can see stored reports.

## Free hosting

Use Vercel Hobby for the frontend, Render Free for the backend, and Neon Free for PostgreSQL. Keep paid upgrades disabled. Render Free sleeps after inactivity and shares monthly free instance hours across the workspace. Its free PostgreSQL service expires after 30 days, so use Neon for this deployment. Chromium must be validated on Render before calling the deployment complete.

## Deployment status

These files prepare the application for deployment. They do not create a hosting account, database, or public deployment. Record the actual frontend and backend URLs here after deployment and verification.
