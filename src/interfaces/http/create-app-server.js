import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  AuthenticationError,
  AuthorizationError,
  NotFoundError,
  ValidationError
} from "../../engine/errors.js";

const CURRENT_DIRECTORY = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = join(CURRENT_DIRECTORY, "..", "..", "..");
const FRONTEND_ROOT = join(PROJECT_ROOT, "frontend", "admin");

const STATIC_FILES = new Map([
  ["/", "index.html"],
  ["/app.js", "app.js"],
  ["/config.js", "config.js"],
  ["/styles.css", "styles.css"]
]);

const CONTENT_TYPES = new Map([
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".css", "text/css; charset=utf-8"]
]);

function readAllowedOrigin(origin, allowedOrigins) {
  if (!origin) {
    return null;
  }

  if (allowedOrigins.includes("*")) {
    return origin;
  }

  return allowedOrigins.includes(origin) ? origin : null;
}

function buildCorsHeaders(origin, allowedOrigins) {
  const allowedOrigin = readAllowedOrigin(origin, allowedOrigins);

  if (!allowedOrigin) {
    return {};
  }

  return {
    "access-control-allow-origin": allowedOrigin,
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "authorization,content-type",
    vary: "Origin"
  };
}

function sendJson(response, statusCode, payload, extraHeaders = {}) {
  response.writeHead(statusCode, {
    "content-type": "application/json; charset=utf-8",
    ...extraHeaders
  });
  response.end(JSON.stringify(payload));
}

function sendEmpty(response, statusCode, extraHeaders = {}) {
  response.writeHead(statusCode, extraHeaders);
  response.end();
}

async function readJsonBody(request) {
  const chunks = [];

  for await (const chunk of request) {
    chunks.push(chunk);
  }

  const body = Buffer.concat(chunks).toString("utf8");
  if (!body) {
    return {};
  }

  try {
    return JSON.parse(body);
  } catch (error) {
    throw new ValidationError("invalid json body");
  }
}

function readBearerToken(request) {
  const header = request.headers.authorization ?? "";
  const [scheme, token] = header.split(" ");

  if (scheme !== "Bearer" || !token) {
    return null;
  }

  return token;
}

async function serveStaticAsset(pathname, response) {
  const relativePath = STATIC_FILES.get(pathname);

  if (!relativePath) {
    return false;
  }

  const filePath = join(FRONTEND_ROOT, relativePath);
  const body = await readFile(filePath);
  const contentType = CONTENT_TYPES.get(extname(filePath)) ?? "application/octet-stream";

  response.writeHead(200, {
    "content-type": contentType
  });
  response.end(body);
  return true;
}

function statusForError(error) {
  if (error instanceof ValidationError) {
    return 400;
  }

  if (error instanceof AuthenticationError) {
    return 401;
  }

  if (error instanceof AuthorizationError) {
    return 403;
  }

  if (error instanceof NotFoundError) {
    return 404;
  }

  return 500;
}

function matchPath(pathname, expression) {
  const match = pathname.match(expression);
  return match ? match.slice(1) : null;
}

