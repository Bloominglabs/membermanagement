const TOKEN_STORAGE_KEY = "membermanagement.admin.token";
const ACCOUNT_STORAGE_KEY = "membermanagement.admin.account";

const config = window.MemberManagementConfig || {};
const apiBaseUrl = config.apiBaseUrl || window.location.origin;

const loginForm = document.querySelector("#login-form");
const memberForm = document.querySelector("#member-form");
const invoiceForm = document.querySelector("#invoice-form");
const paymentForm = document.querySelector("#payment-form");
const donationForm = document.querySelector("#donation-form");
const refreshButton = document.querySelector("#refresh-button");

const statusElement = document.querySelector("#status");
const summaryElement = document.querySelector("#summary");
const membersElement = document.querySelector("#members");
const applicationsElement = document.querySelector("#applications");
const operationLogElement = document.querySelector("#operation-log");

function formatMoney(cents, currency = "USD") {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency
  }).format(cents / 100);
}

function getToken() {
  return sessionStorage.getItem(TOKEN_STORAGE_KEY);
}

function setToken(token) {
  sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
}

function loadPersistedAccount() {
  const raw = sessionStorage.getItem(ACCOUNT_STORAGE_KEY);

  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw);
  } catch (error) {
    sessionStorage.removeItem(ACCOUNT_STORAGE_KEY);
    return null;
  }
}

function setAccount(account) {
  sessionStorage.setItem(ACCOUNT_STORAGE_KEY, JSON.stringify(account));
}

function setStatus(message) {
  statusElement.textContent = message;
}

function appendLog(message) {
  const item = document.createElement("li");
  item.textContent = message;

  if (operationLogElement.children.length === 1 && operationLogElement.firstElementChild.textContent === "No actions recorded yet.") {
    operationLogElement.replaceChildren(item);
    return;
  }

  operationLogElement.prepend(item);
}

function renderSummary(summary) {
  const fields = [
    ["Receivable", formatMoney(summary.receivableCents, summary.currency)],
    ["Prepaid", formatMoney(summary.prepaidCents, summary.currency)],
    ["Donations YTD", formatMoney(summary.donationsYtdCents, summary.currency)]
  ];

  summaryElement.replaceChildren(
    ...fields.map(([label, value]) => {
      const row = document.createElement("div");
      const term = document.createElement("dt");
      const detail = document.createElement("dd");

      term.textContent = label;
      detail.textContent = value;
      row.append(term, detail);
      return row;
    })
  );
}

function renderMembers(items) {
  if (items.length === 0) {
    membersElement.replaceChildren(Object.assign(document.createElement("li"), {
      textContent: "No members yet."
    }));
    return;
  }

  membersElement.replaceChildren(
    ...items.map((member) => {
      const item = document.createElement("li");
      const name = document.createElement("strong");
      const id = document.createElement("div");
      const email = document.createElement("div");
      const status = document.createElement("div");

      name.textContent = member.fullName;
      id.textContent = member.id;
      email.textContent = member.email;
      status.textContent = `${member.status} / ${member.duesClass}`;
      item.append(name, id, email, status);
      return item;
    })
  );
}

function buildApplicationActions(application) {
  const actions = document.createElement("div");
  actions.className = "action-row";

  if (application.status !== "submitted") {
    actions.textContent = `Status: ${application.status}`;
    return actions;
  }

  for (const decision of ["approve", "reject"]) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = decision === "approve" ? "" : "secondary-button";
    button.textContent = decision === "approve" ? "Approve" : "Reject";
    button.addEventListener("click", async () => {
      try {
        await fetchJson(`/api/v1/applications/${application.id}/review`, getToken(), {
          method: "POST",
          headers: {
            "content-type": "application/json"
          },
          body: JSON.stringify({ decision })
        });
        appendLog(`Application ${application.id} marked ${decision}.`);
        await refreshDashboard();
      } catch (error) {
        setStatus(error.message);
      }
    });
    actions.append(button);
  }

  return actions;
}

function renderApplications(items) {
  if (items.length === 0) {
    applicationsElement.replaceChildren(Object.assign(document.createElement("li"), {
      textContent: "No applications yet."
    }));
    return;
  }

  applicationsElement.replaceChildren(
    ...items.map((application) => {
      const item = document.createElement("li");
      const title = document.createElement("strong");
      const details = document.createElement("div");

      title.textContent = application.applicantName;
      details.textContent = `${application.applicantEmail} | ${application.status}`;
      item.append(title, details, buildApplicationActions(application));
      return item;
    })
  );
}

