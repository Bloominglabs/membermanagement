import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";

import { createFileRuntime } from "../../src/adapters/file/create-file-runtime.js";
import { createDefaultDocument } from "../../src/adapters/store/default-document.js";

async function login(engine, username, password) {
  return engine.login({ username, password });
}

test("file runtime persists members, invoices, payments, donations, and applications across restart", async () => {
  const directory = await mkdtemp(join(tmpdir(), "membermanagement-file-runtime-"));
  const dataFile = join(directory, "store.json");

  const firstRuntime = await createFileRuntime({
    dataFilePath: dataFile,
    initialDocument: createDefaultDocument({
      invoices: [],
      payments: [],
      donations: [],
      sessions: []
    })
  });
  const adminSession = await login(firstRuntime.engine, "admin", "change-me");
  const member = await firstRuntime.engine.createMember({
    token: adminSession.token,
    fullName: "Katherine Johnson",
    email: "kj@example.test",
    duesClass: "standard"
  });
  const invoice = await firstRuntime.engine.createInvoice({
    token: adminSession.token,
    memberId: member.id,
    description: "May dues",
    amountCents: 10000,
    dueDate: "2026-05-01"
  });

  await firstRuntime.engine.issueInvoice({
    token: adminSession.token,
    invoiceId: invoice.id
  });
  await firstRuntime.engine.recordManualPayment({
    token: adminSession.token,
    memberId: member.id,
    amountCents: 12000,
    method: "check"
  });
  await firstRuntime.engine.recordDonation({
    token: adminSession.token,
    donorName: "Katherine Johnson",
    amountCents: 3500,
    source: "cash"
  });
  await firstRuntime.engine.submitSponsoredApplication({
    token: adminSession.token,
    applicantName: "Dorothy Vaughan",
    applicantEmail: "dv@example.test",
    notes: "Recommended by staff for testing persistence"
  });

  const secondRuntime = await createFileRuntime({ dataFilePath: dataFile });
  const secondAdminSession = await login(secondRuntime.engine, "admin", "change-me");

  const members = await secondRuntime.engine.listMembers({
    token: secondAdminSession.token
  });
  const applications = await secondRuntime.engine.listApplications({
    token: secondAdminSession.token
  });
  const summary = await secondRuntime.engine.getFinancialSummary({
    token: secondAdminSession.token
  });
  const persistedDocument = JSON.parse(await readFile(dataFile, "utf8"));

  assert.equal(members.items.length, 3);
  assert.equal(applications.items.length, 1);
  assert.deepEqual(summary, {
    currency: "USD",
    receivableCents: 0,
    prepaidCents: 2000,
    donationsYtdCents: 3500
  });
  assert.equal(persistedDocument.members.length, 3);
  assert.equal(persistedDocument.invoices.length, 1);
  assert.equal(persistedDocument.payments.length, 1);
  assert.equal(persistedDocument.donations.length, 1);
  assert.equal(persistedDocument.applications.length, 1);
});
