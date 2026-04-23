import { createFileRuntime } from "./adapters/file/create-file-runtime.js";
import { createInMemoryRuntime } from "./adapters/inmemory/create-in-memory-runtime.js";
import { createAppServer } from "./interfaces/http/create-app-server.js";

function parseAllowedOrigins(value) {
  if (!value) {
    return [];
  }

  return value
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean);
}

async function createRuntime() {
  const allowedOrigins = parseAllowedOrigins(process.env.ALLOWED_WEB_ORIGINS);

  if (process.env.DATA_FILE_PATH) {
    return createFileRuntime({
      dataFilePath: process.env.DATA_FILE_PATH,
      allowedOrigins
    });
  }

  return createInMemoryRuntime({
    allowedOrigins
  });
}

const runtime = await createRuntime();
const server = createAppServer(runtime);
const port = Number(process.env.PORT ?? 3000);

server.listen(port, "0.0.0.0", () => {
  process.stdout.write(`membermanagement-rewrite listening on http://0.0.0.0:${port}\n`);
});
