# Deployment Notes

## Current Deployment Shape

The rewrite can currently run in three modes:

- in-memory demo mode for local evaluation
- JSON-file persistence mode for single-instance testing
- PostgreSQL-backed mode for hosted deployments
- Cloud SQL connector mode for Google Cloud SQL for PostgreSQL

## Environment Variables

- `PORT`: HTTP listen port. Defaults to `3000`.
- `ALLOWED_WEB_ORIGINS`: comma-separated frontend origins allowed to call the API.
- `SESSION_LIFETIME_MINUTES`: optional bearer-token lifetime in minutes. Defaults to `720`.
- `DATA_FILE_PATH`: when set, the server uses the durable JSON-file adapter at this path.
- `DATABASE_URL`: when set, the server uses the normalized PostgreSQL adapter if Cloud SQL connector env is not present.
- `BOOTSTRAP_ADMIN_USERNAME`: optional initial admin username for a fresh store.
- `BOOTSTRAP_ADMIN_PASSWORD`: optional initial admin password for a fresh store.
- `INSTANCE_CONNECTION_NAME`: when set, the server prefers the Cloud SQL connector path.
- `DB_USER`: PostgreSQL username for direct Postgres or Cloud SQL connector mode.
- `DB_PASS`: PostgreSQL password for direct Postgres or Cloud SQL connector mode unless IAM DB auth is enabled.
- `DB_NAME`: PostgreSQL database name for Cloud SQL connector mode.
- `DB_POOL_MAX`: optional pool size for Cloud SQL connector mode. Defaults to `5`.
- `CLOUDSQL_IP_TYPE`: optional Cloud SQL connector IP type. Defaults to `PUBLIC`. Set `PRIVATE` for private IP.
- `DB_IAM_AUTH`: optional `true`/`1` flag to use Cloud SQL automatic IAM database authentication.

## Local Persistent Run

```bash
mkdir -p var/data
DATA_FILE_PATH=var/data/store.json ALLOWED_WEB_ORIGINS=http://127.0.0.1:3000 npm start
```

The admin shell is then available at `http://127.0.0.1:3000/`.

## Hosted PostgreSQL Run

```bash
DATABASE_URL=postgres://app:secret@db.example/membermanagement \
BOOTSTRAP_ADMIN_USERNAME=treasurer \
BOOTSTRAP_ADMIN_PASSWORD='replace-this' \
ALLOWED_WEB_ORIGINS=https://your-org.github.io \
npm start
```

## Cloud SQL Connector Run

```bash
INSTANCE_CONNECTION_NAME=project-id:region:instance-id \
DB_USER=appuser \
DB_PASS='replace-this' \
DB_NAME=membermanagement \
BOOTSTRAP_ADMIN_USERNAME=treasurer \
BOOTSTRAP_ADMIN_PASSWORD='replace-this-too' \
ALLOWED_WEB_ORIGINS=https://your-org.github.io \
npm start
```

## Resource Setup Actions Required

To deploy this branch on a hosted platform, you must provision:

1. A PostgreSQL database.
2. A database user with read/write access to that database.
3. An initial admin username and password, provided via `BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD` on first boot.
4. A static frontend origin, added to `ALLOWED_WEB_ORIGINS`.

If you deploy on Google Cloud SQL with the connector path, you must also:

1. Enable the Cloud SQL Admin API.
2. Grant the runtime identity the `Cloud SQL Client` IAM role.
3. Provide Application Default Credentials in the runtime environment.
4. Configure the Cloud Run service with the Cloud SQL instance connection.
5. Supply `INSTANCE_CONNECTION_NAME`, `DB_USER`, `DB_NAME`, and either `DB_PASS` or IAM DB auth settings.

If you host the static admin separately, you must also point `frontend/admin/config.js` at the API origin used by the deployment.

## Static Frontend Hosting

The admin client in `frontend/admin/` can be hosted separately from the API. Point `frontend/admin/config.js` at the API origin:

```js
window.MemberManagementConfig = {
  apiBaseUrl: "https://your-api.example"
};
```

The API must then allow that origin via `ALLOWED_WEB_ORIGINS`.

## Current Production Caveat

The normalized PostgreSQL adapter and Cloud SQL connector path are now appropriate for deployment of the currently rebuilt workflows. The main remaining deployment gaps are feature coverage outside the rebuilt surface area and the absence of scheduled cleanup for expired sessions.
