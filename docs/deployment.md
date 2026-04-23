# Deployment Notes

## Current Deployment Shape

The rewrite can currently run in three modes:

- in-memory demo mode for local evaluation
- JSON-file persistence mode for single-instance testing
- PostgreSQL-backed mode for hosted deployments

## Environment Variables

- `PORT`: HTTP listen port. Defaults to `3000`.
- `ALLOWED_WEB_ORIGINS`: comma-separated frontend origins allowed to call the API.
- `DATA_FILE_PATH`: when set, the server uses the durable JSON-file adapter at this path.
- `DATABASE_URL`: when set, the server uses the PostgreSQL adapter and prefers it over `DATA_FILE_PATH`.
- `BOOTSTRAP_ADMIN_USERNAME`: optional initial admin username for a fresh store.
- `BOOTSTRAP_ADMIN_PASSWORD`: optional initial admin password for a fresh store.

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

## Resource Setup Actions Required

To deploy this branch on a hosted platform, you must provision:

1. A PostgreSQL database.
2. A database user with read/write access to that database.
3. A `DATABASE_URL` secret for the service.
4. An initial admin username and password, provided via `BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD` on first boot.
5. A static frontend origin, added to `ALLOWED_WEB_ORIGINS`.

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

The PostgreSQL adapter removes the filesystem dependency, but it still stores the application state as a single document and the engine's multi-step workflows are not yet wrapped in broader database transactions. For hosted deployment right now, run the application as a single instance until the normalized SQL adapter lands.
