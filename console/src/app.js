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

window.addEventListener("popstate", () => render(window.location.pathname));
render(window.location.pathname);
