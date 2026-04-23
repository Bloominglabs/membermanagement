import test from "node:test";
import assert from "node:assert/strict";

import { createEngine } from "../../src/engine/create-engine.js";
import { createInMemoryRuntime } from "../../src/adapters/inmemory/create-in-memory-runtime.js";

test("engine rejects missing repository and service ports", () => {
  assert.throws(
    () => createEngine({}),
    /accounts repository is required/
  );
});

test("engine enforces permissions for member listing", async () => {
  const runtime = createInMemoryRuntime({
    accounts: [
      {
        id: "acct-member",
        username: "member-view",
        password: "member-secret",
        roles: ["member-self"]
      }
    ]
  });

  const loginResult = await runtime.engine.login({
    username: "member-view",
    password: "member-secret"
  });

  await assert.rejects(
    () => runtime.engine.listMembers({ token: loginResult.token }),
    /forbidden/
  );
});

