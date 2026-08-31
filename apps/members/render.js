// Presentation. This file writes to the DOM and never calls the network, per
// rule 5 of CLAUDE.md: presentation does not fetch.
//
// The page carries its own bindings. An element with data-field names a path
// into the record the section reads, a template with data-item-for names a list
// inside that record, and every sentence a reader sees is in index.html rather
// than in here. That is what lets tools/members-portal/tests/check_portal.py
// assert, with no browser, that every field the page shows is a field the
// contract serves.

"use strict";

function readPath(record, dotted) {
  let value = record;
  for (const part of dotted.split(".")) {
    if (value === null || typeof value !== "object" || !(part in value)) {
      return undefined;
    }
    value = value[part];
  }
  return value;
}

// Dates are shown as the API sends them, trimmed to the day or the minute. A
// locale format would read differently on each volunteer's machine, and a date
// on a card record is the kind of thing two people compare over the phone.
const formats = {
  date: (value) => String(value).slice(0, 10),
  datetime: (value) => String(value).slice(0, 10) + " at " + String(value).slice(11, 16),
  // The API masks a tag number to its last four characters before it sends one.
  // Taking the last four again is the same answer, so a mock that serves the
  // whole number, as the contract's own example does, still never puts a full
  // card number on a screen somebody can read over a shoulder.
  last4: (value) => "Ending " + String(value).slice(-4).toUpperCase(),
  yesno: (value) => (value ? "Yes" : "No"),
  // A confirmed address is a signal and never a gate. The member record exists
  // and works either way, so this reports what the lab knows rather than what
  // the member is allowed to do. data-model.md section 1.6 is the reason the
  // date can be absent: changing your own email clears it, and you cannot set
  // it yourself.
  confirmed: () => "Email confirmed",
  // What a member chose to show, in the words the directory page uses, so the
  // same setting reads the same wherever it appears.
  visibility: (value) => (value ? "Visible to members" : "Hidden"),
  state: (value) => (value ? "Active" : "Not active"),
};

function formatted(value, format, fallback) {
  if (value === null || value === undefined || value === "") {
    // An empty string fallback is a real choice: a note line with nothing to
    // say collapses rather than reading "Not recorded" under every row title.
    return fallback === undefined ? "Not recorded" : fallback;
  }
  if (format && formats[format]) {
    return formats[format](value);
  }
  return String(value);
}

// A chip is filled when what it reports is true and outlined when it is not,
// so a member reading down a column sees the shape before they read the word.
// Only a field that is genuinely a yes or a no carries one, which is why the
// rule is the raw value rather than the text it was formatted into.
//
// data-chip="present" is the second rule and it exists for one shape: a column
// that holds a date or nothing, where having the date is the yes. An email
// confirmation is that shape. Keeping it as a named rule rather than making the
// first one truthy means a field that is genuinely a boolean still cannot be
// filled in by an empty string or a zero.
function markChip(element, value) {
  if (!("chip" in element.dataset)) {
    return;
  }
  const filled = element.dataset.chip === "present"
    ? value !== null && value !== undefined && value !== ""
    : value === true;
  element.dataset.state = filled ? "on" : "off";
}

function bindFields(root, record) {
  for (const element of root.querySelectorAll("[data-field]")) {
    const value = readPath(record, element.dataset.field);
    element.textContent = formatted(
      value,
      element.dataset.format,
      element.dataset.fallback
    );
    markChip(element, value);
  }
}

function bindLists(section, root, record) {
  for (const holder of root.querySelectorAll("[data-list]")) {
    const name = holder.dataset.list;
    const template = section.querySelector('[data-item-for="' + name + '"]');
    const items = readPath(record, name);
    holder.replaceChildren();
    if (!template || !Array.isArray(items)) {
      continue;
    }
    for (const item of items) {
      const row = template.content.cloneNode(true);
      bindFields(row, item);
      holder.appendChild(row);
    }
  }
}

