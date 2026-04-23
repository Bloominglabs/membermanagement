import { randomUUID } from "node:crypto";
import pg from "pg";

import { createEngine } from "../../engine/create-engine.js";
import { verifyPassword } from "../../security/passwords.js";
import { computeFinancialSummary } from "../store/compute-financial-summary.js";
import { createDefaultDocument, normalizeDocument } from "../store/default-document.js";

const { Pool } = pg;

function clone(value) {
  return structuredClone(value);
}

function parseJson(value, fallback = null) {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }

  return JSON.parse(value);
}

function serializeJson(value) {
  return JSON.stringify(value);
}

function countFromRow(row) {
  return Number(row.count);
}

function normalizeLegacyDocumentValue(value) {
  if (!value) {
    return null;
  }

  if (typeof value === "string") {
    return normalizeDocument(JSON.parse(value));
  }

  return normalizeDocument(value);
}

async function tableExists(db, tableName) {
  const result = await db.query(
    `
      select count(*) as count
      from information_schema.tables
      where table_schema = 'public' and table_name = $1
    `,
    [tableName]
  );

  return countFromRow(result.rows[0]) > 0;
}

async function ensureSchema(db) {
  await db.query(`
    create table if not exists accounts (
      id text,
      username text,
      password_hash text,
      roles_json text,
      member_id text
    )
  `);
  await db.query(`
    create table if not exists sessions (
      token text,
      account_id text,
      issued_at text,
      expires_at text,
      revoked_at text
    )
  `);
  await db.query(`
    create table if not exists members (
      id text,
      full_name text,
      email text,
      status text,
      dues_class text,
      sponsor_member_id text,
      created_at text,
      left_at text,
      cancellation_reason text
    )
  `);
  await db.query(`
    create table if not exists applications (
      id text,
      applicant_name text,
      applicant_email text,
      notes text,
      sponsor_member_id text,
      status text,
      created_at text,
      reviewed_at text,
      reviewed_by_account_id text,
      member_id text
    )
  `);
  await db.query(`
    create table if not exists invoices (
      id text,
      member_id text,
      description text,
      amount_cents integer,
      due_date text,
      status text,
      created_at text,
      created_by_account_id text,
      issued_at text,
      issued_by_account_id text,
      paid_at text
    )
  `);
  await db.query(`
    create table if not exists payments (
      id text,
      member_id text,
      amount_cents integer,
      method text,
      source text,
      recorded_by_account_id text,
      received_at text
    )
  `);
  await db.query(`
    create table if not exists payment_allocations (
      payment_id text,
      invoice_id text,
      amount_cents integer
    )
  `);
  await db.query(`
    create table if not exists donations (
      id text,
      donor_name text,
      amount_cents integer,
      source text,
      received_at text,
      member_id text,
      recorded_by_account_id text
    )
  `);
  await db.query(`
    create table if not exists id_counters (
      kind text,
      next_value integer
    )
  `);
}

async function countRows(db, tableName) {
  const result = await db.query(`select count(*) as count from ${tableName}`);
  return countFromRow(result.rows[0]);
}

async function clearNormalizedTables(db) {
  await db.query("delete from payment_allocations");
  await db.query("delete from payments");
  await db.query("delete from donations");
  await db.query("delete from invoices");
  await db.query("delete from applications");
  await db.query("delete from sessions");
  await db.query("delete from accounts");
  await db.query("delete from members");
  await db.query("delete from id_counters");
}

