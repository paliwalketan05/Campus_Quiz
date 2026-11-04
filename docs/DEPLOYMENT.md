# Staging Deployment Handover

This guide prepares a staging deployment; it does not provision cloud resources or
run database migrations. Do not deploy the application to production until the
staging checks below pass.

## Required staging resources

- A dedicated staging PostgreSQL database using the project schema and a
  least-privilege `campusquiz_app` runtime role.
- A backend service running `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- A static frontend host configured to build `frontend` with `npm ci &&
  npm run build` and publish `frontend/dist`.
- HTTPS origins for both frontend and backend.

Keep staging and production databases, signing secrets, and accounts separate.
Never use migration-owner credentials as the API runtime database URL.

## Backend environment

Configure these values in the backend provider's secret/environment settings:

| Variable | Staging value |
| --- | --- |
| `APP_DATABASE_URL` | Direct, unpooled PostgreSQL URL for the staging `campusquiz_app` role |
| `AUTH_HMAC_SECRET` | Secret matching the staging database `app_auth_config` |
| `JWT_SECRET_KEY` | Independent random secret, at least 32 bytes |
| `CORS_ALLOWED_ORIGINS` | Exact HTTPS origin of the deployed frontend; no wildcard |
| `AUTH_COOKIE_SECURE` | `true` |
| `AUTH_COOKIE_SAMESITE` | `none` when frontend and API are cross-site; otherwise `lax` |
| `AUTH_COOKIE_DOMAIN` | Leave unset for unrelated provider domains |

Use the configured `PORT` provided by the hosting platform. Verify
`GET /health/live` and `GET /health/ready` before connecting the frontend.

Apply migrations only through the migration runner and a separately managed
migration-owner URL. Confirm the target database and migration status before
running `--migrate`; do not run migrations against production from a staging
deployment workflow.

## Frontend environment

Set `VITE_API_BASE_URL` at build time to the backend's full API base, for example
`https://<staging-api-host>/api/v1`. Vite embeds this value in the static build;
it is not a runtime secret. Configure the backend CORS origin to exactly match
the frontend's HTTPS origin. Cross-site cookie deployments require
`AUTH_COOKIE_SAMESITE=none` and `AUTH_COOKIE_SECURE=true`.

For local development, create `frontend/.env.local` from
[`frontend/.env.example`](../frontend/.env.example).

## Staging acceptance checklist

1. Confirm the backend readiness endpoint reaches only the staging database.
2. Confirm frontend login, refresh, CSRF-protected mutations, and logout over
   HTTPS using test accounts.
3. Exercise student discovery, attempt start, autosave, submission, and
   visibility-gated results with disposable staging data.
4. Exercise faculty authoring, session lifecycle, release controls, and
   analytics; verify an unrelated tenant cannot read the data.
5. Capture and review database backups, then rehearse restoring one into an
   isolated database before onboarding real users.
6. Run browser end-to-end and concurrency/load tests only against a separately
   provisioned staging environment with authorized disposable accounts.
7. Record the deployment commit, migration status, rollback procedure, and
   operational contacts before approving production promotion.

No live database, backup, browser end-to-end, concurrency, or provider deployment
verification has been performed from this repository workspace.
