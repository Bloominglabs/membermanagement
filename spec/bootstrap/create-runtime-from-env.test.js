import test from "node:test";
import assert from "node:assert/strict";

import { createRuntimeFromEnv } from "../../src/bootstrap/create-runtime-from-env.js";

test("runtime selection prefers PostgreSQL when DATABASE_URL is present", async () => {
  const calls = [];

  const runtime = await createRuntimeFromEnv({
    env: {
      DATABASE_URL: "postgres://app:secret@db.example/membermanagement",
      ALLOWED_WEB_ORIGINS: "https://admin.example"
    },
    factories: {
      createPostgresRuntime: async (options) => {
        calls.push(["postgres", options]);
        return { kind: "postgres" };
      },
      createFileRuntime: async (options) => {
        calls.push(["file", options]);
        return { kind: "file" };
      },
      createInMemoryRuntime: (options) => {
        calls.push(["memory", options]);
        return { kind: "memory" };
      }
    }
  });

  assert.equal(runtime.kind, "postgres");
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "postgres");
  assert.deepEqual(calls[0][1].allowedOrigins, ["https://admin.example"]);
});

test("runtime selection passes bootstrap admin credentials into the initial seed", async () => {
  const calls = [];

  await createRuntimeFromEnv({
    env: {
      DATABASE_URL: "postgres://app:secret@db.example/membermanagement",
      BOOTSTRAP_ADMIN_USERNAME: "treasurer",
      BOOTSTRAP_ADMIN_PASSWORD: "set-a-real-password"
    },
    factories: {
      createPostgresRuntime: async (options) => {
        calls.push(options);
        return { kind: "postgres" };
      },
      createFileRuntime: async () => ({ kind: "file" }),
      createInMemoryRuntime: () => ({ kind: "memory" })
    }
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].seedDocument.accounts[0].username, "treasurer");
  assert.equal("password" in calls[0].seedDocument.accounts[0], false);
  assert.equal(typeof calls[0].seedDocument.accounts[0].passwordHash, "string");
});

test("runtime selection falls back to file storage before in-memory", async () => {
  const calls = [];

  const runtime = await createRuntimeFromEnv({
    env: {
      DATA_FILE_PATH: "var/data/store.json"
    },
    factories: {
      createPostgresRuntime: async () => {
        calls.push("postgres");
        return { kind: "postgres" };
      },
      createFileRuntime: async (options) => {
        calls.push(["file", options]);
        return { kind: "file" };
      },
      createInMemoryRuntime: () => {
        calls.push("memory");
        return { kind: "memory" };
      }
    }
  });

  assert.equal(runtime.kind, "file");
  assert.deepEqual(calls, [["file", {
    dataFilePath: "var/data/store.json",
    allowedOrigins: []
  }]]);
});
