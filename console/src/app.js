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
    message: "Connectez-vous pour créer, importer et administrer les projets via le Controller.",
  },
  "/hermesfiles": {
    key: "hermesfiles",
    title: "Hermesfiles",
    message: "Connectez-vous pour créer, valider, modifier et versionner les Hermesfiles.",
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
const projectPanel = document.getElementById("project-panel");
const projectRefresh = document.getElementById("project-refresh");
const projectStatus = document.getElementById("project-status");
const projectCoverage = document.getElementById("project-coverage");
const projectCount = document.getElementById("project-count");
const projectAdminList = document.getElementById("project-admin-list");
const projectCreateForm = document.getElementById("project-create-form");
const projectCreateMode = document.getElementById("project-create-mode");
const projectCreateUrlLabel = document.getElementById("project-create-url-label");
const projectCreateUrl = document.getElementById("project-create-url");
const projectCreateSubmit = document.getElementById("project-create-submit");
const projectDetailCard = document.getElementById("project-detail-card");
const projectDetailTitle = document.getElementById("project-detail-title");
const projectDetailState = document.getElementById("project-detail-state");
const projectDetailMeta = document.getElementById("project-detail-meta");
const projectUpdateForm = document.getElementById("project-update-form");
const projectUpdateSubmit = document.getElementById("project-update-submit");
const projectCommandReason = document.getElementById("project-command-reason");
const projectCommandButtons = document.getElementById("project-command-buttons");
const hermesfilePanel = document.getElementById("hermesfile-panel");
const hermesfileRefresh = document.getElementById("hermesfile-refresh");
const hermesfileStatus = document.getElementById("hermesfile-status");
const hermesfileCount = document.getElementById("hermesfile-count");
const hermesfileList = document.getElementById("hermesfile-list");
const hermesfileNew = document.getElementById("hermesfile-new");
const hermesfileEditorTitle = document.getElementById("hermesfile-editor-title");
const hermesfileEditorMode = document.getElementById("hermesfile-editor-mode");
const hermesfileMeta = document.getElementById("hermesfile-meta");
const hermesfileSource = document.getElementById("hermesfile-source");
const hermesfileValidate = document.getElementById("hermesfile-validate");
const hermesfileSave = document.getElementById("hermesfile-save");
const hermesfileValidity = document.getElementById("hermesfile-validity");
const hermesfileDiagnostics = document.getElementById("hermesfile-diagnostics");
const hermesfilePreview = document.getElementById("hermesfile-preview");
const hermesfileRevisionCount = document.getElementById("hermesfile-revision-count");
const hermesfileRevisions = document.getElementById("hermesfile-revisions");
const hermesfileDiffFrom = document.getElementById("hermesfile-diff-from");
const hermesfileDiffTo = document.getElementById("hermesfile-diff-to");
const hermesfileCompare = document.getElementById("hermesfile-compare");
const hermesfileDiff = document.getElementById("hermesfile-diff");

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
let projectLoading = false;
let projectGeneration = 0;
let projectsLoaded = false;
let selectedProjectId = "";
let selectedProjectEtag = "";
let selectedProject = null;
let hermesfileLoading = false;
let hermesfileGeneration = 0;
let hermesfilesLoaded = false;
let selectedHermesfileId = "";
let selectedHermesfileEtag = "";
let selectedHermesfileRevision = 0;
let hermesfileValidated = false;

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
  const key = currentRoute().key;
  const dashboardRoute = key === "dashboard";
  const projectsRoute = key === "projects";
  const hermesfilesRoute = key === "hermesfiles";
  dashboardPanel.hidden = !dashboardRoute || !authenticated;
  projectPanel.hidden = !projectsRoute || !authenticated;
  hermesfilePanel.hidden = !hermesfilesRoute || !authenticated;
  routePanel.hidden = authenticated && (dashboardRoute || projectsRoute || hermesfilesRoute);
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
  if (route.key === "projects" && authenticated && !projectsLoaded) {
    void refreshProjects();
  }
  if (route.key === "hermesfiles" && authenticated && !hermesfilesLoaded) {
    void refreshHermesfiles();
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
  clearProjectState();
  clearHermesfileState();
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
  if (currentRoute().key === "projects") {
    void refreshProjects();
  }
  if (currentRoute().key === "hermesfiles") {
    void refreshHermesfiles();
  }
}

function showUnavailable(error) {
  authenticated = false;
  dashboardGeneration += 1;
  dashboardLoading = false;
  dashboardLoaded = false;
  dashboardRefresh.disabled = false;
  clearProjectState();
  clearHermesfileState();
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

function clearProjectState() {
  projectGeneration += 1;
  projectLoading = false;
  projectsLoaded = false;
  selectedProjectId = "";
  selectedProjectEtag = "";
  selectedProject = null;
  projectRefresh.disabled = false;
  projectCount.textContent = "0";
  projectAdminList.replaceChildren();
  projectDetailCard.hidden = true;
  projectCommandReason.value = "";
}

function projectErrorMessage(error, fallback) {
  const reference = error instanceof ControllerClientError && error.requestId
    ? ` Référence : ${error.requestId}.`
    : "";
  const title = error instanceof Error ? safeText(error.message, fallback, 160) : fallback;
  return `${title}${reference}`;
}

function setProjectBusy(busy) {
  projectLoading = busy;
  projectRefresh.disabled = busy;
  projectCreateSubmit.disabled = busy;
  projectUpdateSubmit.disabled = busy;
  projectCreateForm.querySelectorAll("input, select").forEach((control) => {
    control.disabled = busy;
  });
  projectUpdateForm.querySelectorAll("input").forEach((control) => {
    control.disabled = busy;
  });
  projectCommandButtons.querySelectorAll("button").forEach((button) => {
    button.disabled = busy;
  });
}

function renderProjectList(collection) {
  projectAdminList.replaceChildren();
  projectCount.textContent = String(collection.items.length);
  projectCoverage.textContent = collection.truncated
    ? "Une page suivante existe : la liste reste volontairement bornée."
    : "La première page reçue est complète selon les métadonnées Controller.";
  if (collection.items.length === 0) {
    appendEmpty(projectAdminList, "Aucun projet enregistré.");
    return;
  }
  for (const project of collection.items) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    const heading = document.createElement("strong");
    const detail = document.createElement("span");
    const state = document.createElement("span");
    const identifier = safeId(project, "projet");
    button.type = "button";
    button.dataset.projectId = identifier;
    button.className = "project-list-button";
    if (identifier === selectedProjectId) {
      button.setAttribute("aria-current", "true");
    }
    heading.textContent = safeText(project.name, identifier, 120);
    detail.textContent = `${identifier} · ${safeText(project.default_branch, "branche inconnue", 64)}`;
    state.className = "state-badge";
    state.dataset.state = safeState(project);
    state.textContent = safeState(project);
    button.append(heading, detail, state);
    item.append(button);
    projectAdminList.append(item);
  }
}

function renderProjectDetail(project, etag) {
  selectedProject = project;
  selectedProjectId = safeId(project, "");
  selectedProjectEtag = typeof etag === "string" ? etag : "";
  projectDetailCard.hidden = false;
  projectDetailTitle.textContent = safeText(project.name, selectedProjectId, 120);
  const state = safeState(project);
  projectDetailState.dataset.state = state;
  projectDetailState.textContent = state;
  projectDetailMeta.textContent = [
    `Identifiant ${selectedProjectId}`,
    `branche ${safeText(project.default_branch, "inconnue", 64)}`,
    `mode ${safeText(project.repository && project.repository.mode, "non renseigné", 32)}`,
    `révision ${Number.isInteger(project.resource_revision) ? project.resource_revision : "inconnue"}`,
  ].join(" · ");
  document.getElementById("project-update-name").value = safeText(project.name, "", 120);
  document.getElementById("project-update-policy").value = safeText(project.policy_id, "default", 63);
  document.getElementById("project-update-sandbox").value = typeof project.sandbox_profile_id === "string"
    ? safeText(project.sandbox_profile_id, "", 63)
    : "";
  projectCommandReason.value = "";
  projectCommandButtons.querySelectorAll("button[data-project-command]").forEach((button) => {
    const command = button.dataset.projectCommand;
    button.hidden = (command === "enable" && state === "enabled")
      || (command === "disable" && state !== "enabled")
      || (state === "archived" && command !== "rescan");
  });
}

async function selectProject(identifier) {
  if (!authenticated || projectLoading) {
    return;
  }
  setProjectBusy(true);
  projectStatus.textContent = `Lecture du projet ${safeText(identifier, "sélectionné", 63)}…`;
  try {
    const result = await client.project(identifier);
    renderProjectDetail(result.project, result.etag);
    projectStatus.textContent = "Détail projet chargé depuis le Controller.";
    const collection = await client.projects();
    renderProjectList(collection);
  } catch (error) {
    if (error instanceof ControllerClientError && error.status === 401) {
      showSignedOut("Session expirée. Reconnectez-vous pour administrer les projets.");
      return;
    }
    projectStatus.textContent = projectErrorMessage(error, "Lecture du projet impossible.");
  } finally {
    setProjectBusy(false);
  }
}

async function refreshProjects() {
  if (!authenticated || projectLoading) {
    return;
  }
  const generation = ++projectGeneration;
  setProjectBusy(true);
  projectStatus.textContent = "Lecture du registre projet…";
  try {
    const collection = await client.projects();
    if (generation !== projectGeneration || !authenticated) {
      return;
    }
    renderProjectList(collection);
    projectsLoaded = true;
    projectStatus.textContent = `${collection.items.length} projet(s) reçu(s) du Controller.`;
    if (selectedProjectId && collection.items.some((item) => safeId(item, "") === selectedProjectId)) {
      const result = await client.project(selectedProjectId);
      if (generation === projectGeneration && authenticated) {
        renderProjectDetail(result.project, result.etag);
      }
    } else {
      selectedProjectId = "";
      selectedProjectEtag = "";
      selectedProject = null;
      projectDetailCard.hidden = true;
    }
  } catch (error) {
    if (error instanceof ControllerClientError && error.status === 401) {
      showSignedOut("Session expirée. Reconnectez-vous pour administrer les projets.");
      return;
    }
    projectStatus.textContent = projectErrorMessage(error, "Registre projet indisponible.");
  } finally {
    if (generation === projectGeneration) {
      setProjectBusy(false);
    }
  }
}

async function runProjectMutation(label, operation) {
  if (!authenticated || projectLoading) {
    return;
  }
  setProjectBusy(true);
  projectStatus.textContent = `${label}…`;
  try {
    const accepted = await operation();
    const operationId = safeText(accepted.operation_id, "opération acceptée", 96);
    projectStatus.textContent = `${label} acceptée par le Controller · ${operationId}.`;
    projectsLoaded = false;
    setProjectBusy(false);
    await refreshProjects();
  } catch (error) {
    if (error instanceof ControllerClientError && error.status === 401) {
      showSignedOut("Session expirée. Reconnectez-vous avant toute nouvelle commande.");
      return;
    }
    projectStatus.textContent = projectErrorMessage(error, `${label} impossible.`);
  } finally {
    setProjectBusy(false);
  }
}

async function submitProjectCreate() {
  const mode = projectCreateMode.value;
  const sandbox = document.getElementById("project-create-sandbox").value.trim();
  const intent = {
    name: document.getElementById("project-create-name").value.trim(),
    slug: document.getElementById("project-create-slug").value.trim(),
    repository: {
      mode,
      default_branch: document.getElementById("project-create-branch").value.trim(),
      url: mode === "clone" ? projectCreateUrl.value.trim() : null,
    },
    policy_id: document.getElementById("project-create-policy").value.trim(),
    sandbox_profile_id: sandbox || null,
  };
  await runProjectMutation("Création du projet", () => client.createProject(intent));
  if (!projectLoading) {
    projectCreateForm.reset();
    projectCreateMode.value = "existing";
    document.getElementById("project-create-branch").value = "main";
    document.getElementById("project-create-policy").value = "default";
    projectCreateUrlLabel.hidden = true;
  }
}

function clearHermesfileState() {
  hermesfileGeneration += 1;
  hermesfileLoading = false;
  hermesfilesLoaded = false;
  selectedHermesfileId = "";
  selectedHermesfileEtag = "";
  selectedHermesfileRevision = 0;
  hermesfileValidated = false;
  hermesfileRefresh.disabled = false;
  hermesfileValidate.disabled = false;
  hermesfileSave.disabled = false;
  hermesfileCount.textContent = "0";
  hermesfileRevisionCount.textContent = "0";
  hermesfileList.replaceChildren();
  hermesfileRevisions.replaceChildren();
  hermesfileDiagnostics.replaceChildren();
  hermesfileDiffFrom.replaceChildren();
  hermesfileDiffTo.replaceChildren();
  hermesfileSource.value = "";
  hermesfilePreview.textContent = "Aucune prévisualisation.";
  hermesfileDiff.textContent = "Aucune comparaison.";
  hermesfileValidity.textContent = "non validé";
  hermesfileValidity.dataset.state = "unknown";
  hermesfileEditorMode.textContent = "nouveau";
  hermesfileEditorMode.dataset.state = "draft";
  hermesfileEditorTitle.textContent = "Éditeur Hermesfile";
  hermesfileMeta.textContent = "Chargez le modèle ou sélectionnez un profil.";
  hermesfileSave.textContent = "Créer";
}

function setHermesfileBusy(busy) {
  hermesfileLoading = busy;
  hermesfileRefresh.disabled = busy;
  hermesfileNew.disabled = busy;
  hermesfileValidate.disabled = busy;
  hermesfileSave.disabled = busy;
  hermesfileCompare.disabled = busy;
  hermesfileSource.disabled = busy;
}

function renderHermesfileList(collection) {
  hermesfileList.replaceChildren();
  hermesfileCount.textContent = String(collection.items.length);
  if (collection.items.length === 0) {
    appendEmpty(hermesfileList, "Aucun Hermesfile enregistré.");
    return;
  }
  for (const profile of collection.items) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    const heading = document.createElement("strong");
    const detail = document.createElement("span");
    const state = document.createElement("span");
    const identifier = safeId(profile, "");
    button.type = "button";
    button.dataset.hermesfileId = identifier;
    button.className = "project-list-button";
    if (identifier === selectedHermesfileId) {
      button.setAttribute("aria-current", "true");
    }
    heading.textContent = safeText(profile.name, safeText(profile.profile_name, identifier, 63), 120);
    detail.textContent = `${safeText(profile.profile_name, "profil", 63)} · révision ${Number.isInteger(profile.source_revision) ? profile.source_revision : "?"}`;
    state.className = "state-badge";
    state.dataset.state = safeState(profile);
    state.textContent = safeState(profile);
    button.append(heading, detail, state);
    item.append(button);
    hermesfileList.append(item);
  }
}

