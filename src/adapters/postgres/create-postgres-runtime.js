import pg from "pg";

import { createDocumentRuntime } from "../store/create-document-runtime.js";
import { createDefaultDocument, normalizeDocument } from "../store/default-document.js";

const { Pool } = pg;

const STATE_SLOT = 1;

function clone(value) {
  return structuredClone(value);
}

function documentsEqual(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

async function ensureSchema(pool) {
  await pool.query(`
    create table if not exists app_state (
      slot integer,
      document text
    )
  `);
}

async function readStoredDocument(pool) {
  const result = await pool.query(
    "select document from app_state where slot = $1",
    [STATE_SLOT]
  );

  if (result.rowCount === 0) {
    return null;
  }

  return JSON.parse(result.rows[0].document);
}

async function writeStoredDocument(pool, document) {
  await pool.query("delete from app_state where slot = $1", [STATE_SLOT]);
  await pool.query(
    "insert into app_state (slot, document) values ($1, $2)",
    [STATE_SLOT, JSON.stringify(document)]
  );
}

async function ensureSeedDocument(pool, seedDocument) {
  await ensureSchema(pool);

  const existingDocument = await readStoredDocument(pool);
  if (!existingDocument) {
    const document = normalizeDocument(clone(seedDocument ?? createDefaultDocument()));
    await writeStoredDocument(pool, document);
    return document;
  }

  const normalizedDocument = normalizeDocument(existingDocument);
  if (!documentsEqual(existingDocument, normalizedDocument)) {
    await writeStoredDocument(pool, normalizedDocument);
  }

  return normalizedDocument;
}

function createPoolFromOptions({ connectionString, ssl } = {}) {
  return new Pool({
    connectionString,
    ...(ssl ? { ssl } : {})
  });
}

export async function createPostgresRuntime({
  pool = null,
  connectionString,
  ssl,
  allowedOrigins = [],
  clock,
  seedDocument
} = {}) {
  const runtimePool = pool ?? createPoolFromOptions({ connectionString, ssl });
  const document = await ensureSeedDocument(runtimePool, seedDocument);

  const runtime = createDocumentRuntime({
    document,
    allowedOrigins,
    clock,
    loadDocument: async () => {
      return readStoredDocument(runtimePool);
    },
    persistDocument: async (nextDocument) => {
      await writeStoredDocument(runtimePool, nextDocument);
    }
  });

  runtime.pool = runtimePool;
  runtime.close = async () => {
    if (!pool) {
      await runtimePool.end();
    }
  };

  return runtime;
}
