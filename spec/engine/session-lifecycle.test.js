import test from "node:test";
import assert from "node:assert/strict";

import { createInMemoryRuntime } from "../../src/adapters/inmemory/create-in-memory-runtime.js";

function createMutableClock(startIso) {
  const state = { now: new Date(startIso) };

  return {
    clock: () => new Date(state.now),
    advanceMinutes(minutes) {
      state.now = new Date(state.now.getTime() + (minutes * 60 * 1000));
    }
  };
}

test("expired sessions can no longer access protected routes", async () => {
  const time = createMutableClock("2026-04-23T12:00:00.000Z");
  const runtime = createInMemoryRuntime({
    clock: time.clock,
    sessionLifetimeMinutes: 10
  });

  const session = await runtime.engine.login({
    username: "admin",
    password: "change-me"
  });

  time.advanceMinutes(11);

  await assert.rejects(
    () => runtime.engine.listMembers({ token: session.token }),
    /authentication required/
  );
});

test("logout revokes the current session token", async () => {
  const runtime = createInMemoryRuntime();

  const session = await runtime.engine.login({
    username: "admin",
    password: "change-me"
  });

  await runtime.engine.logout({
    token: session.token
  });

  await assert.rejects(
    () => runtime.engine.getFinancialSummary({ token: session.token }),
    /authentication required/
  );
});

