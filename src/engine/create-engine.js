import {
  AuthenticationError,
  NotFoundError,
  ValidationError
} from "./errors.js";
import { requirePermission } from "./permissions.js";
import { assertPort } from "./ports.js";
import {
  requireDecision,
  requireNonEmptyString,
  requirePositiveInteger
} from "./validators.js";

function nowIso(clock) {
  return clock().toISOString();
}

function presentAccount(account) {
  return {
    id: account.id,
    username: account.username,
    roles: [...account.roles],
    memberId: account.memberId ?? null
  };
}

function presentMember(member) {
  return {
    id: member.id,
    fullName: member.fullName,
    email: member.email,
    status: member.status,
    duesClass: member.duesClass,
    sponsorMemberId: member.sponsorMemberId ?? null
  };
}

function presentApplication(application, member = null) {
  return {
    id: application.id,
    applicantName: application.applicantName,
    applicantEmail: application.applicantEmail,
    notes: application.notes,
    sponsorMemberId: application.sponsorMemberId ?? null,
    status: application.status,
    createdAt: application.createdAt,
    reviewedAt: application.reviewedAt ?? null,
    memberId: application.memberId ?? null,
    member: member ? presentMember(member) : null
  };
}

function presentInvoice(invoice) {
  return {
    id: invoice.id,
    memberId: invoice.memberId,
    description: invoice.description,
    amountCents: invoice.amountCents,
    dueDate: invoice.dueDate,
    status: invoice.status,
    createdAt: invoice.createdAt,
    issuedAt: invoice.issuedAt ?? null,
    paidAt: invoice.paidAt ?? null
  };
}

function presentPayment(payment) {
  return {
    id: payment.id,
    memberId: payment.memberId,
    amountCents: payment.amountCents,
    method: payment.method,
    source: payment.source,
    receivedAt: payment.receivedAt,
    allocations: payment.allocations.map((allocation) => ({
      invoiceId: allocation.invoiceId,
      amountCents: allocation.amountCents
    }))
  };
}

function presentDonation(donation) {
  return {
    id: donation.id,
    donorName: donation.donorName,
    amountCents: donation.amountCents,
    source: donation.source,
    receivedAt: donation.receivedAt
  };
}

function appliedAmountForInvoice(invoiceId, payments) {
  return payments
    .flatMap((payment) => payment.allocations)
    .filter((allocation) => allocation.invoiceId === invoiceId)
    .reduce((total, allocation) => total + allocation.amountCents, 0);
}

async function authenticateSession(dependencies, token) {
  if (!token) {
    throw new AuthenticationError();
  }

  const session = await dependencies.sessions.read(token);
  if (!session) {
    throw new AuthenticationError();
  }

  const account = await dependencies.accounts.findById(session.accountId);
  if (!account) {
    throw new AuthenticationError();
  }

  return { account, session };
}

async function requireExistingMember(dependencies, memberId) {
  const member = await dependencies.members.findById(memberId);
  if (!member) {
    throw new NotFoundError("member not found");
  }

  return member;
}

async function requireExistingApplication(dependencies, applicationId) {
  const application = await dependencies.applications.findById(applicationId);
  if (!application) {
    throw new NotFoundError("application not found");
  }

  return application;
}

async function requireExistingInvoice(dependencies, invoiceId) {
  const invoice = await dependencies.invoices.findById(invoiceId);
  if (!invoice) {
    throw new NotFoundError("invoice not found");
  }

  return invoice;
}

function requireMemberSelfAccount(account) {
  if (!account.memberId) {
    throw new ValidationError("member account is not linked to a member record");
  }

  return account.memberId;
}

