import { ControllerClientError, createControllerClient } from "/assets/controller-client.js";

const routes = Object.freeze({
  "/": {
    key: "dashboard",
    title: "Tableau de bord",
    message: "Les indicateurs opérationnels seront ajoutés au jalon 2R.",
  },
  "/dashboard": {
    key: "dashboard",
    title: "Tableau de bord",
    message: "Les indicateurs opérationnels seront ajoutés au jalon 2R.",
  },
  "/projects": {
    key: "projects",
    title: "Projets",
    message: "La création, l’import et l’administration des projets arriveront au jalon 2S.",
  },
  "/objectives": {
    key: "objectives",
    title: "Objectifs",
    message: "Le cycle de vie des objectifs sera relié à la Console au jalon 2U.",
  },
  "/executions": {
    key: "executions",
    title: "Exécutions",
    message: "Les plans, tâches, workers et sandboxes seront affichés au jalon 2V.",
  },
  "/reviews": {
    key: "reviews",
    title: "Reviews",
    message: "Les décisions humaines et Recovery seront disponibles au jalon 2W.",
  },
  "/events": {
    key: "events",
    title: "Événements",
    message: "Le flux temps réel et la réconciliation seront activés au jalon 2X.",
  },
  "/administration": {
    key: "administration",
    title: "Administration",
    message: "Les diagnostics bornés seront ajoutés progressivement sans exposer de secrets.",
  },
});

const client = createControllerClient();
const sessionPanel = document.getElementById("session-panel");
const sessionStatus = document.getElementById("session-status");
const sessionDetail = document.getElementById("session-detail");
const loginForm = document.getElementById("login-form");
const passwordInput = document.getElementById("operator-password");
const loginButton = document.getElementById("login-button");
const logoutButton = document.getElementById("logout-button");
const connectionBadge = document.getElementById("controller-connection");
const connectionMessage = document.getElementById("controller-message");

function canonicalPath(pathname) {
  if (pathname.length > 1 && pathname.endsWith("/")) {
    return pathname.slice(0, -1);
  }
  return pathname;
}

function routeFor(pathname) {
  return routes[canonicalPath(pathname)] ?? routes["/"];
}

function render(pathname, focusMain = false) {
  const route = routeFor(pathname);
  document.title = `${route.title} · HermesOps Console`;
  document.getElementById("page-title").textContent = route.title;
  document.getElementById("route-title").textContent = route.title;
  document.getElementById("route-message").textContent = route.message;

  document.querySelectorAll("nav a[data-route]").forEach((link) => {
    const active = link.dataset.route === route.key;
    link.toggleAttribute("aria-current", active);
    if (active) {
      link.setAttribute("aria-current", "page");
    }
  });

  if (focusMain) {
    document.getElementById("main-content").focus({ preventScroll: true });
  }
}

function setConnection(kind, label, message) {
  connectionBadge.dataset.state = kind;
  connectionBadge.textContent = label;
  connectionMessage.textContent = message;
}

function showSignedOut(message = "Authentification requise pour accéder aux données du Controller.") {
  sessionPanel.dataset.state = "signed-out";
  sessionStatus.textContent = "Session fermée";
  sessionDetail.textContent = message;
  loginForm.hidden = false;
  logoutButton.hidden = true;
  passwordInput.value = "";
  setConnection("signed-out", "Controller accessible", "La session navigateur n’est pas ouverte.");
}

function showAuthenticated(session, capabilities) {
  const actor = session.actor_id === "operator" ? "Opérateur local" : "Session authentifiée";
  const features = capabilities && capabilities.features && typeof capabilities.features === "object"
    ? Object.values(capabilities.features).filter(Boolean).length
    : 0;
  sessionPanel.dataset.state = "authenticated";
  sessionStatus.textContent = actor;
  sessionDetail.textContent = `${features} capacités Controller annoncées. Les vues métier restent hors du jalon 2Q.`;
  loginForm.hidden = true;
  logoutButton.hidden = false;
  passwordInput.value = "";
  setConnection("authenticated", "Controller connecté", "Session vérifiée par l’état autoritaire du Controller.");
}

function showUnavailable(error) {
  sessionPanel.dataset.state = "unavailable";
  sessionStatus.textContent = "Controller indisponible";
  const requestSuffix = error instanceof ControllerClientError && error.requestId
    ? ` Référence : ${error.requestId}.`
    : "";
  sessionDetail.textContent = `Aucune commande n’est mise en attente dans le navigateur.${requestSuffix}`;
  loginForm.hidden = true;
  logoutButton.hidden = true;
  passwordInput.value = "";
  setConnection("unavailable", "Mode dégradé", "La navigation locale reste disponible en lecture statique.");
}

async function refreshSession() {
  setConnection("checking", "Vérification…", "Lecture de la session auprès du Controller.");
  try {
    const session = await client.session();
    if (!session.authenticated) {
      showSignedOut();
      return;
    }
    const capabilities = await client.capabilities();
    showAuthenticated(session, capabilities);
  } catch (error) {
    if (error instanceof ControllerClientError && error.status === 401) {
      showSignedOut();
      return;
    }
    showUnavailable(error);
  }
}

document.addEventListener("click", (event) => {
  const link = event.target.closest("a[href]");
  if (!link || link.origin !== window.location.origin) {
    return;
  }
  const path = canonicalPath(link.pathname);
  if (!Object.hasOwn(routes, path)) {
    return;
  }
  event.preventDefault();
  window.history.pushState({}, "", path);
  render(path, true);
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginButton.disabled = true;
  sessionStatus.textContent = "Connexion en cours…";
  sessionDetail.textContent = "Le mot de passe est envoyé uniquement au Controller et n’est pas conservé par la Console.";
  try {
    await client.login("operator", passwordInput.value);
    passwordInput.value = "";
    await refreshSession();
  } catch (error) {
    passwordInput.value = "";
    if (error instanceof ControllerClientError && [401, 429].includes(error.status)) {
      showSignedOut("Connexion refusée. Vérifiez le mot de passe ou attendez avant une nouvelle tentative.");
    } else {
      showUnavailable(error);
    }
  } finally {
    loginButton.disabled = false;
  }
});

logoutButton.addEventListener("click", async () => {
  logoutButton.disabled = true;
  sessionStatus.textContent = "Déconnexion en cours…";
  try {
    await client.logout();
    await refreshSession();
  } catch (error) {
    showUnavailable(error);
  } finally {
    logoutButton.disabled = false;
  }
});

window.addEventListener("popstate", () => render(window.location.pathname));
render(window.location.pathname);
refreshSession();