function renderHermesfileDiagnostics(preview) {
  hermesfileDiagnostics.replaceChildren();
  const diagnostics = Array.isArray(preview && preview.diagnostics) ? preview.diagnostics.slice(0, 100) : [];
  const valid = preview && preview.valid === true;
  hermesfileValidated = valid;
  hermesfileValidity.textContent = valid ? "valide" : "invalide";
  hermesfileValidity.dataset.state = valid ? "ready" : "failed";
  if (diagnostics.length === 0) {
    appendEmpty(hermesfileDiagnostics, valid ? "Aucun diagnostic bloquant." : "Aucun diagnostic disponible.");
  } else {
    for (const diagnostic of diagnostics) {
      appendOperationalItem(hermesfileDiagnostics, {
        label: safeText(diagnostic.severity, "diagnostic", 16),
        title: safeText(diagnostic.code, "validation", 128),
        state: safeText(diagnostic.severity, "unknown", 16).toLowerCase(),
        detail: `${safeText(diagnostic.path, "/", 256)} · ${safeText(diagnostic.message, "Diagnostic borné", 500)}`,
      });
    }
  }
  const projection = {
    canonical: preview && preview.canonical ? preview.canonical : null,
    runtime_config: preview && preview.runtime_config ? preview.runtime_config : null,
    source_sha256: preview && typeof preview.source_sha256 === "string" ? preview.source_sha256 : null,
    canonical_sha256: preview && typeof preview.canonical_sha256 === "string" ? preview.canonical_sha256 : null,
  };
  hermesfilePreview.textContent = JSON.stringify(projection, null, 2);
}