async function recordPaymentForMember(dependencies, {
  memberId,
  amountCents,
  method,
  source,
  recordedByAccountId
}) {
  await requireExistingMember(dependencies, memberId);
  requirePositiveInteger("amountCents", amountCents);
  const normalizedMethod = requireNonEmptyString("method", method);
  const receivedAt = nowIso(dependencies.clock);

  const [memberInvoices, memberPayments] = await Promise.all([
    dependencies.invoices.listByMember(memberId),
    dependencies.payments.listByMember(memberId)
  ]);

  const openInvoices = memberInvoices
    .filter((invoice) => invoice.status === "issued")
    .sort((left, right) => {
      return left.dueDate.localeCompare(right.dueDate) || left.createdAt.localeCompare(right.createdAt);
    });

  let remainingPayment = amountCents;
  const allocations = [];

  for (const invoice of openInvoices) {
    const appliedCents = appliedAmountForInvoice(invoice.id, memberPayments);
    const remainingInvoiceCents = Math.max(invoice.amountCents - appliedCents, 0);

    if (remainingInvoiceCents === 0 || remainingPayment === 0) {
      continue;
    }

    const allocatedAmount = Math.min(remainingInvoiceCents, remainingPayment);
    allocations.push({
      invoiceId: invoice.id,
      amountCents: allocatedAmount
    });
    remainingPayment -= allocatedAmount;
  }

  const payment = await dependencies.payments.create({
    memberId,
    amountCents,
    method: normalizedMethod,
    source,
    recordedByAccountId,
    receivedAt,
    allocations
  });

  for (const allocation of allocations) {
    const invoice = await dependencies.invoices.findById(allocation.invoiceId);
    const refreshedPayments = await dependencies.payments.listByMember(memberId);
    const totalApplied = appliedAmountForInvoice(invoice.id, refreshedPayments);

    if (totalApplied >= invoice.amountCents) {
      await dependencies.invoices.update(invoice.id, {
        status: "paid",
        paidAt: receivedAt
      });
    }
  }

  return presentPayment(payment);
}

