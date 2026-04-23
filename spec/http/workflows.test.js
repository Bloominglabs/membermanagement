import test from "node:test";
import assert from "node:assert/strict";
import { once } from "node:events";

import { createAppServer } from "../../src/interfaces/http/create-app-server.js";
import { createInMemoryRuntime } from "../../src/adapters/inmemory/create-in-memory-runtime.js";

async function startServer(options = {}) {
  const runtime = createInMemoryRuntime(options);
  const server = createAppServer(runtime);

  server.listen(0, "127.0.0.1");
  await once(server, "listening");

  const address = server.address();
  const baseUrl = `http://127.0.0.1:${address.port}`;

  return { server, baseUrl };
}

async function login(baseUrl, username, password) {
  const response = await fetch(`${baseUrl}/api/v1/session/login`, {
    method: "POST",
    headers: {
      "content-type": "application/json"
    },
    body: JSON.stringify({ username, password })
  });

  assert.equal(response.status, 200);
  return response.json();
}

test("staff workflows are exposed through the HTTP API", async (t) => {
  const { server, baseUrl } = await startServer({
    accounts: [
      {
        id: "acct-admin",
        username: "admin",
        password: "change-me",
        roles: ["staff-admin"]
      }
    ],
    invoices: [],
    payments: [],
    donations: [],
    sessions: []
  });
  t.after(() => server.close());

  const admin = await login(baseUrl, "admin", "change-me");
  const authHeaders = {
    authorization: `Bearer ${admin.token}`,
    "content-type": "application/json"
  };

  const memberResponse = await fetch(`${baseUrl}/api/v1/members`, {
    method: "POST",
    headers: authHeaders,
    body: JSON.stringify({
      fullName: "Mary Jackson",
      email: "mary@example.test",
      duesClass: "standard"
    })
  });
  const member = await memberResponse.json();
  assert.equal(memberResponse.status, 201);

  const invoiceResponse = await fetch(`${baseUrl}/api/v1/invoices`, {
    method: "POST",
    headers: authHeaders,
    body: JSON.stringify({
      memberId: member.id,
      description: "June dues",
      amountCents: 9000,
      dueDate: "2026-06-15"
    })
  });
  const invoice = await invoiceResponse.json();
  assert.equal(invoiceResponse.status, 201);

  const issueResponse = await fetch(`${baseUrl}/api/v1/invoices/${invoice.id}/issue`, {
    method: "POST",
    headers: authHeaders
  });
  assert.equal(issueResponse.status, 200);

  const paymentResponse = await fetch(`${baseUrl}/api/v1/payments/manual`, {
    method: "POST",
    headers: authHeaders,
    body: JSON.stringify({
      memberId: member.id,
      amountCents: 9500,
      method: "check"
    })
  });
  assert.equal(paymentResponse.status, 201);

  const reportResponse = await fetch(`${baseUrl}/api/v1/reports/financial-summary`, {
    headers: {
      authorization: `Bearer ${admin.token}`
    }
  });
  const report = await reportResponse.json();

  assert.equal(reportResponse.status, 200);
  assert.deepEqual(report, {
    currency: "USD",
    receivableCents: 0,
    prepaidCents: 500,
    donationsYtdCents: 0
  });
});

test("member-self routes are restricted to self-service actions", async (t) => {
  const { server, baseUrl } = await startServer({
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
  t.after(() => server.close());

  const member = await login(baseUrl, "member", "member-secret");
  const authHeaders = {
    authorization: `Bearer ${member.token}`,
    "content-type": "application/json"
  };

  const deniedResponse = await fetch(`${baseUrl}/api/v1/members`, {
    method: "POST",
    headers: authHeaders,
    body: JSON.stringify({
      fullName: "No Access",
      email: "no-access@example.test",
      duesClass: "standard"
    })
  });
  assert.equal(deniedResponse.status, 403);

  const prepaymentResponse = await fetch(`${baseUrl}/api/v1/self/prepayments`, {
    method: "POST",
    headers: authHeaders,
    body: JSON.stringify({
      amountCents: 2200,
      method: "card"
    })
  });

  const donationResponse = await fetch(`${baseUrl}/api/v1/self/donations`, {
    method: "POST",
    headers: authHeaders,
    body: JSON.stringify({
      amountCents: 1300,
      source: "card"
    })
  });

  const cancellationResponse = await fetch(`${baseUrl}/api/v1/self/cancellation`, {
    method: "POST",
    headers: authHeaders,
    body: JSON.stringify({
      reason: "Moving away"
    })
  });

  const applicationResponse = await fetch(`${baseUrl}/api/v1/self/sponsored-applications`, {
    method: "POST",
    headers: authHeaders,
    body: JSON.stringify({
      applicantName: "Sally Ride",
      applicantEmail: "sally@example.test",
      notes: "Recommended by current member"
    })
  });

  assert.equal(prepaymentResponse.status, 201);
  assert.equal(donationResponse.status, 201);
  assert.equal(cancellationResponse.status, 200);
  assert.equal(applicationResponse.status, 201);
});