function renderHermesfileRevisions(collection) {
  const revisions = collection.items;
  hermesfileRevisions.replaceChildren();
  hermesfileDiffFrom.replaceChildren();
  hermesfileDiffTo.replaceChildren();
  hermesfileRevisionCount.textContent = String(revisions.length);
  if (revisions.length === 0) {
    appendEmpty(hermesfileRevisions, "Aucune révision disponible.");
    return;
  }
  for (const revision of revisions) {
    const number = Number(revision.source_revision);
    const item = document.createElement("li");
    const button = document.createElement("button");
    const heading = document.createElement("strong");
    const detail = document.createElement("span");
    button.type = "button";
    button.dataset.hermesfileRevision = String(number);
    button.className = "project-list-button";
    heading.textContent = `Révision ${number}`;
    detail.textContent = `${safeText(revision.canonical_sha256, "empreinte inconnue", 64).slice(0, 16)}… · ${safeText(revision.created_at, "date inconnue", 40)}`;
    button.append(heading, detail);
    item.append(button);
    hermesfileRevisions.append(item);
    for (const select of [hermesfileDiffFrom, hermesfileDiffTo]) {
      const option = document.createElement("option");
      option.value = String(number);
      option.textContent = `Révision ${number}`;
      select.append(option);
    }
  }
  if (revisions.length > 1) {
    hermesfileDiffFrom.value = String(revisions[revisions.length - 1].source_revision);
    hermesfileDiffTo.value = String(revisions[0].source_revision);
  }
}

