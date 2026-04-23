function clone(value) {
  return structuredClone(value);
}

// The default seed keeps the rewrite runnable out of the box while also
// producing the financial numbers asserted by the initial test suite.
const DEFAULT_DOCUMENT = Object.freeze({
  version: 1,
  nextIds: {
    member: 1002,
    application: 1000,
    invoice: 1001,
    payment: 1001,
    donation: 1001
  },
  accounts: [
    {
      id: "acct-admin",
      username: "admin",
      password: "change-me",
      roles: ["staff-admin"]
    }
  ],
  members: [
    {
      id: "mem-1000",
      fullName: "Ada Lovelace",
      email: "ada@example.test",
      status: "active",
      duesClass: "standard"
    },
    {
      id: "mem-1001",
      fullName: "Grace Hopper",
      email: "grace@example.test",
      status: "applicant",
      duesClass: "sponsored"
    }
  ],
  applications: [],
  invoices: [
    {
      id: "inv-1000",
      memberId: "mem-1000",
      description: "Current dues",
      amountCents: 12500,
      dueDate: "2026-04-01",
      status: "issued",
      createdAt: "2026-04-01T00:00:00.000Z",
      issuedAt: "2026-04-01T00:00:00.000Z"
    }
  ],
  payments: [
    {
      id: "pay-1000",
      memberId: "mem-1001",
      amountCents: 2400,
      method: "card",
      source: "self-prepay",
      recordedByAccountId: null,
      receivedAt: "2026-04-02T00:00:00.000Z",
      allocations: []
    }
  ],
  donations: [
    {
      id: "don-1000",
      donorName: "Community Donor",
      amountCents: 8000,
      source: "card",
      receivedAt: "2026-01-15T00:00:00.000Z"
    }
  ],
  sessions: []
});

export function createDefaultDocument(overrides = {}) {
  const document = clone(DEFAULT_DOCUMENT);

  for (const [key, value] of Object.entries(overrides)) {
    if (value === undefined) {
      continue;
    }

    document[key] = clone(value);
  }

  return document;
}
