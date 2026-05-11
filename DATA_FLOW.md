# Data flow (local development)

This diagram describes how the local development stack connects and how authenticated requests flow through the API after the auth milestone.

**Persistence (orgs milestone).** The API defines `organizations` and `users` tables (see Alembic revision `a1b2c3d4e5f6`). The async `OrgRepository` reads and writes rows scoped by `organization_id` for all user lookups and lists. No HTTP handlers on `/orgs` yet beyond an empty router.

**Magic-link auth.** `POST /auth/magic-link` resolves `organization_slug` to an `organizations` row, optionally finds an active `users` row for that tenant and email, and always responds with HTTP 204. When a token is issued, a row is inserted into `magic_link_tokens` with a SHA-256 digest only (never the raw secret). `ConsoleEmailSender` prints the callback URL in local dev; production SES is stubbed. `GET /auth/callback` validates the token, marks it consumed, creates a `sessions` row (UUIDv7 primary key), sets the HttpOnly `wf_session` cookie, and redirects to `public_app_url`. `GET /auth/me` and `POST /auth/logout` use `get_request_auth`, which loads the session by cookie, enforces tenant match on `organization_id`, updates `last_seen_at`, and (for logout) sets `revoked_at`. Each state-changing step records `auth.magic_link.request`, `auth.magic_link.consume`, or `auth.logout` via `AuditWriter` when an organization context exists.

```mermaid
flowchart LR
  post[POST_auth_magic_link]
  tok[magic_link_tokens]
  mail[EmailSender]
  cb[GET_auth_callback]
  sess[sessions]
  cookie[wf_session_cookie]
  me[GET_auth_me]
  post --> tok
  post --> mail
  cb --> tok
  cb --> sess
  cb --> cookie
  cookie --> me
```

**Audit log (append-only).** Each HTTP request passes through `RequestContextMiddleware`, which assigns a UUIDv7 `request_id`, stores it on `request.state`, and binds `request_id` (plus basic HTTP fields) into structlog context variables so JSON logs include correlation metadata. State-changing handlers will call `AuditWriter.record` via the `get_audit_writer` FastAPI dependency; rows land in `audit_log_entries` (Alembic `f6e5d4c3b2a1`) with merged JSON metadata including `request_id`. PostgreSQL triggers reject `UPDATE` and `DELETE` on that table so the log stays append-only at the database layer, not only in application code.

```mermaid
flowchart LR
  http[HTTP_request]
  mw[RequestContextMiddleware]
  sl[structlog_contextvars]
  routes[FastAPI_routes]
  aw[AuditWriter_record]
  pg[(audit_log_entries)]
  http --> mw
  mw --> sl
  mw --> routes
  routes --> aw
  aw --> pg
```

```mermaid
flowchart LR
  subgraph client [Developer machine]
    Browser[Browser]
  end
  subgraph web [apps/web]
    Next[Next.js]
  end
  subgraph api [apps/api]
    FastAPI[FastAPI]
  end
  subgraph infra [infra/local Docker]
    Postgres[(Postgres 16 plus pgvector)]
    MinIO[(MinIO S3)]
    Redis[(Redis 7)]
  end

  Browser -->|HTTP :3000| Next
  Next -->|HTTP :8000 planned| FastAPI
  FastAPI -->|async SQLAlchemy| Postgres
  FastAPI -->|S3 API planned| MinIO
  Redis -.->|unused in app code| FastAPI
```

Redis is started for future queue work and is not used by the API in this milestone.
