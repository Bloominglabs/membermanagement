import { AuthenticationError } from "./errors.js";
import { requirePermission } from "./permissions.js";
import { assertPort } from "./ports.js";

function presentAccount(account) {
  return {
    id: account.id,
    username: account.username,
    roles: [...account.roles]
  };
}

function presentMember(member) {
  return {
    id: member.id,
    fullName: member.fullName,
    status: member.status,
    duesClass: member.duesClass
  };
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

export function createEngine(dependencies) {
  const {
    accounts,
    members,
    reports,
    sessions,
    passwords
  } = dependencies;

  assertPort("accounts repository", accounts, ["findByUsername", "findById"]);
  assertPort("members repository", members, ["list"]);
  assertPort("reports repository", reports, ["getFinancialSummary"]);
  assertPort("sessions repository", sessions, ["issue", "read"]);
  assertPort("password service", passwords, ["verify"]);

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

      requirePermission({
        roles: account.roles,
        permission: "members:read"
      });

      const items = await members.list();

      return {
        items: items.map((member) => presentMember(member))
      };
    },

    async getFinancialSummary({ token }) {
      const { account } = await authenticateSession(dependencies, token);

      requirePermission({
        roles: account.roles,
        permission: "reports:read"
      });

      return reports.getFinancialSummary();
    }
  };
}

