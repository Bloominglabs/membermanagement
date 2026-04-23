import pg from "pg";
import { Connector } from "@google-cloud/cloud-sql-connector";

import { createFileRuntime } from "../adapters/file/create-file-runtime.js";
import { createInMemoryRuntime } from "../adapters/inmemory/create-in-memory-runtime.js";
import { createPostgresRuntime } from "../adapters/postgres/create-postgres-runtime.js";
import { createDefaultDocument } from "../adapters/store/default-document.js";

const { Pool } = pg;

function parsePositiveInteger(value, fallback) {
  const parsedValue = Number.parseInt(value, 10);

  if (Number.isInteger(parsedValue) && parsedValue > 0) {
    return parsedValue;
  }

  return fallback;
}

function parseBoolean(value) {
  return String(value ?? "").toLowerCase() === "true" || value === "1";
}

function requireEnvValue(env, key) {
  if (!env[key]) {
    throw new Error(`${key} is required`);
  }

  return env[key];
}

export function parseAllowedOrigins(value) {
  if (!value) {
    return [];
  }

  return value
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean);
}

function parseSessionLifetimeMinutes(value) {
  return parsePositiveInteger(value, 12 * 60);
}

function resolveCloudSqlIpType(env) {
  if (env.CLOUDSQL_IP_TYPE) {
    return env.CLOUDSQL_IP_TYPE;
  }

  if (parseBoolean(env.PRIVATE_IP)) {
    return "PRIVATE";
  }

  return "PUBLIC";
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

export async function createCloudSqlPoolFromEnv({
  env = process.env,
  ConnectorClass = Connector,
  PoolClass = Pool
} = {}) {
  const connector = new ConnectorClass();
  const usesIamAuthentication = parseBoolean(env.DB_IAM_AUTH);
  const instanceConnectionName = requireEnvValue(env, "INSTANCE_CONNECTION_NAME");
  const dbUser = requireEnvValue(env, "DB_USER");
  const dbName = requireEnvValue(env, "DB_NAME");

  if (!usesIamAuthentication) {
    requireEnvValue(env, "DB_PASS");
  }

  const clientOptions = await connector.getOptions({
    instanceConnectionName,
    ipType: resolveCloudSqlIpType(env),
    ...(usesIamAuthentication ? { authType: "IAM" } : {})
  });

  const pool = new PoolClass({
    ...clientOptions,
    user: dbUser,
    ...(usesIamAuthentication ? {} : { password: env.DB_PASS }),
    database: dbName,
    max: parsePositiveInteger(env.DB_POOL_MAX, 5)
  });

  pool.cloudSqlConnector = connector;
  return pool;
}

export async function createCloudSqlPostgresRuntime({
  env = process.env,
  allowedOrigins = [],
  seedDocument,
  sessionLifetimeMinutes,
  ConnectorClass = Connector,
  PoolClass = Pool,
  poolFactory = createCloudSqlPoolFromEnv,
  runtimeFactory = createPostgresRuntime
} = {}) {
  const pool = await poolFactory({
    env,
    ConnectorClass,
    PoolClass
  });

  const runtime = await runtimeFactory({
    pool,
    allowedOrigins,
    sessionLifetimeMinutes,
    ...(seedDocument ? { seedDocument } : {})
  });

  runtime.close = async () => {
    if (typeof pool.end === "function") {
      await pool.end();
    }

    if (typeof pool.cloudSqlConnector?.close === "function") {
      pool.cloudSqlConnector.close();
    }
  };

  return runtime;
}

export async function createRuntimeFromEnv({
  env = process.env,
  factories = {}
} = {}) {
  const allowedOrigins = parseAllowedOrigins(env.ALLOWED_WEB_ORIGINS);
  const seedDocument = createSeedDocumentFromEnv(env);
  const sessionLifetimeMinutes = env.SESSION_LIFETIME_MINUTES
    ? parseSessionLifetimeMinutes(env.SESSION_LIFETIME_MINUTES)
    : undefined;
  const createPostgres = factories.createPostgresRuntime ?? createPostgresRuntime;
  const createCloudSql = factories.createCloudSqlPostgresRuntime ?? createCloudSqlPostgresRuntime;
  const createFile = factories.createFileRuntime ?? createFileRuntime;
  const createInMemory = factories.createInMemoryRuntime ?? createInMemoryRuntime;

  if (env.INSTANCE_CONNECTION_NAME) {
    return createCloudSql({
      env,
      instanceConnectionName: env.INSTANCE_CONNECTION_NAME,
      allowedOrigins,
      ...(sessionLifetimeMinutes ? { sessionLifetimeMinutes } : {}),
      ...(seedDocument ? { seedDocument } : {})
    });
  }

  if (env.DATABASE_URL) {
    return createPostgres({
      connectionString: env.DATABASE_URL,
      allowedOrigins,
      ...(sessionLifetimeMinutes ? { sessionLifetimeMinutes } : {}),
      ...(seedDocument ? { seedDocument } : {})
    });
  }

  if (env.DATA_FILE_PATH) {
    return createFile({
      dataFilePath: env.DATA_FILE_PATH,
      allowedOrigins,
      ...(sessionLifetimeMinutes ? { sessionLifetimeMinutes } : {}),
      ...(seedDocument ? { initialDocument: seedDocument } : {})
    });
  }

  return createInMemory({
      allowedOrigins,
    ...(sessionLifetimeMinutes ? { sessionLifetimeMinutes } : {})
  });
}