export function createEngine(dependencies) {
  const {
    accounts,
    applications,
    members,
    invoices,
    payments,
    donations,
    reports,
    sessions,
    passwords,
    clock = () => new Date()
  } = dependencies;

  assertPort("accounts repository", accounts, ["findByUsername", "findById"]);
  assertPort("applications repository", applications, ["list", "findById", "create", "update"]);
  assertPort("members repository", members, ["list", "findById", "create", "update"]);
  assertPort("invoices repository", invoices, ["list", "listByMember", "findById", "create", "update"]);
  assertPort("payments repository", payments, ["list", "listByMember", "create"]);
  assertPort("donations repository", donations, ["list", "create"]);
  assertPort("reports repository", reports, ["getFinancialSummary"]);
  assertPort("sessions repository", sessions, ["issue", "read"]);
  assertPort("password service", passwords, ["verify"]);

  dependencies.clock = clock;

  return {
    async login({ username, password }) {
      const account = await accounts.findByUsername(username);

      if (!account) {
        throw new AuthenticationError("invalid credentials");
      }

      const passwordMatches = await passwords.verify({ account, password });
      if (!passwordMatches) {
        throw new AuthenticationError("invalid credentials");
      }

      const token = await sessions.issue({
        accountId: account.id,
        roles: account.roles
      });

      return {
        token,
        account: presentAccount(account)
      };
    },

    async listMembers({ token }) {
      const { account } = await authenticateSession(dependencies, token);
      requirePermission({ roles: account.roles, permission: "members:read" });

      const items = await members.list();

      return {
        items: items.map((member) => presentMember(member))
      };
    },

    async createMember({ token, fullName, email, duesClass, status = "active", sponsorMemberId = null }) {
      const { account } = await authenticateSession(dependencies, token);
      requirePermission({ roles: account.roles, permission: "members:write" });

      const member = await members.create({
        fullName: requireNonEmptyString("fullName", fullName),
        email: requireNonEmptyString("email", email),
        duesClass: requireNonEmptyString("duesClass", duesClass),
        status: requireNonEmptyString("status", status),
        sponsorMemberId,
        createdAt: nowIso(clock)
      });

      return presentMember(member);
    },

    async submitSponsoredApplication({ token, applicantName, applicantEmail, notes = "" }) {
      const { account } = await authenticateSession(dependencies, token);

      const sponsorMemberId = account.memberId ?? null;

      if (account.roles.includes("member-self")) {
        requirePermission({ roles: account.roles, permission: "self:application:create" });
        requireMemberSelfAccount(account);
      } else {
        requirePermission({ roles: account.roles, permission: "members:write" });
      }

      const application = await applications.create({
        applicantName: requireNonEmptyString("applicantName", applicantName),
        applicantEmail: requireNonEmptyString("applicantEmail", applicantEmail),
        notes: typeof notes === "string" ? notes.trim() : "",
        sponsorMemberId,
        status: "submitted",
        createdAt: nowIso(clock)
      });

      return presentApplication(application);
    },

    async listApplications({ token }) {
      const { account } = await authenticateSession(dependencies, token);
      requirePermission({ roles: account.roles, permission: "members:read" });

      const items = await applications.list();

      return {
        items: items.map((application) => presentApplication(application))
      };
    },

    async reviewApplication({ token, applicationId, decision }) {
      const { account } = await authenticateSession(dependencies, token);
      requirePermission({ roles: account.roles, permission: "members:write" });

      const application = await requireExistingApplication(dependencies, applicationId);
      if (application.status !== "submitted") {
        throw new ValidationError("only submitted applications can be reviewed");
      }

      const normalizedDecision = requireDecision(decision);
      const reviewedAt = nowIso(clock);

      if (normalizedDecision === "reject") {
        const rejectedApplication = await applications.update(application.id, {
          status: "rejected",
          reviewedAt,
          reviewedByAccountId: account.id
        });

        return presentApplication(rejectedApplication);
      }

      const member = await members.create({
        fullName: application.applicantName,
        email: application.applicantEmail,
        duesClass: "standard",
        status: "applicant",
        sponsorMemberId: application.sponsorMemberId,
        createdAt: reviewedAt
      });

      const approvedApplication = await applications.update(application.id, {
        status: "approved",
        reviewedAt,
        reviewedByAccountId: account.id,
        memberId: member.id
      });

      return presentApplication(approvedApplication, member);
    },

    async createInvoice({ token, memberId, description, amountCents, dueDate }) {
      const { account } = await authenticateSession(dependencies, token);
      requirePermission({ roles: account.roles, permission: "billing:write" });

      await requireExistingMember(dependencies, memberId);

      const invoice = await invoices.create({
        memberId,
        description: requireNonEmptyString("description", description),
        amountCents: requirePositiveInteger("amountCents", amountCents),
        dueDate: requireNonEmptyString("dueDate", dueDate),
        status: "draft",
        createdAt: nowIso(clock),
        createdByAccountId: account.id
      });

      return presentInvoice(invoice);
    },

    async issueInvoice({ token, invoiceId }) {
      const { account } = await authenticateSession(dependencies, token);
      requirePermission({ roles: account.roles, permission: "billing:write" });

      const invoice = await requireExistingInvoice(dependencies, invoiceId);
      if (invoice.status !== "draft") {
        throw new ValidationError("only draft invoices can be issued");
      }

      const updatedInvoice = await invoices.update(invoice.id, {
        status: "issued",
        issuedAt: nowIso(clock),
        issuedByAccountId: account.id
      });

      return presentInvoice(updatedInvoice);
    },

    async recordManualPayment({ token, memberId, amountCents, method }) {
      const { account } = await authenticateSession(dependencies, token);
      requirePermission({ roles: account.roles, permission: "billing:write" });

      return recordPaymentForMember(dependencies, {
        memberId,
        amountCents,
        method,
        source: "manual",
        recordedByAccountId: account.id
      });
    },

    async recordSelfPrepayment({ token, amountCents, method }) {
      const { account } = await authenticateSession(dependencies, token);
      requirePermission({ roles: account.roles, permission: "self:prepay" });

      return recordPaymentForMember(dependencies, {
        memberId: requireMemberSelfAccount(account),
        amountCents,
        method,
        source: "self-prepay",
        recordedByAccountId: account.id
      });
    },

    async recordDonation({ token, donorName, amountCents, source }) {
      const { account } = await authenticateSession(dependencies, token);
      requirePermission({ roles: account.roles, permission: "donations:write" });

      const donation = await donations.create({
        donorName: requireNonEmptyString("donorName", donorName),
        amountCents: requirePositiveInteger("amountCents", amountCents),
        source: requireNonEmptyString("source", source),
        receivedAt: nowIso(clock),
        recordedByAccountId: account.id
      });

      return presentDonation(donation);
    },

    async recordSelfDonation({ token, amountCents, source }) {
      const { account } = await authenticateSession(dependencies, token);
      requirePermission({ roles: account.roles, permission: "self:donate" });

      const member = await requireExistingMember(dependencies, requireMemberSelfAccount(account));

      const donation = await donations.create({
        donorName: member.fullName,
        amountCents: requirePositiveInteger("amountCents", amountCents),
        source: requireNonEmptyString("source", source),
        receivedAt: nowIso(clock),
        memberId: member.id
      });

      return presentDonation(donation);
    },

    async cancelOwnMembership({ token, reason = "" }) {
      const { account } = await authenticateSession(dependencies, token);
      requirePermission({ roles: account.roles, permission: "self:cancel" });

      const memberId = requireMemberSelfAccount(account);
      await requireExistingMember(dependencies, memberId);

      const updatedMember = await members.update(memberId, {
        status: "left",
        leftAt: nowIso(clock),
        cancellationReason: typeof reason === "string" ? reason.trim() : ""
      });

      return presentMember(updatedMember);
    },

    async getFinancialSummary({ token }) {
      const { account } = await authenticateSession(dependencies, token);
      requirePermission({ roles: account.roles, permission: "reports:read" });

      return reports.getFinancialSummary();
    }
  };
}
