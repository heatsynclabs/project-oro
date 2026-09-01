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

// http and https only, and checked here rather than taken on trust. The rule is
// social_urls_are_http in db/migrations/001_schema.sql and this page is a
// courtesy, so a value that arrives some other way still must not reach an href:
// a javascript: URL in one runs when a member clicks it.
function isHttpUrl(value) {
  return typeof value === "string"
    && (value.startsWith("http://") || value.startsWith("https://"));
}

function bindFields(root, record) {
  for (const element of root.querySelectorAll("[data-field]")) {
    const value = readPath(record, element.dataset.field);
    const text = formatted(
      value,
      element.dataset.format,
      element.dataset.fallback
    );
    // data-link is opt in. A member who typed their website in expects to be
    // able to open it, and until 2026-08-31 every one of them was printed as
    // text somebody had to select and paste.
    if ("link" in element.dataset && isHttpUrl(value)) {
      const anchor = document.createElement("a");
      anchor.href = value;
      anchor.textContent = text;
      // Somebody else's page. It does not get told where the reader came from.
      anchor.rel = "noreferrer";
      element.replaceChildren(anchor);
    } else {
      element.textContent = text;
    }
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
    // A list inside a card has no section of its own, so the data-empty a whole
    // view uses does not reach it. Without this the Roles card rendered a
    // heading over nothing for every member who holds no role, which is most of
    // them, unlike every other view here.
    const empty = section.querySelector('[data-empty-for="' + name + '"]');
    if (empty) {
      empty.hidden = items.length > 0;
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

// What the live region says once a view has something in it.
//
// A sighted member never sees this line: members.css clips it to a pixel. A
// screen reader reads it out on every view change, so it is the one status
// line in the portal that some members cannot skip, and it used to say
// "Your cards, loaded." to exactly those members. A live region should say
// what changed. So a list says how many things are in it and a record says
// nothing at all, because show() moves focus to the heading and the heading
// is what gets read.
function announce(section, parts, count) {
  const one = section.dataset.one;
  if (!one) { parts.status.textContent = ""; return; }
  const many = section.dataset.many;
  if (count === 0) { parts.status.textContent = "No " + many + "."; return; }
  parts.status.textContent = count === 1 ? "1 " + one + "." : count + " " + many + ".";
}

function showRecord(section, record) {
  const parts = clear(section);
  bindFields(parts.target, record);
  bindLists(section, parts.target, record);
  parts.target.hidden = false;
  announce(section, parts, null);
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
  announce(section, parts, items.length);
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


// What a view shows before its request answers, and what it shows when nothing
// answered at all. Both are about one view, so both stayed here when chrome.js
// took the page around them.
function showLoading(section) {
  const parts = clear(section);
  parts.status.textContent = section.dataset.loading;
}


function showSilence(section) {
  showFromTemplate(section, "api-unreachable", null);
}


const render = {
  showRecord: showRecord,
  showList: showList,
  showProblem: showProblem,
  showSignedOut: showSignedOut,
  showSilence: showSilence,
  showLoading: showLoading,
  fillFromTemplate: fillFromTemplate,
  formatted: formatted,
  readPath: readPath,
};
