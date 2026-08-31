// Fetching. This file knows the members API and knows nothing about the DOM,
// per rule 5 of CLAUDE.md: fetching does not render.
//
// Every path is relative, so the portal calls the same origin it was served
// from. Caddy strips /v1 and proxies to the contract mock today, and proxies to
// services/api when that is wired in. Neither this file nor any page names a
// host.
//
// The access token comes from identity.js, which is the only file that holds
// one. It is asked for on every call rather than read once, because a token
// lasts ten minutes and a member reading their record for longer than that
// should not be thrown out. Asking for it is what renews it.

"use strict";

const BASE = "/v1";

// A token no identity service issued, sent deliberately, once, to find out what
// is behind /v1. Anything that answers 200 to it is checking no tokens, and the
// only thing on this origin that does that is the contract mock. The page says
// what this measured rather than claiming either one.
const A_TOKEN_NOTHING_ISSUED = "not a token any identity service issued";

// Both media types on every call. A refusal is served as
// application/problem+json, and asking only for application/json gets a 406
// instead of the sentence the contract wrote for the reader.
const ACCEPTED = "application/json, application/problem+json";

// What a call gives back. One shape for the four outcomes, so a caller reads
// the outcome rather than catching an exception to find out what happened.
//   ok          the record, in data
//   refused     the API answered with an RFC 9457 problem detail, in problem
//   signed-out  nobody is signed in, so nothing was asked
//   silent      nothing answered, or the answer was not the API's
function ok(data) {
  return { outcome: "ok", data: data, problem: null };
}

function refused(problem) {
  return { outcome: "refused", data: null, problem: problem };
}

function signedOut() {
  return { outcome: "signed-out", data: null, problem: null };
}

function silent(reason) {
  return { outcome: "silent", data: null, problem: null, reason: reason };
}

async function send(path, method, token, asked) {
  const request = { method: method, headers: {
    "Authorization": "Bearer " + token,
    "Accept": ACCEPTED,
  } };
  if (asked) {
    request.headers["Content-Type"] = "application/json";
    request.body = JSON.stringify(asked);
  }
  let answer;
  try {
    answer = await fetch(BASE + path, request);
  } catch (unreachable) {
    return silent(unreachable.message);
  }

  let body = null;
  try {
    body = await answer.json();
  } catch (notJson) {
    // Caddy answers its own 404 as text when a route is missing, so a page that
    // assumed JSON here would report a parse failure and hide the real one,
    // which is that nothing is proxying /v1.
    if (answer.ok) {
      return silent("the answer was not JSON");
    }
    return silent("HTTP " + answer.status + ", and the body was not JSON");
  }
  return answer.ok ? ok(body) : refused(body);
}

async function read(path) {
  const token = await identity.accessToken();
  if (!token) {
    return signedOut();
  }
  return send(path, "GET", token);
}

// The one thing this portal writes. A member whose sign in has no member record
// behind it can write one, and nothing else on this page changes anything.
//
// The body is what the FirstSignIn schema in docs/api/members-v1.yaml declares,
// read there on 2026-08-30: a name, an optional address, and nothing else
// accepted. Both come from the identity service rather than from a field on
// this page, because the person just proved who they are to it and typing a
// name again is work with no reader.
//
// The address is sent rather than left out. members.email is unique, so a
// legacy member whose record the lab already holds is refused by the database
// and told an admin joins them to it, where sending no address would quietly
// write them a second, empty record.
async function claimMemberRecord(person) {
  const token = await identity.accessToken();
  if (!token) {
    return signedOut();
  }
  const asked = { name: person.name };
  if (person.email) {
    asked.email = person.email;
  }
  return send("/me", "POST", token, asked);
}

// What is behind /v1, measured rather than assumed, so the page can stop saying
// "the contract mock" on the day that stops being true without anybody
// remembering to edit a sentence.
async function whatAnswers() {
  const answer = await send("/me", "GET", A_TOKEN_NOTHING_ISSUED);
  if (answer.outcome === "ok") {
    return "mock";
  }
  if (answer.outcome === "refused") {
    return "service";
  }
  // Nothing answered, so the page goes on saying it does not know rather than
  // picking one. Caddy with no /v1 route looks exactly like this.
  return "unknown";
}

// One entry point for reading rather than six named wrappers. Each view section
// in index.html declares the path it reads, so a second list of them here would
// be a second place to keep right.
const api = {
  read: read,
  claimMemberRecord: claimMemberRecord,
  whatAnswers: whatAnswers,
};