async function loadHermesfile(identifier) {
  if (!authenticated || hermesfileLoading) {
    return;
  }
  setHermesfileBusy(true);
  hermesfileStatus.textContent = "Lecture du Hermesfile sélectionné…";
  try {
    const result = await client.hermesfile(identifier);
    const current = result.hermesfile;
    const profile = current.profile || {};
    const revision = current.revision || {};
    selectedHermesfileId = safeId(profile, "");
    selectedHermesfileEtag = result.etag;
    selectedHermesfileRevision = Number.isInteger(profile.source_revision) ? profile.source_revision : 0;
    hermesfileSource.value = typeof revision.source === "string" ? revision.source : "";
    hermesfileEditorTitle.textContent = safeText(profile.name, safeText(profile.profile_name, "Hermesfile", 63), 120);
    hermesfileEditorMode.textContent = "édition";
    hermesfileEditorMode.dataset.state = safeState(profile);
    hermesfileMeta.textContent = `${selectedHermesfileId} · révision source ${selectedHermesfileRevision} · révision ressource ${Number.isInteger(profile.resource_revision) ? profile.resource_revision : "?"}`;
    hermesfileSave.textContent = "Créer une nouvelle révision";
    renderHermesfileDiagnostics({
      valid: true,
      diagnostics: revision.diagnostics || [],
      canonical: revision.canonical || null,
      runtime_config: revision.runtime_config || null,
      source_sha256: revision.source_sha256 || null,
      canonical_sha256: revision.canonical_sha256 || null,
    });
    const revisions = await client.hermesfileRevisions(selectedHermesfileId);
    renderHermesfileRevisions(revisions);
    const collection = await client.hermesfiles();
    renderHermesfileList(collection);
    hermesfileStatus.textContent = "Hermesfile et historique chargés depuis le Controller.";
  } catch (error) {
    if (error instanceof ControllerClientError && error.status === 401) {
      showSignedOut("Session expirée. Reconnectez-vous pour administrer les Hermesfiles.");
      return;
    }
    hermesfileStatus.textContent = projectErrorMessage(error, "Lecture du Hermesfile impossible.");
  } finally {
    setHermesfileBusy(false);
  }
}

