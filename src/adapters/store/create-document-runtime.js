import { randomUUID } from "node:crypto";

import { createEngine } from "../../engine/create-engine.js";
import { verifyPassword } from "../../security/passwords.js";
import { computeFinancialSummary } from "./compute-financial-summary.js";
import { createDefaultDocument, normalizeDocument } from "./default-document.js";

function clone(value) {
  return structuredClone(value);
}

function createStateAccess(state, loadDocument, persistDocument) {
  const refresh = async () => {
    if (!loadDocument) {
      return state.document;
    }

    state.document = normalizeDocument(await loadDocument());
    return state.document;
  };

  const persist = async () => {
    state.document = normalizeDocument(state.document);
    await persistDocument(clone(state.document));
  };

  return { refresh, persist };
}

function createIdAllocator(state, access) {
  return async function allocateId(kind, prefix) {
    await access.refresh();

    const idNumber = state.document.nextIds[kind];
    state.document.nextIds[kind] += 1;
    await access.persist();
    return `${prefix}-${idNumber}`;
  };
}

function createAccountsRepository(state, access) {
  return {
    async findByUsername(username) {
      await access.refresh();
      const account = state.document.accounts.find((record) => record.username === username);
      return account ? clone(account) : null;
    },

    async findById(id) {
      await access.refresh();
      const account = state.document.accounts.find((record) => record.id === id);
      return account ? clone(account) : null;
    }
  };
}

function createMembersRepository(state, access, allocateId) {
  return {
    async list() {
      await access.refresh();
      return state.document.members.map((record) => clone(record));
    },

    async findById(id) {
      await access.refresh();
      const member = state.document.members.find((record) => record.id === id);
      return member ? clone(member) : null;
    },

    async create(input) {
      await access.refresh();

      const member = {
        id: await allocateId("member", "mem"),
        ...clone(input)
      };

      state.document.members.push(member);
      await access.persist();
      return clone(member);
    },

    async update(id, updates) {
      await access.refresh();

      const index = state.document.members.findIndex((record) => record.id === id);
      if (index === -1) {
        return null;
      }

      state.document.members[index] = {
        ...state.document.members[index],
        ...clone(updates)
      };

      await access.persist();
      return clone(state.document.members[index]);
    }
  };
}

function createApplicationsRepository(state, access, allocateId) {
  return {
    async list() {
      await access.refresh();
      return state.document.applications.map((record) => clone(record));
    },

    async findById(id) {
      await access.refresh();
      const application = state.document.applications.find((record) => record.id === id);
      return application ? clone(application) : null;
    },

    async create(input) {
      await access.refresh();

      const application = {
        id: await allocateId("application", "app"),
        ...clone(input)
      };

      state.document.applications.push(application);
      await access.persist();
      return clone(application);
    },

    async update(id, updates) {
      await access.refresh();

      const index = state.document.applications.findIndex((record) => record.id === id);
      if (index === -1) {
        return null;
      }

      state.document.applications[index] = {
        ...state.document.applications[index],
        ...clone(updates)
      };

      await access.persist();
      return clone(state.document.applications[index]);
    }
  };
}

function createInvoicesRepository(state, access, allocateId) {
  return {
    async list() {
      await access.refresh();
      return state.document.invoices.map((record) => clone(record));
    },

    async listByMember(memberId) {
      await access.refresh();
      return state.document.invoices
        .filter((record) => record.memberId === memberId)
        .map((record) => clone(record));
    },

    async findById(id) {
      await access.refresh();
      const invoice = state.document.invoices.find((record) => record.id === id);
      return invoice ? clone(invoice) : null;
    },

    async create(input) {
      await access.refresh();

      const invoice = {
        id: await allocateId("invoice", "inv"),
        ...clone(input)
      };

      state.document.invoices.push(invoice);
      await access.persist();
      return clone(invoice);
    },

    async update(id, updates) {
      await access.refresh();

      const index = state.document.invoices.findIndex((record) => record.id === id);
      if (index === -1) {
        return null;
      }

      state.document.invoices[index] = {
        ...state.document.invoices[index],
        ...clone(updates)
      };

      await access.persist();
      return clone(state.document.invoices[index]);
    }
  };
}

function createPaymentsRepository(state, access, allocateId) {
  return {
    async list() {
      await access.refresh();
      return state.document.payments.map((record) => clone(record));
    },

    async listByMember(memberId) {
      await access.refresh();
      return state.document.payments
        .filter((record) => record.memberId === memberId)
        .map((record) => clone(record));
    },

    async create(input) {
      await access.refresh();

      const payment = {
        id: await allocateId("payment", "pay"),
        ...clone(input)
      };

      state.document.payments.push(payment);
      await access.persist();
      return clone(payment);
    }
  };
}

function createDonationsRepository(state, access, allocateId) {
  return {
    async list() {
      await access.refresh();
      return state.document.donations.map((record) => clone(record));
    },

    async create(input) {
      await access.refresh();

      const donation = {
        id: await allocateId("donation", "don"),
        ...clone(input)
      };

      state.document.donations.push(donation);
      await access.persist();
      return clone(donation);
    }
  };
}

function createSessionsRepository(state, access) {
  return {
    async issue(session) {
      await access.refresh();

      const persistedSession = {
        token: randomUUID(),
        ...clone(session)
      };

      state.document.sessions.push(persistedSession);
      await access.persist();
      return persistedSession.token;
    },

    async read(token) {
      await access.refresh();
      const session = state.document.sessions.find((record) => record.token === token);
      return session ? clone(session) : null;
    },

    async revoke(token, revokedAt) {
      await access.refresh();

      const index = state.document.sessions.findIndex((record) => record.token === token);
      if (index === -1) {
        return null;
      }

      state.document.sessions[index] = {
        ...state.document.sessions[index],
        revokedAt
      };

      await access.persist();
      return clone(state.document.sessions[index]);
    }
  };
}

function createReportsRepository(state, access, clock) {
  return {
    async getFinancialSummary() {
      await access.refresh();

      return computeFinancialSummary({
        invoices: state.document.invoices,
        payments: state.document.payments,
        donations: state.document.donations,
        year: clock().getUTCFullYear()
      });
    }
  };
}

function createPasswordService() {
  return {
    async verify({ account, password }) {
      return verifyPassword({
        password,
        passwordHash: account.passwordHash
      });
    }
  };
}

export function createDocumentRuntime({
  document: initialDocument,
  loadDocument = null,
  persistDocument = async () => {},
  allowedOrigins = [],
  clock = () => new Date(),
  sessionLifetimeMinutes
} = {}) {
  const state = {
    document: normalizeDocument(clone(initialDocument ?? createDefaultDocument()))
  };
  const access = createStateAccess(state, loadDocument, persistDocument);
  const allocateId = createIdAllocator(state, access);

  const runtime = {
    config: {
      allowedOrigins: [...allowedOrigins]
    },
    state
  };

  runtime.engine = createEngine({
    accounts: createAccountsRepository(state, access),
    applications: createApplicationsRepository(state, access, allocateId),
    members: createMembersRepository(state, access, allocateId),
    invoices: createInvoicesRepository(state, access, allocateId),
    payments: createPaymentsRepository(state, access, allocateId),
    donations: createDonationsRepository(state, access, allocateId),
    reports: createReportsRepository(state, access, clock),
    sessions: createSessionsRepository(state, access),
    passwords: createPasswordService(),
    clock,
    sessionLifetimeMinutes
  });

  return runtime;
}
