import { randomUUID } from "node:crypto";

import { createEngine } from "../../engine/create-engine.js";

function clone(value) {
  return structuredClone(value);
}

function createAccountsRepository(records) {
  return {
    async findByUsername(username) {
      const account = records.find((record) => record.username === username);
      return account ? clone(account) : null;
    },

    async findById(id) {
      const account = records.find((record) => record.id === id);
      return account ? clone(account) : null;
    }
  };
}

function createMembersRepository(records) {
  return {
    async list() {
      return records.map((record) => clone(record));
    }
  };
}

function createReportsRepository(summary) {
  return {
    async getFinancialSummary() {
      return clone(summary);
    }
  };
}

function createSessionsRepository() {
  const sessions = new Map();

  return {
    async issue(session) {
      const token = randomUUID();
      sessions.set(token, clone(session));
      return token;
    },

    async read(token) {
      const session = sessions.get(token);
      return session ? clone(session) : null;
    }
  };
}

function createPasswordService() {
  return {
    // The in-memory adapter deliberately keeps credentials simple so the engine
    // contract stays visible. A production adapter will replace this with real
    // password hashing and durable account storage.
    async verify({ account, password }) {
      return account.password === password;
    }
  };
}

export function createInMemoryRuntime(options = {}) {
  const accounts = clone(options.accounts ?? [
    {
      id: "acct-admin",
      username: "admin",
      password: "change-me",
      roles: ["staff-admin"]
    }
  ]);
  const members = clone(options.members ?? [
    {
      id: "mem-1000",
      fullName: "Ada Lovelace",
      status: "active",
      duesClass: "standard"
    },
    {
      id: "mem-1001",
      fullName: "Grace Hopper",
      status: "applicant",
      duesClass: "sponsored"
    }
  ]);
  const reportSummary = clone(options.reportSummary ?? {
    currency: "USD",
    receivableCents: 12500,
    prepaidCents: 2400,
    donationsYtdCents: 8000
  });

  const runtime = {
    config: {
      allowedOrigins: [...(options.allowedOrigins ?? [])]
    }
  };

  runtime.engine = createEngine({
    accounts: createAccountsRepository(accounts),
    members: createMembersRepository(members),
    reports: createReportsRepository(reportSummary),
    sessions: createSessionsRepository(),
    passwords: createPasswordService()
  });

  return runtime;
}

