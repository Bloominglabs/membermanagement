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

test("GET /healthz returns ok", async (t) => {
  const { server, baseUrl } = await startServer();
  t.after(() => server.close());

  const response = await fetch(`${baseUrl}/healthz`);

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: "ok" });
});

test("GET / serves the static admin shell", async (t) => {
  const { server, baseUrl } = await startServer();
  t.after(() => server.close());

  const response = await fetch(`${baseUrl}/`);
  const body = await response.text();

  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type"), /text\/html/);
  assert.match(body, /Member Management Admin/);
  assert.match(body, /config\.js/);
  assert.match(body, /app\.js/);
});

test("members and reports require authentication", async (t) => {
  const { server, baseUrl } = await startServer();
  t.after(() => server.close());

  const membersResponse = await fetch(`${baseUrl}/api/v1/members`);
  const reportsResponse = await fetch(`${baseUrl}/api/v1/reports/financial-summary`);

  assert.equal(membersResponse.status, 401);
  assert.equal(reportsResponse.status, 401);
});

test("staff login yields a token that can read members and reports", async (t) => {
  const { server, baseUrl } = await startServer();
  t.after(() => server.close());

  const loginResponse = await fetch(`${baseUrl}/api/v1/session/login`, {
    method: "POST",
    headers: {
      "content-type": "application/json"
    },
    body: JSON.stringify({
      username: "admin",
      password: "change-me"
    })
  });

  assert.equal(loginResponse.status, 200);
  const loginPayload = await loginResponse.json();
  assert.equal(typeof loginPayload.token, "string");
  assert.equal(loginPayload.account.username, "admin");

  const authHeaders = {
    authorization: `Bearer ${loginPayload.token}`
  };

  const membersResponse = await fetch(`${baseUrl}/api/v1/members`, {
    headers: authHeaders
  });
  const membersPayload = await membersResponse.json();

  assert.equal(membersResponse.status, 200);
  assert.equal(membersPayload.items.length, 2);
  assert.deepEqual(membersPayload.items.map((member) => member.status), ["active", "applicant"]);

  const reportsResponse = await fetch(`${baseUrl}/api/v1/reports/financial-summary`, {
    headers: authHeaders
  });
  const reportsPayload = await reportsResponse.json();

  assert.equal(reportsResponse.status, 200);
  assert.deepEqual(reportsPayload, {
    currency: "USD",
    receivableCents: 12500,
    prepaidCents: 2400,
    donationsYtdCents: 8000
  });
});

test("allowed origins receive CORS headers for API requests", async (t) => {
  const { server, baseUrl } = await startServer({
    allowedOrigins: ["https://example.github.io"]
  });
  t.after(() => server.close());

  const response = await fetch(`${baseUrl}/api/v1/session/login`, {
    method: "OPTIONS",
    headers: {
      origin: "https://example.github.io",
      "access-control-request-method": "POST",
      "access-control-request-headers": "content-type,authorization"
    }
  });

  assert.equal(response.status, 204);
  assert.equal(response.headers.get("access-control-allow-origin"), "https://example.github.io");
  assert.match(response.headers.get("access-control-allow-headers"), /authorization/);
});
