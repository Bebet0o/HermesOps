import { ControllerClientError, createControllerClient } from "/assets/controller-client.js";

const routes = Object.freeze({
  "/": {
    key: "dashboard",
    title: "Tableau de bord",
    message: "Connectez-vous pour lire le tableau de bord opérationnel.",
  },
  "/dashboard": {
    key: "dashboard",
    title: "Tableau de bord",
    message: "Connectez-vous pour lire le tableau de bord opérationnel.",
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
    message: "Les plans, tâches, workers et sandboxes détaillés seront affichés au jalon 2V.",
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
const dashboardPanel = document.getElementById("dashboard-panel");
const dashboardRefresh = document.getElementById("dashboard-refresh");
const dashboardStatus = document.getElementById("dashboard-status");
const dashboardCoverage = document.getElementById("dashboard-coverage");
const routePanel = document.getElementById("route-panel");

const dashboardResources = Object.freeze([
  Object.freeze({ key: "projects", load: () => client.projects() }),
  Object.freeze({ key: "objectives", load: () => client.objectives() }),
  Object.freeze({ key: "reviews", load: () => client.reviews() }),
  Object.freeze({ key: "recoveries", load: () => client.recoveries() }),
  Object.freeze({ key: "plans", load: () => client.plans() }),
  Object.freeze({ key: "assignments", load: () => client.reviewerAssignments() }),
]);

const activeObjectiveStates = new Set(["planned", "planning", "running", "blocked", "paused"]);
const activePlanTerminalStates = new Set(["succeeded", "failed", "cancelled", "completed"]);
const objectiveAttentionStates = new Set(["blocked", "failed"]);
const reviewAttentionStates = new Set(["rejected", "pending", "running", "human_review", "debt"]);
const recoveryAttentionStates = new Set(["blocked", "failed", "pending", "recovery_required"]);
const assignmentAttentionStates = new Set(["assigned", "claimed", "failed", "pending"]);

let authenticated = false;
let dashboardLoading = false;
let dashboardGeneration = 0;
let dashboardLoaded = false;

function canonicalPath(pathname) {
  if (pathname.length > 1 && pathname.endsWith("/")) {
    return pathname.slice(0, -1);
  }
  return pathname;
}

function routeFor(pathname) {
  return routes[canonicalPath(pathname)] ?? routes["/"];
}

function currentRoute() {
  return routeFor(window.location.pathname);
}

function safeText(value, fallback = "Non renseigné", maximum = 120) {
  if (typeof value !== "string") {
    return fallback;
  }
  const normalized = value.replace(/[\u0000-\u001f\u007f]/g, " ").trim();
  return normalized.slice(0, maximum) || fallback;
}

function safeState(item) {
  return safeText(item && item.state, "inconnu", 40).toLowerCase();
}

function safeId(item, fallback) {
  return safeText(item && item.id, fallback, 96);
}

function displayFunctionalPanel() {
  const dashboardRoute = currentRoute().key === "dashboard";
  dashboardPanel.hidden = !dashboardRoute || !authenticated;
  routePanel.hidden = dashboardRoute && authenticated;
}

function render(pathname, focusMain = false) {
  const route = routeFor(pathname);
  document.title = `${route.title} · HermesOps Console`;
  document.getElementById("page-title").textContent = route.title;
  document.getElementById("route-title").textContent = route.title;
  document.getElementById("route-message").textContent = route.message;

  document.querySelectorAll("nav a[data-route]").forEach((link) => {
    const active = link.dataset.route === route.key;
    link.removeAttribute("aria-current");
    if (active) {
      link.setAttribute("aria-current", "page");
    }
  });

  displayFunctionalPanel();
  if (route.key === "dashboard" && authenticated && !dashboardLoaded) {
    void refreshDashboard();
  }

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
  authenticated = false;
  dashboardGeneration += 1;
  dashboardLoading = false;
  dashboardLoaded = false;
  dashboardRefresh.disabled = false;
  sessionPanel.dataset.state = "signed-out";
  sessionStatus.textContent = "Session fermée";
  sessionDetail.textContent = message;
  loginForm.hidden = false;
  logoutButton.hidden = true;
  passwordInput.value = "";
  setConnection("signed-out", "Controller accessible", "La session navigateur n’est pas ouverte.");
  displayFunctionalPanel();
}

function showAuthenticated(session, capabilities) {
  const actor = session.actor_id === "operator" ? "Opérateur local" : "Session authentifiée";
  const features = capabilities && capabilities.features && typeof capabilities.features === "object"
    ? Object.values(capabilities.features).filter(Boolean).length
    : 0;
  authenticated = true;
  dashboardLoading = false;
  dashboardRefresh.disabled = false;
  sessionPanel.dataset.state = "authenticated";
  sessionStatus.textContent = actor;
  sessionDetail.textContent = `${features} capacités Controller annoncées. Les collections du dashboard restent bornées.`;
  loginForm.hidden = true;
  logoutButton.hidden = false;
  passwordInput.value = "";
  setConnection("authenticated", "Controller connecté", "Session vérifiée par l’état autoritaire du Controller.");
  displayFunctionalPanel();
  if (currentRoute().key === "dashboard") {
    void refreshDashboard();
  }
}

function showUnavailable(error) {
  authenticated = false;
  dashboardGeneration += 1;
  dashboardLoading = false;
  dashboardLoaded = false;
  dashboardRefresh.disabled = false;
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
  displayFunctionalPanel();
}

function clearList(list) {
  list.replaceChildren();
}

function appendEmpty(list, message) {
  const item = document.createElement("li");
  item.className = "empty-state";
  item.textContent = message;
  list.append(item);
}

function appendOperationalItem(list, { label, title, state, detail }) {
  const item = document.createElement("li");
  const top = document.createElement("div");
  const type = document.createElement("span");
  const heading = document.createElement("strong");
  const badge = document.createElement("span");
  const description = document.createElement("p");

  top.className = "operational-item-heading";
  type.className = "operational-type";
  type.textContent = label;
  heading.textContent = title;
  badge.className = "state-badge";
  badge.dataset.state = state;
  badge.textContent = state;
  description.textContent = detail;

  top.append(type, badge);
  item.append(top, heading, description);
  list.append(item);
}

function collectionItems(collections, key) {
  return collections[key] ? collections[key].items : [];
}

function attentionEntries(collections) {
  const entries = [];
  for (const objective of collectionItems(collections, "objectives")) {
    const state = safeState(objective);
    if (objectiveAttentionStates.has(state)) {
      const projects = Array.isArray(objective.project_ids)
        ? objective.project_ids.map((value) => safeText(value, "", 48)).filter(Boolean).join(", ")
        : "Projet non renseigné";
      entries.push({
        label: "Objectif",
        title: safeText(objective.title, safeId(objective, "Objectif")),
        state,
        detail: projects || "Projet non renseigné",
      });
    }
  }
  for (const review of collectionItems(collections, "reviews")) {
    const state = safeState(review);
    if (reviewAttentionStates.has(state)) {
      entries.push({
        label: "Review",
        title: safeId(review, "Review"),
        state,
        detail: safeText(review.summary, `Projet ${safeText(review.project_id, "inconnu", 48)}`),
      });
    }
  }
  for (const recovery of collectionItems(collections, "recoveries")) {
    const state = safeState(recovery);
    if (recoveryAttentionStates.has(state)) {
      entries.push({
        label: "Recovery",
        title: safeId(recovery, "Recovery"),
        state,
        detail: `Projet ${safeText(recovery.project_id, "inconnu", 48)}`,
      });
    }
  }
  for (const assignment of collectionItems(collections, "assignments")) {
    const state = safeState(assignment);
    if (assignmentAttentionStates.has(state)) {
      entries.push({
        label: "Review assignée",
        title: safeId(assignment, "Assignation"),
        state,
        detail: `Run ${safeText(assignment.run_id, "non renseigné", 72)}`,
      });
    }
  }
  return entries.slice(0, 8);
}

function renderDashboard(collections, errors) {
  const projects = collectionItems(collections, "projects");
  const objectives = collectionItems(collections, "objectives");
  const plans = collectionItems(collections, "plans");
  const enabledProjects = projects.filter((item) => safeState(item) === "enabled");
  const activeObjectives = objectives.filter((item) => activeObjectiveStates.has(safeState(item)));
  const attention = attentionEntries(collections);

  document.getElementById("metric-projects").textContent = String(enabledProjects.length);
  document.getElementById("metric-projects-detail").textContent = `${projects.length} projet(s) visible(s) sur la page bornée.`;
  document.getElementById("metric-objectives").textContent = String(activeObjectives.length);
  document.getElementById("metric-objectives-detail").textContent = `${objectives.length} objectif(s) visible(s), états Controller conservés.`;
  document.getElementById("metric-attention").textContent = String(attention.length);
  document.getElementById("metric-attention-detail").textContent = attention.length
    ? "Éléments visibles nécessitant une vérification opérateur."
    : "Aucun blocage explicite dans les données reçues.";
  document.getElementById("attention-count").textContent = String(attention.length);

  const attentionList = document.getElementById("attention-list");
  clearList(attentionList);
  if (attention.length === 0) {
    appendEmpty(attentionList, "Aucun élément d’attention explicite dans les collections disponibles.");
  } else {
    attention.forEach((entry) => appendOperationalItem(attentionList, entry));
  }

  const activeList = document.getElementById("active-work-list");
  clearList(activeList);
  const activePlans = plans
    .filter((item) => !activePlanTerminalStates.has(safeState(item)))
    .slice(0, 6);
  if (activePlans.length === 0) {
    appendEmpty(activeList, "Aucun plan actif visible sur la première page.");
  } else {
    for (const plan of activePlans) {
      const counts = plan && typeof plan.task_counts === "object" && plan.task_counts !== null
        ? plan.task_counts
        : {};
      appendOperationalItem(activeList, {
        label: "Plan",
        title: safeId(plan, "Plan"),
        state: safeState(plan),
        detail: `${Number.isSafeInteger(counts.total) ? counts.total : 0} tâche(s) · objectif ${safeText(plan.objective_id, "inconnu", 72)}`,
      });
    }
  }

  const projectList = document.getElementById("project-list");
  clearList(projectList);
  if (projects.length === 0) {
    appendEmpty(projectList, "Aucun projet visible dans la projection Controller.");
  } else {
    for (const project of projects.slice(0, 6)) {
      appendOperationalItem(projectList, {
        label: "Projet",
        title: safeText(project.name, safeId(project, "Projet")),
        state: safeState(project),
        detail: `Branche ${safeText(project.default_branch, "non renseignée", 48)}`,
      });
    }
  }

  const truncated = Object.values(collections).some((collection) => collection.truncated);
  const unavailable = errors.length;
  const coverage = [];
  coverage.push(truncated
    ? "Une ou plusieurs collections possèdent une page suivante : le dashboard reste volontairement partiel."
    : "Toutes les premières pages reçues sont complètes selon leurs métadonnées.");
  if (unavailable) {
    coverage.push(`${unavailable} collection(s) indisponible(s) : les autres données restent affichées sans extrapolation.`);
  }
  dashboardCoverage.textContent = coverage.join(" ");

  const now = new Date();
  const readableTime = Number.isNaN(now.getTime())
    ? "lecture terminée"
    : now.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  dashboardStatus.textContent = unavailable
    ? `Lecture partielle à ${readableTime}.`
    : `Lecture complète des six collections à ${readableTime}.`;
}

async function refreshDashboard() {
  if (!authenticated || dashboardLoading) {
    return;
  }
  dashboardLoading = true;
  dashboardRefresh.disabled = true;
  dashboardStatus.textContent = "Lecture des projections Controller…";
  const generation = ++dashboardGeneration;
  try {
    const settled = await Promise.allSettled(dashboardResources.map((resource) => resource.load()));
    if (generation !== dashboardGeneration || !authenticated) {
      return;
    }
    const collections = {};
    const errors = [];
    settled.forEach((result, index) => {
      const resource = dashboardResources[index];
      if (result.status === "fulfilled") {
        collections[resource.key] = result.value;
      } else {
        errors.push(result.reason);
      }
    });
    const sessionError = errors.find((error) => error instanceof ControllerClientError && error.status === 401);
    if (sessionError) {
      showSignedOut("Session expirée. Reconnectez-vous pour actualiser les données.");
      return;
    }
    if (Object.keys(collections).length === 0) {
      dashboardStatus.textContent = "Aucune collection opérationnelle n’est disponible.";
      dashboardCoverage.textContent = "Le dashboard ne conserve aucune ancienne valeur et n’invente aucun état.";
      return;
    }
    renderDashboard(collections, errors);
    dashboardLoaded = true;
  } finally {
    if (generation === dashboardGeneration) {
      dashboardLoading = false;
      dashboardRefresh.disabled = false;
    }
  }
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

dashboardRefresh.addEventListener("click", () => {
  dashboardLoaded = false;
  void refreshDashboard();
});

window.addEventListener("popstate", () => render(window.location.pathname));
render(window.location.pathname);
refreshSession();