async function refreshHermesfiles() {
  if (!authenticated || hermesfileLoading) {
    return;
  }
  const generation = ++hermesfileGeneration;
  setHermesfileBusy(true);
  hermesfileStatus.textContent = "Lecture des Hermesfiles…";
  try {
    const collection = await client.hermesfiles();
    if (generation !== hermesfileGeneration || !authenticated) {
      return;
    }
    renderHermesfileList(collection);
    hermesfilesLoaded = true;
    hermesfileStatus.textContent = `${collection.items.length} Hermesfile(s) reçu(s) du Controller.`;
    if (selectedHermesfileId && collection.items.some((item) => safeId(item, "") === selectedHermesfileId)) {
      setHermesfileBusy(false);
      await loadHermesfile(selectedHermesfileId);
    }
  } catch (error) {
    if (error instanceof ControllerClientError && error.status === 401) {
      showSignedOut("Session expirée. Reconnectez-vous pour administrer les Hermesfiles.");
      return;
    }
    hermesfileStatus.textContent = projectErrorMessage(error, "Registre Hermesfile indisponible.");
  } finally {
    if (generation === hermesfileGeneration) {
      setHermesfileBusy(false);
    }
  }
}

async function loadHermesfileTemplate() {
  if (!authenticated || hermesfileLoading) {
    return;
  }
  setHermesfileBusy(true);
  try {
    const template = await client.hermesfileTemplate();
    selectedHermesfileId = "";
    selectedHermesfileEtag = "";
    selectedHermesfileRevision = 0;
    hermesfileSource.value = typeof template.source === "string" ? template.source : "";
    hermesfileEditorTitle.textContent = "Nouveau Hermesfile";
    hermesfileEditorMode.textContent = "nouveau";
    hermesfileEditorMode.dataset.state = "draft";
    hermesfileMeta.textContent = "Modèle officiel chargé. La création reste séparée de la validation.";
    hermesfileSave.textContent = "Créer";
    hermesfileDiagnostics.replaceChildren();
    appendEmpty(hermesfileDiagnostics, "Validez la source avant de la créer.");
    hermesfilePreview.textContent = "Aucune prévisualisation.";
    hermesfileRevisions.replaceChildren();
    hermesfileDiffFrom.replaceChildren();
    hermesfileDiffTo.replaceChildren();
    hermesfileRevisionCount.textContent = "0";
    hermesfileDiff.textContent = "Aucune comparaison.";
    hermesfileValidated = false;
    hermesfileValidity.textContent = "non validé";
    hermesfileValidity.dataset.state = "unknown";
    hermesfileStatus.textContent = "Modèle Hermesfile chargé depuis le Controller.";
  } catch (error) {
    hermesfileStatus.textContent = projectErrorMessage(error, "Modèle Hermesfile indisponible.");
  } finally {
    setHermesfileBusy(false);
  }
}

