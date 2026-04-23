import test from "node:test";
import assert from "node:assert/strict";

import { newDb } from "pg-mem";

import { createPostgresRuntime } from "../../src/adapters/postgres/create-postgres-runtime.js";
import { createDefaultDocument } from "../../src/adapters/store/default-document.js";

async function createPool() {
  const db = newDb();
  const adapter = db.adapters.createPg();
  return new adapter.Pool();
}

async function listTables(pool) {
  const result = await pool.query("select table_name from information_schema.tables where table_schema = 'public' order by table_name");
  return result.rows.map((row) => row.table_name);
}

test("postgres runtime creates normalized tables instead of legacy app_state storage", async () => {
  const pool = await createPool();

  await createPostgresRuntime({
    pool,
    seedDocument: createDefaultDocument()
  });

  const tables = await listTables(pool);

  assert.equal(tables.includes("accounts"), true);
  assert.equal(tables.includes("sessions"), true);
  assert.equal(tables.includes("members"), true);
  assert.equal(tables.includes("payments"), true);
  assert.equal(tables.includes("payment_allocations"), true);
  assert.equal(tables.includes("app_state"), false);

  await pool.end();
});

