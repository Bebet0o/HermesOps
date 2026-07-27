const ALLOWED_ENDPOINTS = Object.freeze({
  session: Object.freeze({ method: "GET", path: "/api/v1/auth/session" }),
  login: Object.freeze({ method: "POST", path: "/api/v1/auth/login" }),
  csrf: Object.freeze({ method: "POST", path: "/api/v1/auth/csrf" }),
  logout: Object.freeze({ method: "POST", path: "/api/v1/auth/logout" }),
  capabilities: Object.freeze({ method: "GET", path: "/api/v1/system/capabilities" }),
});

const REQUEST_TIMEOUT_MS = 7000;
const MAX_ERROR_TEXT = 160;

export class ControllerClientError extends Error {
  constructor(message, { status = 0, code = "controller_unavailable", requestId = "" } = {}) {
    super(message);
    this.name = "ControllerClientError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

function idempotencyKey(label) {
  if (!globalThis.crypto || typeof globalThis.crypto.randomUUID !== "function") {
    throw new ControllerClientError("Le navigateur ne fournit pas une source aléatoire sûre.", {
      code: "secure_random_unavailable",
    });
  }
  return `console-${label}-${globalThis.crypto.randomUUID()}`;
}

function safeText(value, fallback) {
  if (typeof value !== "string") {
    return fallback;
  }
  const normalized = value.replace(/[\u0000-\u001f\u007f]/g, " ").trim();
  return normalized.slice(0, MAX_ERROR_TEXT) || fallback;
}

async function parsePayload(response) {
  const contentType = response.headers.get("content-type") || "";
  const mediaType = contentType.split(";", 1)[0].trim().toLowerCase();
  if (!["application/json", "application/problem+json"].includes(mediaType)) {
    throw new ControllerClientError("Réponse Controller invalide.", {
      status: response.status,
      code: "invalid_controller_response",
      requestId: response.headers.get("x-request-id") || "",
    });
  }
  try {
    const payload = await response.json();
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      throw new TypeError("payload");
    }
    return payload;
  } catch (error) {
    if (error instanceof ControllerClientError) {
      throw error;
    }
    throw new ControllerClientError("Réponse Controller invalide.", {
      status: response.status,
      code: "invalid_controller_response",
      requestId: response.headers.get("x-request-id") || "",
    });
  }
}

async function request(endpointName, { body, csrfToken, idempotencyLabel } = {}) {
  const endpoint = ALLOWED_ENDPOINTS[endpointName];
  if (!endpoint) {
    throw new ControllerClientError("Opération Controller non autorisée.", {
      code: "unsupported_controller_operation",
    });
  }

  const headers = new Headers({ Accept: "application/json" });
  let encodedBody;
  if (endpoint.method === "POST") {
    headers.set("Content-Type", "application/json");
    headers.set("Idempotency-Key", idempotencyKey(idempotencyLabel || endpointName));
    encodedBody = JSON.stringify(body ?? {});
  }
  if (csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }

  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let response;
  try {
    response = await fetch(endpoint.path, {
      method: endpoint.method,
      headers,
      body: encodedBody,
      credentials: "same-origin",
      cache: "no-store",
      redirect: "error",
      referrerPolicy: "no-referrer",
      signal: controller.signal,
    });
  } catch (error) {
    const timeoutMessage = error && error.name === "AbortError"
      ? "Le Controller ne répond pas dans le délai prévu."
      : "Le Controller est indisponible.";
    throw new ControllerClientError(timeoutMessage, { code: "controller_unavailable" });
  } finally {
    globalThis.clearTimeout(timeout);
  }

  const payload = await parsePayload(response);
  if (!response.ok) {
    throw new ControllerClientError(
      safeText(payload.title, "La requête Controller a échoué."),
      {
        status: response.status,
        code: safeText(payload.code, "controller_request_failed"),
        requestId: safeText(payload.request_id, response.headers.get("x-request-id") || ""),
      },
    );
  }
  return payload;
}

function dataObject(payload) {
  if (!payload.data || typeof payload.data !== "object" || Array.isArray(payload.data)) {
    throw new ControllerClientError("Réponse Controller incomplète.", {
      code: "invalid_controller_response",
    });
  }
  return payload.data;
}

export function createControllerClient() {
  return Object.freeze({
    async session() {
      return dataObject(await request("session"));
    },
    async login(username, password) {
      if (username !== "operator" || typeof password !== "string" || password.length === 0) {
        throw new ControllerClientError("Identifiants invalides.", {
          status: 400,
          code: "invalid_credentials",
        });
      }
      return dataObject(await request("login", {
        body: { username, password },
        idempotencyLabel: "login",
      }));
    },
    async capabilities() {
      return dataObject(await request("capabilities"));
    },
    async logout() {
      const csrf = dataObject(await request("csrf", {
        body: {},
        idempotencyLabel: "csrf",
      }));
      if (typeof csrf.token !== "string" || !csrf.token.startsWith("csrf1.")) {
        throw new ControllerClientError("Jeton de sécurité Controller invalide.", {
          code: "invalid_csrf_response",
        });
      }
      return dataObject(await request("logout", {
        body: {},
        csrfToken: csrf.token,
        idempotencyLabel: "logout",
      }));
    },
  });
}
