// The wiring: which view is on screen, and getting its record from api.js to
// render.js. This is the only file that does both, which is what a composition
// root is for.
//
// Routing is in the fragment rather than the path because the portal is static
// files behind a file server. A path route would need a rewrite in Caddy, and
// reloading a deep link without one answers 404, which is the failure a
// volunteer hits first and understands last.

"use strict";

const sections = Array.from(document.querySelectorAll("[data-source]"));
const navigation = Array.from(document.querySelectorAll("[data-nav]"));
const alreadyRead = new Set();

function sectionFor(route) {
  return sections.find((section) => section.dataset.route === route);
}

async function load(section) {
  if (alreadyRead.has(section.id)) {
    return;
  }
  render.showLoading(section);
  const answer = await api.read(section.dataset.source);
  if (answer.outcome === "ok") {
    if (Array.isArray(answer.data)) {
      render.showList(section, answer.data);
    } else {
      render.showRecord(section, answer.data);
    }
    alreadyRead.add(section.id);
    return;
  }
  // Nothing is added to alreadyRead on a refusal or a silence, so moving away
  // and back asks again. A member whose first look landed while the API was
  // restarting should not have to reload the whole portal.
  if (answer.outcome === "refused") {
    render.showProblem(section, answer.problem);
  } else {
    render.showSilence(section);
  }
}

function mark(current) {
  for (const link of navigation) {
    if (link.dataset.nav === current.dataset.route) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  }
}

function show(route, moveFocus) {
  const wanted = sectionFor(route) || sections[0];
  for (const section of sections) {
    section.hidden = section !== wanted;
  }
  mark(wanted);
  if (moveFocus) {
    // The document did not change, so a screen reader is not told anything
    // happened unless focus goes to the new heading.
    wanted.querySelector("h2").focus();
  }
  load(wanted);
}

function routeInAddress() {
  return window.location.hash.replace(/^#/, "");
}

window.addEventListener("hashchange", () => show(routeInAddress(), true));

show(routeInAddress(), false);
