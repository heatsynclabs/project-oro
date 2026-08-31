// The profile form: fill it from a record, read it back into a request body,
// and say what happened when it saved. This file writes to the DOM and never
// calls the network, which is the split render.js already keeps.
//
// No field is named here. Each one is an element in index.html carrying
// data-edit, named after the property it sends, and
// tools/members-portal/tests/check_profile.py holds every one of those names
// against MemberSelfUpdate in docs/api/members-v1.yaml. A field invented in
// this file would be refused by the API and caught by that check.
//
// The two sentences this shows are attributes on the form, for the same reason
// every view carries data-loading and data-loaded: a check with no browser can
// read the copy where it cannot run the code.

"use strict";

const profileForm = document.querySelector("[data-profile-form]");
// The view the form sits in, read from the page rather than written down, so
// main.js can hand it a record without a route name living in two files.
const profileSection = profileForm
  ? profileForm.closest("[data-source]") : null;

function editableFields() {
  return Array.from(profileForm.querySelectorAll("[data-edit]"));
}

function saveParts() {
  return {
    said: profileForm.querySelector("[data-save-status]"),
    error: profileForm.querySelector("[data-save-error]"),
  };
}

// ------------------------------------------------ the record, in and out

function fillProfileForm(section, record) {
  if (!profileForm || section !== profileSection || !record) {
    return;
  }
  for (const field of editableFields()) {
    const value = record[field.dataset.edit];
    if (field.type === "checkbox") {
      field.checked = value === true;
    } else {
      field.value = value === null || value === undefined ? "" : String(value);
    }
  }
  clearFieldProblems();
}

// Every field the form offers, on every save, rather than only the ones that
// changed. PATCH applies a partial update either way, and a diff kept here
// would be a second opinion about what the record already says.
function profileChanges() {
  const asked = {};
  for (const field of editableFields()) {
    if (field.type === "checkbox") {
      asked[field.dataset.edit] = field.checked;
      continue;
    }
    // An emptied box means the member wants nothing there. Every one of these
    // takes null in the contract except the name, and the browser refuses to
    // submit that one empty.
    const typed = field.value.trim();
    asked[field.dataset.edit] = typed === "" ? null : typed;
  }
  return asked;
}

// ------------------------------------------- a refusal that names one field

// One line under one field, made when a refusal names it and taken away when
// the next save clears it. The sentence is the API's rather than this page's.
function problemLine(field) {
  const standing = field.parentElement.querySelector(".field-problem");
  if (standing) {
    return standing;
  }
  const line = document.createElement("span");
  line.className = "field-problem";
  line.id = field.id + "-problem";
  field.parentElement.appendChild(line);
  return line;
}

function markFieldProblem(named) {
  const field = profileForm.querySelector(
    '[data-edit="' + named.field + '"]');
  if (!field) {
    return;
  }
  const line = problemLine(field);
  line.textContent = named.detail;
  field.setAttribute("aria-invalid", "true");
  // Tied to the field rather than left loose on the page, so a screen reader
  // reads the problem out with the box it is about.
  field.setAttribute("aria-describedby", line.id);
}

function clearFieldProblems() {
  for (const field of editableFields()) {
    field.removeAttribute("aria-invalid");
    field.removeAttribute("aria-describedby");
  }
  for (const line of profileForm.querySelectorAll(".field-problem")) {
    line.remove();
  }
}

// ----------------------------------------------------- what happened to it

function showSaving() {
  clearFieldProblems();
  const parts = saveParts();
  parts.said.textContent = profileForm.dataset.saving;
  parts.error.replaceChildren();
  parts.error.hidden = true;
}

function showSaved() {
  const parts = saveParts();
  parts.said.textContent = profileForm.dataset.saved;
  parts.error.replaceChildren();
  parts.error.hidden = true;
}

// The block every other refusal on this page gets, plus a line under each field
// the API named, because a member looking at a form needs to know which box.
function showSaveProblem(problem) {
  const parts = saveParts();
  parts.said.textContent = "";
  render.fillFromTemplate(parts.error, "api-problem", problem);
  for (const named of (problem && problem.errors) || []) {
    markFieldProblem(named);
  }
}

function showSaveSilence() {
  const parts = saveParts();
  parts.said.textContent = "";
  render.fillFromTemplate(parts.error, "api-unreachable", null);
}

const profile = {
  section: profileSection,
  fill: fillProfileForm,
  changes: profileChanges,
  showSaving: showSaving,
  showSaved: showSaved,
  showSaveProblem: showSaveProblem,
  showSaveSilence: showSaveSilence,
};
