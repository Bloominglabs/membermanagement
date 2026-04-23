import { createDocumentRuntime } from "../store/create-document-runtime.js";
import { createDefaultDocument } from "../store/default-document.js";

export function createInMemoryRuntime(options = {}) {
  return createDocumentRuntime({
    document: createDefaultDocument({
      accounts: options.accounts,
      members: options.members,
      applications: options.applications,
      invoices: options.invoices,
      payments: options.payments,
      donations: options.donations,
      sessions: options.sessions,
      nextIds: options.nextIds
    }),
    allowedOrigins: options.allowedOrigins,
    clock: options.clock,
    sessionLifetimeMinutes: options.sessionLifetimeMinutes
  });
}
