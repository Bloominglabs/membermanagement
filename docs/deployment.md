# Deployment Notes

## Current Deployment Shape

The rewrite can currently run in two modes:

- in-memory demo mode for local evaluation
- JSON-file persistence mode for single-instance testing or light-duty deployment

## Environment Variables

- `PORT`: HTTP listen port. Defaults to `3000`.
- `ALLOWED_WEB_ORIGINS`: comma-separated frontend origins allowed to call the API.
- `DATA_FILE_PATH`: when set, the server uses the durable JSON-file adapter at this path.

## Local Persistent Run

```bash
mkdir -p var/data
DATA_FILE_PATH=var/data/store.json ALLOWED_WEB_ORIGINS=http://127.0.0.1:3000 npm start
```

The admin shell is then available at `http://127.0.0.1:3000/`.

## Static Frontend Hosting

The admin client in `frontend/admin/` can be hosted separately from the API. Point `frontend/admin/config.js` at the API origin:

```js
window.MemberManagementConfig = {
  apiBaseUrl: "https://your-api.example"
};
```

The API must then allow that origin via `ALLOWED_WEB_ORIGINS`.

## Current Production Caveat

The JSON-file adapter is a valid persistence bridge for a single-instance deployment, but it is not the final production store for multi-instance or Cloud Run-style deployments. The next deployment-critical step is a durable networked adapter behind the same repository ports.