function partsOf(section) {
  return {
    status: section.querySelector("[data-status]"),
    target: section.querySelector("[data-target]"),
    empty: section.querySelector("[data-empty]"),
    error: section.querySelector("[data-error]"),
  };
}

function clear(section) {
  const parts = partsOf(section);
  parts.error.replaceChildren();
  parts.error.hidden = true;
  parts.target.hidden = true;
  if (parts.empty) { parts.empty.hidden = true; }
  return parts;
}

function showRecord(section, record) {
  const parts = clear(section);
  bindFields(parts.target, record);
  bindLists(section, parts.target, record);
  parts.target.hidden = false;
  parts.status.textContent = section.dataset.loaded;
}

function showList(section, items) {
  const parts = clear(section);
  const template = section.querySelector("[data-item]");
  parts.target.replaceChildren();
  for (const item of items) {
    const row = template.content.cloneNode(true);
    bindFields(row, item);
    bindLists(section, row, item);
    parts.target.appendChild(row);
  }
  if (items.length === 0 && parts.empty) {
    parts.empty.hidden = false;
  } else {
    parts.target.hidden = false;
  }
  parts.status.textContent = section.dataset.loaded;
}

// A block cloned out of the page and shown wherever it was asked for. The
// section's own error region is one caller and the profile form's is the other,
// because a refusal on a save must not take the form off the screen with the
// half the member had just typed into it.
function fillFromTemplate(into, templateId, problem) {
  const template = document.getElementById(templateId);
  const block = template.content.cloneNode(true);
  if (problem) {
    bindFields(block, problem);
  }
  into.replaceChildren(block);
  into.hidden = false;
}

function showFromTemplate(section, templateId, problem) {
  const parts = clear(section);
  fillFromTemplate(parts.error, templateId, problem);
  parts.status.textContent = "";
}

// The one refusal a member can act on. services/api/app/problems.py names it
// no-member-record: the sign in is real and no member row is joined to it, so
// the block for it carries the button that creates one. Keyed on the slug at
// the end of the type rather than on the status, because the status is 401 and
// so is every other way of not being signed in.
const NO_MEMBER_RECORD = "/no-member-record";

// A refusal the contract expects is not a fault. GET /me/waiver answers 404
// when nobody has recorded a waiver, and the reader needs that sentence rather
// than an error block. The section says which status means that.
function showProblem(section, problem) {
  if (section.dataset.emptyOn === String(problem.status)) {
    const parts = clear(section);
    parts.empty.hidden = false;
    parts.status.textContent = "";
    return;
  }
  if (String(problem.type || "").endsWith(NO_MEMBER_RECORD)) {
    showFromTemplate(section, "api-no-member-record", problem);
    return;
  }
  showFromTemplate(section, "api-problem", problem);
}


function showSignedOut(section) {
  showFromTemplate(section, "not-signed-in", null);
}


// ---------------------------------------------------------------- the chrome

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

function showBehindTheApi(which) {
  pickOne("data-behind", which);
}

function showSigningIn(which) {
  pickOne("data-signing-in", which);
}

function showSilence(section) {
  showFromTemplate(section, "api-unreachable", null);
}

function showLoading(section) {
  const parts = clear(section);
  parts.status.textContent = section.dataset.loading;
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
  document.querySelector(".notice").hidden = false;
  document.querySelector("[data-landing]").hidden = true;
}

const render = {
  showTheLanding: showTheLanding,
  showTheViews: showTheViews,
  showRecord: showRecord,
  showList: showList,
  showProblem: showProblem,
  showSignedOut: showSignedOut,
  showWho: showWho,
  showBehindTheApi: showBehindTheApi,
  showSigningIn: showSigningIn,
  showSilence: showSilence,
  showLoading: showLoading,
  fillFromTemplate: fillFromTemplate,
  formatted: formatted,
  readPath: readPath,
};
