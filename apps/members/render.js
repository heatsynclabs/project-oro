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
  // The four rules card eligibility is decided on, as words a member would
  // use. The enum is closed by the CardEligibility schema in
  // docs/api/members-v1.yaml, so an unmapped value is a contract change and
  // shows through rather than being swallowed.
  requirement: (value) => ({
    tier: "Membership tier",
    tenure: "How long you have been a member",
    standing: "Standing",
    waiver: "Waiver",
  }[value] || value),
  // What a member chose to show, in the words the directory page uses, so the
  // same setting reads the same wherever it appears.
  visibility: (value) => (value ? "Visible to members" : "Hidden"),
  state: (value) => (value ? "Active" : "Not active"),
};

function present(value, format, fallback) {
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
function markChip(element, value) {
  if (!("chip" in element.dataset)) {
    return;
  }
  element.dataset.state = value === true ? "on" : "off";
}

function bindFields(root, record) {
  for (const element of root.querySelectorAll("[data-field]")) {
    const value = readPath(record, element.dataset.field);
    element.textContent = present(
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

function showFromTemplate(section, templateId, problem) {
  const parts = clear(section);
  const template = document.getElementById(templateId);
  const block = template.content.cloneNode(true);
  if (problem) {
    bindFields(block, problem);
  }
  parts.error.appendChild(block);
  parts.error.hidden = false;
  parts.status.textContent = "";
}

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
  showFromTemplate(section, "api-problem", problem);
}

function showSilence(section) {
  showFromTemplate(section, "api-unreachable", null);
}

function showLoading(section) {
  const parts = clear(section);
  parts.status.textContent = section.dataset.loading;
}

const render = {
  showRecord: showRecord,
  showList: showList,
  showProblem: showProblem,
  showSilence: showSilence,
  showLoading: showLoading,
  present: present,
  readPath: readPath,
};