export function createAppServer(runtime) {
  const allowedOrigins = runtime.config.allowedOrigins ?? [];

  return createServer(async (request, response) => {
    const url = new URL(request.url, "http://127.0.0.1");
    const corsHeaders = buildCorsHeaders(request.headers.origin, allowedOrigins);

    try {
      if (request.method === "OPTIONS" && url.pathname.startsWith("/api/")) {
        sendEmpty(response, 204, corsHeaders);
        return;
      }

      if (request.method === "GET" && url.pathname === "/healthz") {
        sendJson(response, 200, { status: "ok" }, corsHeaders);
        return;
      }

      if (request.method === "POST" && url.pathname === "/api/v1/session/login") {
        const body = await readJsonBody(request);
        const payload = await runtime.engine.login(body);
        sendJson(response, 200, payload, corsHeaders);
        return;
      }

      if (request.method === "POST" && url.pathname === "/api/v1/session/logout") {
        await runtime.engine.logout({
          token: readBearerToken(request)
        });
        sendEmpty(response, 204, corsHeaders);
        return;
      }

      if (request.method === "GET" && url.pathname === "/api/v1/members") {
        const payload = await runtime.engine.listMembers({
          token: readBearerToken(request)
        });
        sendJson(response, 200, payload, corsHeaders);
        return;
      }

      if (request.method === "POST" && url.pathname === "/api/v1/members") {
        const body = await readJsonBody(request);
        const payload = await runtime.engine.createMember({
          token: readBearerToken(request),
          ...body
        });
        sendJson(response, 201, payload, corsHeaders);
        return;
      }

      if (request.method === "GET" && url.pathname === "/api/v1/applications") {
        const payload = await runtime.engine.listApplications({
          token: readBearerToken(request)
        });
        sendJson(response, 200, payload, corsHeaders);
        return;
      }

      if (request.method === "POST" && url.pathname === "/api/v1/self/sponsored-applications") {
        const body = await readJsonBody(request);
        const payload = await runtime.engine.submitSponsoredApplication({
          token: readBearerToken(request),
          ...body
        });
        sendJson(response, 201, payload, corsHeaders);
        return;
      }

      const applicationReviewMatch = matchPath(url.pathname, /^\/api\/v1\/applications\/([^/]+)\/review$/);
      if (request.method === "POST" && applicationReviewMatch) {
        const [applicationId] = applicationReviewMatch;
        const body = await readJsonBody(request);
        const payload = await runtime.engine.reviewApplication({
          token: readBearerToken(request),
          applicationId,
          decision: body.decision
        });
        sendJson(response, 200, payload, corsHeaders);
        return;
      }

      if (request.method === "POST" && url.pathname === "/api/v1/invoices") {
        const body = await readJsonBody(request);
        const payload = await runtime.engine.createInvoice({
          token: readBearerToken(request),
          ...body
        });
        sendJson(response, 201, payload, corsHeaders);
        return;
      }

      const invoiceIssueMatch = matchPath(url.pathname, /^\/api\/v1\/invoices\/([^/]+)\/issue$/);
      if (request.method === "POST" && invoiceIssueMatch) {
        const [invoiceId] = invoiceIssueMatch;
        const payload = await runtime.engine.issueInvoice({
          token: readBearerToken(request),
          invoiceId
        });
        sendJson(response, 200, payload, corsHeaders);
        return;
      }

      if (request.method === "POST" && url.pathname === "/api/v1/payments/manual") {
        const body = await readJsonBody(request);
        const payload = await runtime.engine.recordManualPayment({
          token: readBearerToken(request),
          ...body
        });
        sendJson(response, 201, payload, corsHeaders);
        return;
      }

      if (request.method === "POST" && url.pathname === "/api/v1/donations") {
        const body = await readJsonBody(request);
        const payload = await runtime.engine.recordDonation({
          token: readBearerToken(request),
          ...body
        });
        sendJson(response, 201, payload, corsHeaders);
        return;
      }

      if (request.method === "POST" && url.pathname === "/api/v1/self/prepayments") {
        const body = await readJsonBody(request);
        const payload = await runtime.engine.recordSelfPrepayment({
          token: readBearerToken(request),
          ...body
        });
        sendJson(response, 201, payload, corsHeaders);
        return;
      }

      if (request.method === "POST" && url.pathname === "/api/v1/self/donations") {
        const body = await readJsonBody(request);
        const payload = await runtime.engine.recordSelfDonation({
          token: readBearerToken(request),
          ...body
        });
        sendJson(response, 201, payload, corsHeaders);
        return;
      }

      if (request.method === "POST" && url.pathname === "/api/v1/self/cancellation") {
        const body = await readJsonBody(request);
        const payload = await runtime.engine.cancelOwnMembership({
          token: readBearerToken(request),
          ...body
        });
        sendJson(response, 200, payload, corsHeaders);
        return;
      }

      if (request.method === "GET" && url.pathname === "/api/v1/reports/financial-summary") {
        const payload = await runtime.engine.getFinancialSummary({
          token: readBearerToken(request)
        });
        sendJson(response, 200, payload, corsHeaders);
        return;
      }

      if (request.method === "GET" && await serveStaticAsset(url.pathname, response)) {
        return;
      }

      sendJson(response, 404, { error: "not found" }, corsHeaders);
    } catch (error) {
      sendJson(
        response,
        statusForError(error),
        { error: error.message },
        corsHeaders
      );
    }
  });
}
