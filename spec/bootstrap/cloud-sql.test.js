import test from "node:test";
import assert from "node:assert/strict";

import { createCloudSqlPoolFromEnv, createRuntimeFromEnv } from "../../src/bootstrap/create-runtime-from-env.js";

test("cloud sql pool builder uses connector options and database settings", async () => {
  const connectorCalls = [];
  const poolCalls = [];

  const pool = await createCloudSqlPoolFromEnv({
    env: {
      INSTANCE_CONNECTION_NAME: "project:region:instance",
      DB_USER: "appuser",
      DB_PASS: "dbpass",
      DB_NAME: "membermanagement",
      DB_POOL_MAX: "7",
      CLOUDSQL_IP_TYPE: "PRIVATE"
    },
    ConnectorClass: class FakeConnector {
      async getOptions(options) {
        connectorCalls.push(options);
        return {
          host: "127.0.0.1",
          port: 5432,
          ssl: "from-connector"
        };
      }
    },
    PoolClass: class FakePool {
      constructor(options) {
        poolCalls.push(options);
        this.options = options;
      }
    }
  });

  assert.equal(pool.options.user, "appuser");
  assert.equal(pool.options.password, "dbpass");
  assert.equal(pool.options.database, "membermanagement");
  assert.equal(pool.options.max, 7);
  assert.equal(pool.options.ssl, "from-connector");
  assert.deepEqual(connectorCalls, [{
    instanceConnectionName: "project:region:instance",
    ipType: "PRIVATE"
  }]);
  assert.equal(poolCalls.length, 1);
});

test("runtime selection uses Cloud SQL connector when instance env is present", async () => {
  const calls = [];

  const runtime = await createRuntimeFromEnv({
    env: {
      INSTANCE_CONNECTION_NAME: "project:region:instance",
      DB_USER: "appuser",
      DB_PASS: "dbpass",
      DB_NAME: "membermanagement"
    },
    factories: {
      createCloudSqlPostgresRuntime: async (options) => {
        calls.push(options);
        return { kind: "cloudsql" };
      },
      createPostgresRuntime: async () => ({ kind: "postgres" }),
      createFileRuntime: async () => ({ kind: "file" }),
      createInMemoryRuntime: () => ({ kind: "memory" })
    }
  });

  assert.equal(runtime.kind, "cloudsql");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].instanceConnectionName, "project:region:instance");
});