function parseIntegerField(formData, fieldName) {
  return Number.parseInt(formData.get(fieldName), 10);
}

async function fetchJson(path, token, options = {}) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...(token ? { authorization: `Bearer ${token}` } : {})
    }
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "request failed");
  }

  return payload;
}

async function refreshDashboard() {
  const token = getToken();

  if (!token) {
    setStatus("Not authenticated.");
    return;
  }

  const account = loadPersistedAccount();
  if (account) {
    setStatus(`Authenticated as ${account.username}.`);
  }

  const [membersPayload, applicationsPayload, summaryPayload] = await Promise.all([
    fetchJson("/api/v1/members", token),
    fetchJson("/api/v1/applications", token),
    fetchJson("/api/v1/reports/financial-summary", token)
  ]);

  renderMembers(membersPayload.items);
  renderApplications(applicationsPayload.items);
  renderSummary(summaryPayload);
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const formData = new FormData(loginForm);

  try {
    const payload = await fetchJson("/api/v1/session/login", null, {
      method: "POST",
      headers: {
        "content-type": "application/json"
      },
      body: JSON.stringify({
        username: formData.get("username"),
        password: formData.get("password")
      })
    });

    setToken(payload.token);
    setAccount(payload.account);
    appendLog(`Authenticated as ${payload.account.username}.`);
    await refreshDashboard();
  } catch (error) {
    setStatus(error.message);
  }
});

memberForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(memberForm);

  try {
    const member = await fetchJson("/api/v1/members", getToken(), {
      method: "POST",
      headers: {
        "content-type": "application/json"
      },
      body: JSON.stringify({
        fullName: formData.get("fullName"),
        email: formData.get("email"),
        duesClass: formData.get("duesClass")
      })
    });

    appendLog(`Created member ${member.id} (${member.fullName}).`);
    memberForm.reset();
    await refreshDashboard();
  } catch (error) {
    setStatus(error.message);
  }
});

invoiceForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(invoiceForm);

  try {
    const invoice = await fetchJson("/api/v1/invoices", getToken(), {
      method: "POST",
      headers: {
        "content-type": "application/json"
      },
      body: JSON.stringify({
        memberId: formData.get("memberId"),
        description: formData.get("description"),
        amountCents: parseIntegerField(formData, "amountCents"),
        dueDate: formData.get("dueDate")
      })
    });

    if (formData.get("issueImmediately")) {
      await fetchJson(`/api/v1/invoices/${invoice.id}/issue`, getToken(), {
        method: "POST"
      });
      appendLog(`Created and issued invoice ${invoice.id} for member ${invoice.memberId}.`);
    } else {
      appendLog(`Created draft invoice ${invoice.id} for member ${invoice.memberId}.`);
    }

    invoiceForm.reset();
    await refreshDashboard();
  } catch (error) {
    setStatus(error.message);
  }
});

paymentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(paymentForm);

  try {
    const payment = await fetchJson("/api/v1/payments/manual", getToken(), {
      method: "POST",
      headers: {
        "content-type": "application/json"
      },
      body: JSON.stringify({
        memberId: formData.get("memberId"),
        amountCents: parseIntegerField(formData, "amountCents"),
        method: formData.get("method")
      })
    });

    appendLog(`Recorded payment ${payment.id} for member ${payment.memberId}.`);
    paymentForm.reset();
    await refreshDashboard();
  } catch (error) {
    setStatus(error.message);
  }
});

donationForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(donationForm);

  try {
    const donation = await fetchJson("/api/v1/donations", getToken(), {
      method: "POST",
      headers: {
        "content-type": "application/json"
      },
      body: JSON.stringify({
        donorName: formData.get("donorName"),
        amountCents: parseIntegerField(formData, "amountCents"),
        source: formData.get("source")
      })
    });

    appendLog(`Recorded donation ${donation.id} from ${donation.donorName}.`);
    donationForm.reset();
    await refreshDashboard();
  } catch (error) {
    setStatus(error.message);
  }
});

refreshButton.addEventListener("click", () => {
  refreshDashboard().catch((error) => {
    setStatus(error.message);
  });
});

refreshDashboard().catch((error) => {
  setStatus(error.message);
});
