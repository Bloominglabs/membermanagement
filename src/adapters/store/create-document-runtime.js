import { randomUUID } from "node:crypto";

import { createEngine } from "../../engine/create-engine.js";
import { computeFinancialSummary } from "./compute-financial-summary.js";
import { createDefaultDocument } from "./default-document.js";

function clone(value) {
  return structuredClone(value);
}

function createIdAllocator(state, persistDocument) {
  return async function allocateId(kind, prefix) {
    const idNumber = state.document.nextIds[kind];
    state.document.nextIds[kind] += 1;
    await persistDocument();
    return `${prefix}-${idNumber}`;
  };
}

function createAccountsRepository(state) {
  return {
    async findByUsername(username) {
      const account = state.document.accounts.find((record) => record.username === username);
      return account ? clone(account) : null;
    },

    async findById(id) {
      const account = state.document.accounts.find((record) => record.id === id);
      return account ? clone(account) : null;
    }
  };
}

function createMembersRepository(state, persistDocument, allocateId) {
  return {
    async list() {
      return state.document.members.map((record) => clone(record));
    },

    async findById(id) {
      const member = state.document.members.find((record) => record.id === id);
      return member ? clone(member) : null;
    },

    async create(input) {
      const member = {
        id: await allocateId("member", "mem"),
        ...clone(input)
      };

      state.document.members.push(member);
      await persistDocument();
      return clone(member);
    },

    async update(id, updates) {
      const index = state.document.members.findIndex((record) => record.id === id);
      if (index === -1) {
        return null;
      }

      state.document.members[index] = {
        ...state.document.members[index],
        ...clone(updates)
      };

      await persistDocument();
      return clone(state.document.members[index]);
    }
  };
}

function createApplicationsRepository(state, persistDocument, allocateId) {
  return {
    async list() {
      return state.document.applications.map((record) => clone(record));
    },

    async findById(id) {
      const application = state.document.applications.find((record) => record.id === id);
      return application ? clone(application) : null;
    },

    async create(input) {
      const application = {
        id: await allocateId("application", "app"),
        ...clone(input)
      };

      state.document.applications.push(application);
      await persistDocument();
      return clone(application);
    },

    async update(id, updates) {
      const index = state.document.applications.findIndex((record) => record.id === id);
      if (index === -1) {
        return null;
      }

      state.document.applications[index] = {
        ...state.document.applications[index],
        ...clone(updates)
      };

      await persistDocument();
      return clone(state.document.applications[index]);
    }
  };
}

function createInvoicesRepository(state, persistDocument, allocateId) {
  return {
    async list() {
      return state.document.invoices.map((record) => clone(record));
    },

    async listByMember(memberId) {
      return state.document.invoices
        .filter((record) => record.memberId === memberId)
        .map((record) => clone(record));
    },

    async findById(id) {
      const invoice = state.document.invoices.find((record) => record.id === id);
      return invoice ? clone(invoice) : null;
    },

    async create(input) {
      const invoice = {
        id: await allocateId("invoice", "inv"),
        ...clone(input)
      };

      state.document.invoices.push(invoice);
      await persistDocument();
      return clone(invoice);
    },

    async update(id, updates) {
      const index = state.document.invoices.findIndex((record) => record.id === id);
      if (index === -1) {
        return null;
      }

      state.document.invoices[index] = {
        ...state.document.invoices[index],
        ...clone(updates)
      };

      await persistDocument();
      return clone(state.document.invoices[index]);
    }
  };
}

function createPaymentsRepository(state, persistDocument, allocateId) {
  return {
    async list() {
      return state.document.payments.map((record) => clone(record));
    },

    async listByMember(memberId) {
      return state.document.payments
        .filter((record) => record.memberId === memberId)
        .map((record) => clone(record));
    },

    async create(input) {
      const payment = {
        id: await allocateId("payment", "pay"),
        ...clone(input)
      };

      state.document.payments.push(payment);
      await persistDocument();
      return clone(payment);
    }
  };
}

function createDonationsRepository(state, persistDocument, allocateId) {
  return {
    async list() {
      return state.document.donations.map((record) => clone(record));
    },

    async create(input) {
      const donation = {
        id: await allocateId("donation", "don"),
        ...clone(input)
      };

      state.document.donations.push(donation);
      await persistDocument();
      return clone(donation);
    }
  };
}

function createSessionsRepository(state, persistDocument) {
  return {
    async issue(session) {
      const persistedSession = {
        token: randomUUID(),
        ...clone(session)
      };

      state.document.sessions.push(persistedSession);
      await persistDocument();
      return persistedSession.token;
    },

    async read(token) {
      const session = state.document.sessions.find((record) => record.token === token);
      return session ? clone(session) : null;
    }
  };
}

function createReportsRepository(state, clock) {
  return {
    async getFinancialSummary() {
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
      return account.password === password;
    }
  };
}

export function createDocumentRuntime({
  document: initialDocument,
  persistDocument = async () => {},
  allowedOrigins = [],
  clock = () => new Date()
} = {}) {
  const state = {
    document: clone(initialDocument ?? createDefaultDocument())
  };
  const persist = async () => persistDocument(clone(state.document));
  const allocateId = createIdAllocator(state, persist);

  const runtime = {
    config: {
      allowedOrigins: [...allowedOrigins]
    },
    state
  };

  runtime.engine = createEngine({
    accounts: createAccountsRepository(state),
    applications: createApplicationsRepository(state, persist, allocateId),
    members: createMembersRepository(state, persist, allocateId),
    invoices: createInvoicesRepository(state, persist, allocateId),
    payments: createPaymentsRepository(state, persist, allocateId),
    donations: createDonationsRepository(state, persist, allocateId),
    reports: createReportsRepository(state, clock),
    sessions: createSessionsRepository(state, persist),
    passwords: createPasswordService(),
    clock
  });

  return runtime;
}

