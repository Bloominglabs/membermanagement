import test from "node:test";
import assert from "node:assert/strict";

import { createInMemoryRuntime } from "../../src/adapters/inmemory/create-in-memory-runtime.js";

async function login(engine, username, password) {
  return engine.login({ username, password });
}

test("staff can create members, review applications, issue invoices, and record payments", async () => {
  const runtime = createInMemoryRuntime({
    accounts: [
      {
        id: "acct-admin",
        username: "admin",
        password: "change-me",
        roles: ["staff-admin"]
      },
      {
        id: "acct-sponsor",
        username: "sponsor",
        password: "member-secret",
        roles: ["member-self"],
        memberId: "mem-1000"
      }
    ],
    invoices: [],
    payments: [],
    donations: [],
    sessions: []
  });

  const sponsorSession = await login(runtime.engine, "sponsor", "member-secret");
  const application = await runtime.engine.submitSponsoredApplication({
    token: sponsorSession.token,
    applicantName: "Annie Easley",
    applicantEmail: "annie@example.test",
    notes: "Works in the machine shop"
  });

  assert.equal(application.status, "submitted");
  assert.equal(application.sponsorMemberId, "mem-1000");

  const adminSession = await login(runtime.engine, "admin", "change-me");
  const reviewedApplication = await runtime.engine.reviewApplication({
    token: adminSession.token,
    applicationId: application.id,
    decision: "approve"
  });

  assert.equal(reviewedApplication.status, "approved");
  assert.equal(reviewedApplication.member.status, "applicant");

  const invoice = await runtime.engine.createInvoice({
    token: adminSession.token,
    memberId: reviewedApplication.member.id,
    description: "Welcome dues",
    amountCents: 10000,
    dueDate: "2026-06-01"
  });

  assert.equal(invoice.status, "draft");

  const issuedInvoice = await runtime.engine.issueInvoice({
    token: adminSession.token,
    invoiceId: invoice.id
  });

  assert.equal(issuedInvoice.status, "issued");

  const payment = await runtime.engine.recordManualPayment({
    token: adminSession.token,
    memberId: reviewedApplication.member.id,
    amountCents: 12000,
    method: "cash"
  });

  assert.equal(payment.allocations.length, 1);
  assert.equal(payment.allocations[0].amountCents, 10000);

  const summary = await runtime.engine.getFinancialSummary({
    token: adminSession.token
  });

  assert.deepEqual(summary, {
    currency: "USD",
    receivableCents: 0,
    prepaidCents: 2000,
    donationsYtdCents: 0
  });
});

test("member-self can only use self-service operations", async () => {
  const runtime = createInMemoryRuntime({
    accounts: [
      {
        id: "acct-admin",
        username: "admin",
        password: "change-me",
        roles: ["staff-admin"]
      },
      {
        id: "acct-member",
        username: "member",
        password: "member-secret",
        roles: ["member-self"],
        memberId: "mem-1000"
      }
    ],
    invoices: [],
    payments: [],
    donations: [],
    sessions: []
  });

  const memberSession = await login(runtime.engine, "member", "member-secret");

  await assert.rejects(
    () => runtime.engine.createMember({
      token: memberSession.token,
      fullName: "Should Fail",
      email: "fail@example.test",
      duesClass: "standard"
    }),
    /forbidden/
  );

  const prepayment = await runtime.engine.recordSelfPrepayment({
    token: memberSession.token,
    amountCents: 2500,
    method: "card"
  });
  const donation = await runtime.engine.recordSelfDonation({
    token: memberSession.token,
    amountCents: 1700,
    source: "card"
  });
  const cancellation = await runtime.engine.cancelOwnMembership({
    token: memberSession.token,
    reason: "Moving away"
  });
  const application = await runtime.engine.submitSponsoredApplication({
    token: memberSession.token,
    applicantName: "Mae Jemison",
    applicantEmail: "mae@example.test",
    notes: "Interested in electronics"
  });

  assert.equal(prepayment.memberId, "mem-1000");
  assert.equal(donation.amountCents, 1700);
  assert.equal(cancellation.status, "left");
  assert.equal(application.status, "submitted");
});
