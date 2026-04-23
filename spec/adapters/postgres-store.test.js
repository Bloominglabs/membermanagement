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

async function login(engine, username, password) {
  return engine.login({ username, password });
}

test("postgres runtime preserves workflow state across runtime recreation", async () => {
  const pool = await createPool();
  const seedDocument = createDefaultDocument({
    invoices: [],
    payments: [],
    donations: [],
    sessions: []
  });

  const firstRuntime = await createPostgresRuntime({
    pool,
    seedDocument
  });
  const admin = await login(firstRuntime.engine, "admin", "change-me");

  const member = await firstRuntime.engine.createMember({
    token: admin.token,
    fullName: "Guion Bluford",
    email: "guion@example.test",
    duesClass: "standard"
  });
  const invoice = await firstRuntime.engine.createInvoice({
    token: admin.token,
    memberId: member.id,
    description: "July dues",
    amountCents: 11000,
    dueDate: "2026-07-01"
  });
  await firstRuntime.engine.issueInvoice({
    token: admin.token,
    invoiceId: invoice.id
  });
  await firstRuntime.engine.recordManualPayment({
    token: admin.token,
    memberId: member.id,
    amountCents: 13000,
    method: "check"
  });

  const secondRuntime = await createPostgresRuntime({ pool });
  const secondAdmin = await login(secondRuntime.engine, "admin", "change-me");
  const members = await secondRuntime.engine.listMembers({ token: secondAdmin.token });
  const summary = await secondRuntime.engine.getFinancialSummary({ token: secondAdmin.token });

  assert.equal(members.items.length, 3);
  assert.deepEqual(summary, {
    currency: "USD",
    receivableCents: 0,
    prepaidCents: 2000,
    donationsYtdCents: 0
  });

  await pool.end();
});