async function seedFromDocument(db, document) {
  const normalizedDocument = normalizeDocument(clone(document));

  await clearNormalizedTables(db);

  for (const [kind, nextValue] of Object.entries(normalizedDocument.nextIds)) {
    await db.query(
      "insert into id_counters (kind, next_value) values ($1, $2)",
      [kind, nextValue]
    );
  }

  for (const account of normalizedDocument.accounts) {
    await db.query(
      `
        insert into accounts (id, username, password_hash, roles_json, member_id)
        values ($1, $2, $3, $4, $5)
      `,
      [
        account.id,
        account.username,
        account.passwordHash,
        serializeJson(account.roles),
        account.memberId ?? null
      ]
    );
  }

  for (const member of normalizedDocument.members) {
    await db.query(
      `
        insert into members (
          id, full_name, email, status, dues_class,
          sponsor_member_id, created_at, left_at, cancellation_reason
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9)
      `,
      [
        member.id,
        member.fullName,
        member.email,
        member.status,
        member.duesClass,
        member.sponsorMemberId ?? null,
        member.createdAt ?? null,
        member.leftAt ?? null,
        member.cancellationReason ?? null
      ]
    );
  }

  for (const application of normalizedDocument.applications) {
    await db.query(
      `
        insert into applications (
          id, applicant_name, applicant_email, notes, sponsor_member_id,
          status, created_at, reviewed_at, reviewed_by_account_id, member_id
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
      `,
      [
        application.id,
        application.applicantName,
        application.applicantEmail,
        application.notes,
        application.sponsorMemberId ?? null,
        application.status,
        application.createdAt,
        application.reviewedAt ?? null,
        application.reviewedByAccountId ?? null,
        application.memberId ?? null
      ]
    );
  }

  for (const invoice of normalizedDocument.invoices) {
    await db.query(
      `
        insert into invoices (
          id, member_id, description, amount_cents, due_date, status,
          created_at, created_by_account_id, issued_at, issued_by_account_id, paid_at
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
      `,
      [
        invoice.id,
        invoice.memberId,
        invoice.description,
        invoice.amountCents,
        invoice.dueDate,
        invoice.status,
        invoice.createdAt,
        invoice.createdByAccountId ?? null,
        invoice.issuedAt ?? null,
        invoice.issuedByAccountId ?? null,
        invoice.paidAt ?? null
      ]
    );
  }

  for (const payment of normalizedDocument.payments) {
    await db.query(
      `
        insert into payments (
          id, member_id, amount_cents, method, source, recorded_by_account_id, received_at
        )
        values ($1, $2, $3, $4, $5, $6, $7)
      `,
      [
        payment.id,
        payment.memberId,
        payment.amountCents,
        payment.method,
        payment.source,
        payment.recordedByAccountId ?? null,
        payment.receivedAt
      ]
    );

    for (const allocation of payment.allocations) {
      await db.query(
        `
          insert into payment_allocations (payment_id, invoice_id, amount_cents)
          values ($1, $2, $3)
        `,
        [
          payment.id,
          allocation.invoiceId,
          allocation.amountCents
        ]
      );
    }
  }

  for (const donation of normalizedDocument.donations) {
    await db.query(
      `
        insert into donations (
          id, donor_name, amount_cents, source, received_at, member_id, recorded_by_account_id
        )
        values ($1, $2, $3, $4, $5, $6, $7)
      `,
      [
        donation.id,
        donation.donorName,
        donation.amountCents,
        donation.source,
        donation.receivedAt,
        donation.memberId ?? null,
        donation.recordedByAccountId ?? null
      ]
    );
  }

  for (const session of normalizedDocument.sessions) {
    await db.query(
      `
        insert into sessions (token, account_id, issued_at, expires_at, revoked_at)
        values ($1, $2, $3, $4, $5)
      `,
      [
        session.token,
        session.accountId,
        session.issuedAt ?? null,
        session.expiresAt ?? null,
        session.revokedAt ?? null
      ]
    );
  }
}

async function loadLegacyDocument(db) {
  if (!await tableExists(db, "app_state")) {
    return null;
  }

  const result = await db.query("select document from app_state limit 1");

  if (result.rowCount === 0) {
    return null;
  }

  return normalizeLegacyDocumentValue(result.rows[0].document);
}

async function ensureSeeded(db, seedDocument) {
  await ensureSchema(db);

  const existingAccounts = await countRows(db, "accounts");
  if (existingAccounts > 0) {
    return;
  }

  const legacyDocument = await loadLegacyDocument(db);
  const document = legacyDocument ?? seedDocument ?? createDefaultDocument();
  await seedFromDocument(db, document);
}

