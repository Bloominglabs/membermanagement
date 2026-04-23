import { createFileRuntime } from "../adapters/file/create-file-runtime.js";
import { createInMemoryRuntime } from "../adapters/inmemory/create-in-memory-runtime.js";
import { createPostgresRuntime } from "../adapters/postgres/create-postgres-runtime.js";
import { createDefaultDocument } from "../adapters/store/default-document.js";

export function parseAllowedOrigins(value) {
  if (!value) {
    return [];
  }

  return value
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean);
}

function createSeedDocumentFromEnv(env) {
  if (!env.BOOTSTRAP_ADMIN_USERNAME && !env.BOOTSTRAP_ADMIN_PASSWORD) {
    return undefined;
  }

  return createDefaultDocument({
    accounts: [
      {
        id: "acct-admin",
        username: env.BOOTSTRAP_ADMIN_USERNAME || "admin",
        password: env.BOOTSTRAP_ADMIN_PASSWORD || "change-me",
        roles: ["staff-admin"]
      }
    ],
    sessions: []
  });
}

export async function createRuntimeFromEnv({
  env = process.env,
  factories = {}
} = {}) {
  const allowedOrigins = parseAllowedOrigins(env.ALLOWED_WEB_ORIGINS);
  const seedDocument = createSeedDocumentFromEnv(env);
  const createPostgres = factories.createPostgresRuntime ?? createPostgresRuntime;
  const createFile = factories.createFileRuntime ?? createFileRuntime;
  const createInMemory = factories.createInMemoryRuntime ?? createInMemoryRuntime;

  if (env.DATABASE_URL) {
    return createPostgres({
      connectionString: env.DATABASE_URL,
      allowedOrigins,
      ...(seedDocument ? { seedDocument } : {})
    });
  }

  if (env.DATA_FILE_PATH) {
    return createFile({
      dataFilePath: env.DATA_FILE_PATH,
      allowedOrigins,
      ...(seedDocument ? { initialDocument: seedDocument } : {})
    });
  }

  return createInMemory({
    allowedOrigins
  });
}