async function validateHermesfileEditor() {
  if (!authenticated || hermesfileLoading) {
    return;
  }
  setHermesfileBusy(true);
  hermesfileStatus.textContent = "Validation stricte du Hermesfile…";
  try {
    const preview = await client.validateHermesfile(hermesfileSource.value);
    renderHermesfileDiagnostics(preview);
    hermesfileStatus.textContent = preview.valid
      ? "Hermesfile valide. La configuration canonique et runtime est prévisualisée."
      : "Hermesfile invalide. Corrigez les diagnostics avant persistance.";
  } catch (error) {
    hermesfileValidated = false;
    hermesfileStatus.textContent = projectErrorMessage(error, "Validation Hermesfile impossible.");
  } finally {
    setHermesfileBusy(false);
  }
}

async function saveHermesfileEditor() {
  if (!authenticated || hermesfileLoading) {
    return;
  }
  if (!hermesfileValidated) {
    hermesfileStatus.textContent = "Validez la source avant de la persister.";
    return;
  }
  setHermesfileBusy(true);
  hermesfileStatus.textContent = selectedHermesfileId ? "Création d’une nouvelle révision…" : "Création du Hermesfile…";
  try {
    const operation = selectedHermesfileId
      ? await client.updateHermesfile(selectedHermesfileId, selectedHermesfileEtag, hermesfileSource.value)
      : await client.createHermesfile(hermesfileSource.value);
    const target = operation && operation.result && typeof operation.result.sandbox_id === "string"
      ? operation.result.sandbox_id
      : selectedHermesfileId;
    hermesfileStatus.textContent = `Opération ${safeText(operation.id, "acceptée", 96)} terminée.`;
    hermesfilesLoaded = false;
    setHermesfileBusy(false);
    if (target) {
      await loadHermesfile(target);
    } else {
      await refreshHermesfiles();
    }
  } catch (error) {
    if (error instanceof ControllerClientError && error.status === 401) {
      showSignedOut("Session expirée. Reconnectez-vous avant toute persistance Hermesfile.");
      return;
    }
    hermesfileStatus.textContent = projectErrorMessage(error, "Persistance Hermesfile impossible.");
  } finally {
    setHermesfileBusy(false);
  }
}

async function loadHistoricalRevision(revision) {
  if (!selectedHermesfileId || hermesfileLoading) {
    return;
  }
  setHermesfileBusy(true);
  try {
    const historical = await client.hermesfileRevision(selectedHermesfileId, revision);
    hermesfileSource.value = typeof historical.source === "string" ? historical.source : "";
    renderHermesfileDiagnostics({
      valid: true,
      diagnostics: historical.diagnostics || [],
      canonical: historical.canonical || null,
      runtime_config: historical.runtime_config || null,
      source_sha256: historical.source_sha256 || null,
      canonical_sha256: historical.canonical_sha256 || null,
    });
    hermesfileMeta.textContent = `Révision historique ${revision} chargée en lecture. Enregistrer créera une nouvelle révision depuis l’ETag courant.`;
    hermesfileStatus.textContent = `Révision ${revision} chargée.`;
  } catch (error) {
    hermesfileStatus.textContent = projectErrorMessage(error, "Révision Hermesfile indisponible.");
  } finally {
    setHermesfileBusy(false);
  }
}

