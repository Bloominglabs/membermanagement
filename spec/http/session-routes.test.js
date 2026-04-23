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
  return {
    server,
    baseUrl: `http://127.0.0.1:${address.port}`
  };
}

test("logout endpoint revokes a bearer token", async (t) => {
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
  const loginPayload = await loginResponse.json();
  const authHeaders = {
    authorization: `Bearer ${loginPayload.token}`
  };

  const logoutResponse = await fetch(`${baseUrl}/api/v1/session/logout`, {
    method: "POST",
    headers: authHeaders
  });

  assert.equal(logoutResponse.status, 204);

  const postLogoutResponse = await fetch(`${baseUrl}/api/v1/members`, {
    headers: authHeaders
  });

  assert.equal(postLogoutResponse.status, 401);
});

