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
    // A paged endpoint answers with the page rather than with the list, so the
    // section names which property of it holds the items.
    const held = section.dataset.listIn
      ? answer.data[section.dataset.listIn]
      : answer.data;
    if (Array.isArray(held)) {
      render.showList(section, held);
    } else {
      render.showRecord(section, held);
      profile.fill(section, held);
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
    chrome.showWho("signed-out", "");
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
//
// Named apart from api.claimMemberRecord deliberately. These are classic
// scripts sharing one global scope, so two files declaring one name pick a
// winner by load order, which README.md records happening once already.
async function writeFirstSignIn(control) {
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

// A member changing their own record. api.js does the fetching and profile.js
// draws the form, so the two meet here.
async function sendProfileChanges() {
  profile.showSaving();
  const answer = await api.saveProfile(profile.changes());
  if (answer.outcome === "ok") {
    // The API answers with the record it saved, so the cards above the form and
    // the boxes inside it are both redrawn from what the lab now holds. The
    // confirmed chip beside the email address is the one that moves on a save.
    render.showRecord(profile.section, answer.data);
    profile.fill(profile.section, answer.data);
    profile.showSaved();
  } else if (answer.outcome === "refused") {
    profile.showSaveProblem(answer.problem);
  } else if (answer.outcome === "signed-out") {
    chrome.showWho("signed-out", "");
    render.showSignedOut(profile.section);
  } else {
    profile.showSaveSilence();
  }
}

document.addEventListener("submit", (event) => {
  if (!("profileForm" in event.target.dataset)) {
    return;
  }
  // Left alone, the browser navigates to this page with the fields in the query
  // string, which loses the tokens the tab is holding and shows nobody a
  // refusal.
  event.preventDefault();
  sendProfileChanges();
});

// One listener for the whole page rather than one per control, because the sign
// in button inside a view is cloned out of a template long after this runs.
document.addEventListener("click", (event) => {
  const control = event.target.closest(
    "[data-sign-in], [data-join], [data-sign-out], [data-claim-member]");
  if (!control) {
    return;
  }
  if ("signIn" in control.dataset) {
    identity.startSignIn();
  } else if ("join" in control.dataset) {
    identity.startJoin();
  } else if ("signOut" in control.dataset) {
    identity.signOut();
  } else {
    writeFirstSignIn(control);
  }
});

window.addEventListener("hashchange", () => show(routeInAddress(), true));

// Signing in comes first, because a code arriving in the address has to be
// exchanged before any view asks for a token, and because the chrome saying
// nobody is signed in while somebody is would be a lie in the first thing a
// reader looks at.
async function start() {
  const state = await identity.begin();
  chrome.showWho(state, "");
  chrome.showSigningIn(
    state === "signed-in" || state === "signed-out" ? "" : state);
  // Started rather than awaited: the views can load while the identity service
  // is asked who this is, and the chip carries a name the moment it answers.
  if (state === "signed-in") {
    identity.whoIsSignedIn().then((who) => {
      person = who;
      chrome.showWho(state, who.name);
    });
  }
  api.whatAnswers().then((behind) => chrome.showBehindTheApi(behind));
  if (state === "signed-in") {
    chrome.showTheViews();
    show(routeInAddress(), false);
  } else {
    // Every view here is about the reader's own things, and somebody who has
    // never been here has none. Seven tabs each saying "sign in to read this"
    // is a locked door with seven handles, so they get one page with the two
    // things they can actually do.
    chrome.showTheLanding();
  }
}

start();