function mapAccountRow(row) {
  return {
    id: row.id,
    username: row.username,
    passwordHash: row.password_hash,
    roles: parseJson(row.roles_json, []),
    memberId: row.member_id ?? null
  };
}

function mapMemberRow(row) {
  return {
    id: row.id,
    fullName: row.full_name,
    email: row.email,
    status: row.status,
    duesClass: row.dues_class,
    sponsorMemberId: row.sponsor_member_id ?? null,
    createdAt: row.created_at ?? null,
    leftAt: row.left_at ?? null,
    cancellationReason: row.cancellation_reason ?? null
  };
}

function mapApplicationRow(row) {
  return {
    id: row.id,
    applicantName: row.applicant_name,
    applicantEmail: row.applicant_email,
    notes: row.notes ?? "",
    sponsorMemberId: row.sponsor_member_id ?? null,
    status: row.status,
    createdAt: row.created_at,
    reviewedAt: row.reviewed_at ?? null,
    reviewedByAccountId: row.reviewed_by_account_id ?? null,
    memberId: row.member_id ?? null
  };
}

function mapInvoiceRow(row) {
  return {
    id: row.id,
    memberId: row.member_id,
    description: row.description,
    amountCents: Number(row.amount_cents),
    dueDate: row.due_date,
    status: row.status,
    createdAt: row.created_at,
    createdByAccountId: row.created_by_account_id ?? null,
    issuedAt: row.issued_at ?? null,
    issuedByAccountId: row.issued_by_account_id ?? null,
    paidAt: row.paid_at ?? null
  };
}

function mapPaymentRow(row, allocations) {
  return {
    id: row.id,
    memberId: row.member_id,
    amountCents: Number(row.amount_cents),
    method: row.method,
    source: row.source,
    recordedByAccountId: row.recorded_by_account_id ?? null,
    receivedAt: row.received_at,
    allocations
  };
}

function mapDonationRow(row) {
  return {
    id: row.id,
    donorName: row.donor_name,
    amountCents: Number(row.amount_cents),
    source: row.source,
    receivedAt: row.received_at,
    memberId: row.member_id ?? null,
    recordedByAccountId: row.recorded_by_account_id ?? null
  };
}

function mapSessionRow(row) {
  return {
    token: row.token,
    accountId: row.account_id,
    issuedAt: row.issued_at ?? null,
    expiresAt: row.expires_at ?? null,
    revokedAt: row.revoked_at ?? null
  };
}

async function readCounter(db, kind) {
  const result = await db.query(
    "select next_value from id_counters where kind = $1 limit 1",
    [kind]
  );

  if (result.rowCount === 0) {
    throw new Error(`missing id counter for ${kind}`);
  }

  return Number(result.rows[0].next_value);
}

async function updateCounter(db, kind, nextValue) {
  await db.query(
    "update id_counters set next_value = $2 where kind = $1",
    [kind, nextValue]
  );
}

async function allocateId(db, kind, prefix) {
  const currentValue = await readCounter(db, kind);
  await updateCounter(db, kind, currentValue + 1);
  return `${prefix}-${currentValue}`;
}

async function updateRecord(db, {
  table,
  idValue,
  idColumn = "id",
  updates,
  columnMap,
  readById
}) {
  const entries = Object.entries(updates).filter(([key]) => key in columnMap);

  if (entries.length === 0) {
    return readById(idValue);
  }

  const setClauses = [];
  const values = [];

  for (const [index, [key, value]] of entries.entries()) {
    setClauses.push(`${columnMap[key]} = $${index + 1}`);
    values.push(value);
  }

  values.push(idValue);

  await db.query(
    `update ${table} set ${setClauses.join(", ")} where ${idColumn} = $${values.length}`,
    values
  );

  return readById(idValue);
}