async function compareHermesfileHistory() {
  if (!selectedHermesfileId || hermesfileLoading) {
    return;
  }
  const fromRevision = Number(hermesfileDiffFrom.value);
  const toRevision = Number(hermesfileDiffTo.value);
  if (!Number.isInteger(fromRevision) || !Number.isInteger(toRevision) || fromRevision === toRevision) {
    hermesfileStatus.textContent = "Choisissez deux révisions différentes.";
    return;
  }
  setHermesfileBusy(true);
  try {
    const comparison = await client.compareHermesfileRevisions(selectedHermesfileId, fromRevision, toRevision);
    hermesfileDiff.textContent = JSON.stringify(comparison, null, 2);
    hermesfileStatus.textContent = `${Array.isArray(comparison.changes) ? comparison.changes.length : 0} chemin(s) canonique(s) modifié(s).`;
  } catch (error) {
    hermesfileStatus.textContent = projectErrorMessage(error, "Comparaison Hermesfile impossible.");
  } finally {
    setHermesfileBusy(false);
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

projectRefresh.addEventListener("click", () => {
  projectsLoaded = false;
  void refreshProjects();
});

projectCreateMode.addEventListener("change", () => {
  const clone = projectCreateMode.value === "clone";
  projectCreateUrlLabel.hidden = !clone;
  projectCreateUrl.required = clone;
  if (!clone) {
    projectCreateUrl.value = "";
  }
});

projectCreateForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void submitProjectCreate();
});

projectAdminList.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-project-id]");
  if (button) {
    void selectProject(button.dataset.projectId || "");
  }
});

projectUpdateForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!selectedProjectId || !selectedProjectEtag) {
    projectStatus.textContent = "Sélectionnez un projet avant de modifier ses métadonnées.";
    return;
  }
  const sandbox = document.getElementById("project-update-sandbox").value.trim();
  const changes = {
    name: document.getElementById("project-update-name").value.trim(),
    policy_id: document.getElementById("project-update-policy").value.trim(),
    sandbox_profile_id: sandbox || null,
  };
  void runProjectMutation(
    "Mise à jour du projet",
    () => client.updateProject(selectedProjectId, selectedProjectEtag, changes),
  );
});

projectCommandButtons.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-project-command]");
  if (!button || !selectedProjectId || !selectedProjectEtag) {
    return;
  }
  const command = button.dataset.projectCommand || "";
  if (command === "archive") {
    const accepted = globalThis.confirm(
      `Archiver ${selectedProjectId} désactive définitivement son usage opérationnel. Continuer ?`,
    );
    if (!accepted) {
      projectStatus.textContent = "Archivage annulé avant envoi au Controller.";
      return;
    }
  }
  const labels = {
    enable: "Activation du projet",
    disable: "Désactivation du projet",
    rescan: "Rescan du dépôt",
    archive: "Archivage du projet",
  };
  const reason = projectCommandReason.value.trim() || null;
  void runProjectMutation(
    labels[command] || "Commande projet",
    () => client.commandProject(selectedProjectId, command, selectedProjectEtag, reason),
  );
});

hermesfileRefresh.addEventListener("click", () => {
  hermesfilesLoaded = false;
  void refreshHermesfiles();
});

hermesfileNew.addEventListener("click", () => {
  void loadHermesfileTemplate();
});

hermesfileList.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-hermesfile-id]");
  if (button) {
    void loadHermesfile(button.dataset.hermesfileId || "");
  }
});

hermesfileRevisions.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-hermesfile-revision]");
  if (button) {
    void loadHistoricalRevision(Number(button.dataset.hermesfileRevision));
  }
});

hermesfileValidate.addEventListener("click", () => {
  void validateHermesfileEditor();
});

hermesfileSave.addEventListener("click", () => {
  void saveHermesfileEditor();
});

hermesfileCompare.addEventListener("click", () => {
  void compareHermesfileHistory();
});

hermesfileSource.addEventListener("input", () => {
  hermesfileValidated = false;
  hermesfileValidity.textContent = "à revalider";
  hermesfileValidity.dataset.state = "unknown";
});

window.addEventListener("popstate", () => render(window.location.pathname));
render(window.location.pathname);
refreshSession();
