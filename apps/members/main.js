// The wiring: who is signed in, which view is on screen, and getting a record
// from api.js to render.js. This is the only file that both fetches and
// renders, which is what a composition root is for.
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
  present(section, await api.read(section.dataset.source));
}

function present(section, answer) {
  if (answer.outcome === "ok") {
    if (Array.isArray(answer.data)) {
      render.showList(section, answer.data);
    } else {
      render.showRecord(section, answer.data);
    }
    alreadyRead.add(section.id);
    return;
  }
  // Nothing is added to alreadyRead unless a record came back, so moving away
  // and back asks again. A member whose first look landed while the API was
  // restarting should not have to reload the whole portal, and one who signs in
  // should not have to either.
  if (answer.outcome === "refused") {
    render.showProblem(section, answer.problem);
  } else if (answer.outcome === "signed-out") {
    // The chrome as well as the view, because a session that ended part way
    // leaves the app bar naming somebody who is no longer signed in.
    render.showWho("signed-out", "");
    render.showSignedOut(section);
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

// Who the identity service says is reading, kept because two things need it:
// the chip in the app bar, and the name and address a first sign in sends.
let person = { name: "", email: "" };

// A first sign in. The API refused every view with the same refusal, so all of
// them are asked again rather than only the one the button was in.
async function claimMemberRecord(control) {
  const section = control.closest("[data-source]");
  render.showLoading(section);
  const answer = await api.claimMemberRecord(person);
  if (answer.outcome !== "ok") {
    present(section, answer);
    return;
  }
  alreadyRead.clear();
  show(routeInAddress(), true);
}

// One listener for the whole page rather than one per control, because the sign
// in button inside a view is cloned out of a template long after this runs.
document.addEventListener("click", (event) => {
  const control = event.target.closest(
    "[data-sign-in], [data-sign-out], [data-claim-member]");
  if (!control) {
    return;
  }
  if ("signIn" in control.dataset) {
    identity.startSignIn();
  } else if ("signOut" in control.dataset) {
    identity.signOut();
  } else {
    claimMemberRecord(control);
  }
});

window.addEventListener("hashchange", () => show(routeInAddress(), true));

// Signing in comes first, because a code arriving in the address has to be
// exchanged before any view asks for a token, and because the chrome saying
// nobody is signed in while somebody is would be a lie in the first thing a
// reader looks at.
async function start() {
  const state = await identity.begin();
  render.showWho(state, "");
  render.showSigningIn(
    state === "signed-in" || state === "signed-out" ? "" : state);
  // Started rather than awaited: the views can load while the identity service
  // is asked who this is, and the chip carries a name the moment it answers.
  if (state === "signed-in") {
    identity.whoIsSignedIn().then((who) => {
      person = who;
      render.showWho(state, who.name);
    });
  }
  api.whatAnswers().then((behind) => render.showBehindTheApi(behind));
  show(routeInAddress(), false);
}

start();