function createAccountsRepository(db) {
  return {
    async findByUsername(username) {
      const result = await db.query(
        "select * from accounts where username = $1 limit 1",
        [username]
      );

      return result.rowCount === 0 ? null : mapAccountRow(result.rows[0]);
    },

    async findById(id) {
      const result = await db.query(
        "select * from accounts where id = $1 limit 1",
        [id]
      );

      return result.rowCount === 0 ? null : mapAccountRow(result.rows[0]);
    }
  };
}

function createMembersRepository(db) {
  async function findById(id) {
    const result = await db.query(
      "select * from members where id = $1 limit 1",
      [id]
    );

    return result.rowCount === 0 ? null : mapMemberRow(result.rows[0]);
  }

  return {
    async list() {
      const result = await db.query("select * from members order by id");
      return result.rows.map((row) => mapMemberRow(row));
    },

    findById,

    async create(input) {
      const id = await allocateId(db, "member", "mem");

      await db.query(
        `
          insert into members (
            id, full_name, email, status, dues_class,
            sponsor_member_id, created_at, left_at, cancellation_reason
          )
          values ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        `,
        [
          id,
          input.fullName,
          input.email,
          input.status,
          input.duesClass,
          input.sponsorMemberId ?? null,
          input.createdAt ?? null,
          input.leftAt ?? null,
          input.cancellationReason ?? null
        ]
      );

      return findById(id);
    },

    async update(id, updates) {
      return updateRecord(db, {
        table: "members",
        idValue: id,
        updates,
        columnMap: {
          fullName: "full_name",
          email: "email",
          status: "status",
          duesClass: "dues_class",
          sponsorMemberId: "sponsor_member_id",
          createdAt: "created_at",
          leftAt: "left_at",
          cancellationReason: "cancellation_reason"
        },
        readById: findById
      });
    }
  };
}

function createApplicationsRepository(db) {
  async function findById(id) {
    const result = await db.query(
      "select * from applications where id = $1 limit 1",
      [id]
    );

    return result.rowCount === 0 ? null : mapApplicationRow(result.rows[0]);
  }

  return {
    async list() {
      const result = await db.query("select * from applications order by id");
      return result.rows.map((row) => mapApplicationRow(row));
    },

    findById,

    async create(input) {
      const id = await allocateId(db, "application", "app");

      await db.query(
        `
          insert into applications (
            id, applicant_name, applicant_email, notes, sponsor_member_id,
            status, created_at, reviewed_at, reviewed_by_account_id, member_id
          )
          values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        `,
        [
          id,
          input.applicantName,
          input.applicantEmail,
          input.notes ?? "",
          input.sponsorMemberId ?? null,
          input.status,
          input.createdAt,
          input.reviewedAt ?? null,
          input.reviewedByAccountId ?? null,
          input.memberId ?? null
        ]
      );

      return findById(id);
    },

    async update(id, updates) {
      return updateRecord(db, {
        table: "applications",
        idValue: id,
        updates,
        columnMap: {
          applicantName: "applicant_name",
          applicantEmail: "applicant_email",
          notes: "notes",
          sponsorMemberId: "sponsor_member_id",
          status: "status",
          createdAt: "created_at",
          reviewedAt: "reviewed_at",
          reviewedByAccountId: "reviewed_by_account_id",
          memberId: "member_id"
        },
        readById: findById
      });
    }
  };
}

