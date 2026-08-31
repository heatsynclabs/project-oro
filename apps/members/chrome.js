// The page around the views: who is signed in, the band under the masthead, and
// which of the portal's two shapes is on screen.
//
// Split out of render.js, which reached the 300 line ceiling in rule 6. The
// boundary is the one that file already drew with a divider: render.js puts a
// record on a screen, and this decides what the screen is. Neither fetches,
// per rule 5.
//
// A plain script like every other file here, so it loads before render.js and
// main.js in index.html and reaches nothing they define.

"use strict";

// Which chip and which controls each state gets. Every sentence in them is in
// index.html; a member's name is data rather than copy, so it comes from here.
function showWho(state, name) {
  const signedIn = state === "signed-in";
  for (const chip of document.querySelectorAll("[data-who]")) {
    chip.hidden = chip.dataset.who !== (signedIn ? "signed-in" : "signed-out");
  }
  if (signedIn && name) {
    document.querySelector("[data-name]").textContent = name;
  }
  // The app bar's own control only. The landing carries its own pair and is
  // shown or hidden as a page rather than a control at a time.
  for (const control of document.querySelectorAll(".appbar [data-sign-in]")) {
    control.hidden = state !== "signed-out";
  }
  document.querySelector("[data-sign-out]").hidden = !signedIn;
}

// The band under the masthead answers two questions and they are independent:
// what is behind the members API, and whether signing in can work on this
// origin at all. Each group holds one sentence per answer and shows one of
// them, or none when the group has nothing to say.
function pickOne(attribute, wanted) {
  for (const element of document.querySelectorAll("[" + attribute + "]")) {
    element.hidden = element.getAttribute(attribute) !== wanted;
  }
}

// There is no sentence for "service", and that is the point. A member does not
// need to be told there is an API behind their own record, and a caution band
// on a page where nothing is wrong trains people to ignore the band on the day
// it says something real. The mock and the unanswered case still have one,
// because both mean what is on the screen is not what the lab holds.
function showBehindTheApi(which) {
  pickOne("data-behind", which);
  quietTheBandIfNothingIsLeft();
}

function showSigningIn(which) {
  pickOne("data-signing-in", which);
}

// The two shapes this page has. Signed in it is a set of views with a nav above
// them. Signed out it is one page with a way in, because every view is about the
// reader's own things and somebody who has never been here has none.
function showTheLanding() {
  const landing = document.querySelector("[data-landing]");
  document.querySelector(".views").hidden = true;
  for (const section of document.querySelectorAll("[data-source]")) {
    section.hidden = true;
  }
  // What is behind the members API is a true thing to say about records, and
  // there are none on this page. The band stays for the sentences that are
  // about signing in, because those are the reason somebody is still here.
  for (const line of document.querySelectorAll("[data-behind]")) {
    line.hidden = true;
  }
  quietTheBandIfNothingIsLeft();
  landing.hidden = false;
  landing.querySelector("h2").focus();
}

function quietTheBandIfNothingIsLeft() {
  const band = document.querySelector(".notice");
  const showing = Array.from(band.querySelectorAll("p")).some((p) => !p.hidden);
  band.hidden = !showing;
}

function showTheViews() {
  document.querySelector(".views").hidden = false;
  quietTheBandIfNothingIsLeft();
  document.querySelector("[data-landing]").hidden = true;
}

const chrome = {
  showWho: showWho,
  showBehindTheApi: showBehindTheApi,
  showSigningIn: showSigningIn,
  showTheLanding: showTheLanding,
  showTheViews: showTheViews,
  quietTheBandIfNothingIsLeft: quietTheBandIfNothingIsLeft,
};
