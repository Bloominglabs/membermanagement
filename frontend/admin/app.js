const TOKEN_STORAGE_KEY = "membermanagement.admin.token";
const ACCOUNT_STORAGE_KEY = "membermanagement.admin.account";

const form = document.querySelector("#login-form");
const statusElement = document.querySelector("#status");
const membersElement = document.querySelector("#members");
const summaryElement = document.querySelector("#summary");

const config = window.MemberManagementConfig || {};
const apiBaseUrl = config.apiBaseUrl || window.location.origin;

function formatMoney(cents, currency = "USD") {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency
  }).format(cents / 100);
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

function setStatus(message) {
  statusElement.textContent = message;
}

function renderMembers(items) {
  membersElement.replaceChildren(
    ...items.map((member) => {
      const item = document.createElement("li");
      item.textContent = `${member.fullName} (${member.status}, ${member.duesClass})`;
      return item;
    })
  );
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
  const token = sessionStorage.getItem(TOKEN_STORAGE_KEY);

  if (!token) {
    setStatus("Not authenticated.");
    return;
  }

  const account = loadPersistedAccount();
  if (account) {
    setStatus(`Authenticated as ${account.username}.`);
  }

  const [membersPayload, summaryPayload] = await Promise.all([
    fetchJson("/api/v1/members", token),
    fetchJson("/api/v1/reports/financial-summary", token)
  ]);

  renderMembers(membersPayload.items);
  renderSummary(summaryPayload);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const formData = new FormData(form);

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

    sessionStorage.setItem(TOKEN_STORAGE_KEY, payload.token);
    sessionStorage.setItem(ACCOUNT_STORAGE_KEY, JSON.stringify(payload.account));
    setStatus(`Authenticated as ${payload.account.username}.`);
    await refreshDashboard();
  } catch (error) {
    setStatus(error.message);
  }
});

refreshDashboard().catch((error) => {
  setStatus(error.message);
});