function createInvoicesRepository(db) {
  async function findById(id) {
    const result = await db.query(
      "select * from invoices where id = $1 limit 1",
      [id]
    );

    return result.rowCount === 0 ? null : mapInvoiceRow(result.rows[0]);
  }

  return {
    async list() {
      const result = await db.query("select * from invoices order by id");
      return result.rows.map((row) => mapInvoiceRow(row));
    },

    async listByMember(memberId) {
      const result = await db.query(
        "select * from invoices where member_id = $1 order by due_date, created_at, id",
        [memberId]
      );

      return result.rows.map((row) => mapInvoiceRow(row));
    },

    findById,

    async create(input) {
      const id = await allocateId(db, "invoice", "inv");

      await db.query(
        `
          insert into invoices (
            id, member_id, description, amount_cents, due_date, status,
            created_at, created_by_account_id, issued_at, issued_by_account_id, paid_at
          )
          values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        `,
        [
          id,
          input.memberId,
          input.description,
          input.amountCents,
          input.dueDate,
          input.status,
          input.createdAt,
          input.createdByAccountId ?? null,
          input.issuedAt ?? null,
          input.issuedByAccountId ?? null,
          input.paidAt ?? null
        ]
      );

      return findById(id);
    },

    async update(id, updates) {
      return updateRecord(db, {
        table: "invoices",
        idValue: id,
        updates,
        columnMap: {
          memberId: "member_id",
          description: "description",
          amountCents: "amount_cents",
          dueDate: "due_date",
          status: "status",
          createdAt: "created_at",
          createdByAccountId: "created_by_account_id",
          issuedAt: "issued_at",
          issuedByAccountId: "issued_by_account_id",
          paidAt: "paid_at"
        },
        readById: findById
      });
    }
  };
}

async function loadAllocationsByPaymentId(db) {
  const result = await db.query("select * from payment_allocations");
  const allocationsByPaymentId = new Map();

  for (const row of result.rows) {
    const paymentId = row.payment_id;
    const allocations = allocationsByPaymentId.get(paymentId) ?? [];
    allocations.push({
      invoiceId: row.invoice_id,
      amountCents: Number(row.amount_cents)
    });
    allocationsByPaymentId.set(paymentId, allocations);
  }

  return allocationsByPaymentId;
}

function createPaymentsRepository(db) {
  async function hydratePaymentRows(paymentRows) {
    const allocationsByPaymentId = await loadAllocationsByPaymentId(db);

    return paymentRows.map((row) => mapPaymentRow(
      row,
      allocationsByPaymentId.get(row.id) ?? []
    ));
  }

  return {
    async list() {
      const result = await db.query("select * from payments order by received_at, id");
      return hydratePaymentRows(result.rows);
    },

    async listByMember(memberId) {
      const result = await db.query(
        "select * from payments where member_id = $1 order by received_at, id",
        [memberId]
      );

      return hydratePaymentRows(result.rows);
    },

    async create(input) {
      const id = await allocateId(db, "payment", "pay");

      await db.query(
        `
          insert into payments (
            id, member_id, amount_cents, method, source, recorded_by_account_id, received_at
          )
          values ($1, $2, $3, $4, $5, $6, $7)
        `,
        [
          id,
          input.memberId,
          input.amountCents,
          input.method,
          input.source,
          input.recordedByAccountId ?? null,
          input.receivedAt
        ]
      );

      for (const allocation of input.allocations) {
        await db.query(
          `
            insert into payment_allocations (payment_id, invoice_id, amount_cents)
            values ($1, $2, $3)
          `,
          [id, allocation.invoiceId, allocation.amountCents]
        );
      }

      const result = await db.query(
        "select * from payments where id = $1 limit 1",
        [id]
      );

      const hydrated = await hydratePaymentRows(result.rows);
      return hydrated[0];
    }
  };
}

function createDonationsRepository(db) {
  return {
    async list() {
      const result = await db.query("select * from donations order by received_at, id");
      return result.rows.map((row) => mapDonationRow(row));
    },

    async create(input) {
      const id = await allocateId(db, "donation", "don");

      await db.query(
        `
          insert into donations (
            id, donor_name, amount_cents, source, received_at, member_id, recorded_by_account_id
          )
          values ($1, $2, $3, $4, $5, $6, $7)
        `,
        [
          id,
          input.donorName,
          input.amountCents,
          input.source,
          input.receivedAt,
          input.memberId ?? null,
          input.recordedByAccountId ?? null
        ]
      );

      const result = await db.query(
        "select * from donations where id = $1 limit 1",
        [id]
      );

      return mapDonationRow(result.rows[0]);
    }
  };
}

function createSessionsRepository(db) {
  return {
    async issue(session) {
      const token = session.token ?? randomUUID();

      await db.query(
        `
          insert into sessions (token, account_id, issued_at, expires_at, revoked_at)
          values ($1, $2, $3, $4, $5)
        `,
        [
          token,
          session.accountId,
          session.issuedAt ?? null,
          session.expiresAt ?? null,
          session.revokedAt ?? null
        ]
      );

      return token;
    },

    async read(token) {
      const result = await db.query(
        "select * from sessions where token = $1 limit 1",
        [token]
      );

      return result.rowCount === 0 ? null : mapSessionRow(result.rows[0]);
    },

    async revoke(token, revokedAt) {
      await db.query(
        "update sessions set revoked_at = $2 where token = $1",
        [token, revokedAt]
      );

      const result = await db.query(
        "select * from sessions where token = $1 limit 1",
        [token]
      );

      return result.rowCount === 0 ? null : mapSessionRow(result.rows[0]);
    }
  };
}

function createReportsRepository(db, clock) {
  return {
    async getFinancialSummary() {
      const [invoiceResult, paymentResult, allocationResult, donationResult] = await Promise.all([
        db.query("select * from invoices"),
        db.query("select * from payments"),
        db.query("select * from payment_allocations"),
        db.query("select * from donations")
      ]);

      const allocationsByPaymentId = new Map();
      for (const row of allocationResult.rows) {
        const allocations = allocationsByPaymentId.get(row.payment_id) ?? [];
        allocations.push({
          invoiceId: row.invoice_id,
          amountCents: Number(row.amount_cents)
        });
        allocationsByPaymentId.set(row.payment_id, allocations);
      }

      return computeFinancialSummary({
        invoices: invoiceResult.rows.map((row) => mapInvoiceRow(row)),
        payments: paymentResult.rows.map((row) => mapPaymentRow(
          row,
          allocationsByPaymentId.get(row.id) ?? []
        )),
        donations: donationResult.rows.map((row) => mapDonationRow(row)),
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

function createScopedDependencies(db, shared, includeTransactions) {
  const dependencies = {
    accounts: createAccountsRepository(db),
    applications: createApplicationsRepository(db),
    members: createMembersRepository(db),
    invoices: createInvoicesRepository(db),
    payments: createPaymentsRepository(db),
    donations: createDonationsRepository(db),
    reports: createReportsRepository(db, shared.clock),
    sessions: createSessionsRepository(db),
    passwords: createPasswordService(),
    clock: shared.clock,
    sessionLifetimeMinutes: shared.sessionLifetimeMinutes
  };

  if (includeTransactions && typeof db.connect === "function") {
    dependencies.transactions = {
      run: async (work) => {
        const client = await db.connect();

        try {
          await client.query("begin");
          const scopedDependencies = createScopedDependencies(
            client,
            shared,
            false
          );
          const result = await work(scopedDependencies);
          await client.query("commit");
          return result;
        } catch (error) {
          await client.query("rollback");
          throw error;
        } finally {
          client.release();
        }
      }
    };
  }

  return dependencies;
}

function createPoolFromOptions({ connectionString, ssl } = {}) {
  return new Pool({
    connectionString,
    ...(ssl ? { ssl } : {})
  });
}

export async function createPostgresRuntime({
  pool = null,
  connectionString,
  ssl,
  allowedOrigins = [],
  clock = () => new Date(),
  seedDocument,
  sessionLifetimeMinutes
} = {}) {
  const runtimePool = pool ?? createPoolFromOptions({ connectionString, ssl });
  const ownsPool = !pool;

  await ensureSeeded(runtimePool, seedDocument);

  const shared = {
    clock,
    sessionLifetimeMinutes
  };

  const runtime = {
    config: {
      allowedOrigins: [...allowedOrigins]
    },
    pool: runtimePool
  };

  runtime.engine = createEngine(
    createScopedDependencies(runtimePool, shared, true)
  );

  runtime.close = async () => {
    if (ownsPool) {
      await runtimePool.end();
    }
  };

  return runtime;
}
