// Fetching. This file knows the members API and knows nothing about the DOM,
// per rule 5 of CLAUDE.md: fetching does not render.
//
// Every path is relative, so the portal calls the same origin it was served
// from. Caddy strips /v1 and proxies to the contract mock today, and proxies to
// services/api when that exists. Neither this file nor any page names a host.

"use strict";

// There is no identity service, so there is no access token to carry. The
// contract mock accepts any bearer token and validates no signature, which is
// what lets the portal be finished before the service exists. Phase 2 replaces
// this with an authorization code flow against the identity provider.
const CONTRACT_MOCK_TOKEN = "no-identity-service-yet";

const BASE = "/v1";

// What a call gives back. One shape for the three outcomes, so a caller reads
// the outcome rather than catching an exception to find out what happened.
//   ok       the record, in data
//   refused  the API answered with an RFC 9457 problem detail, in problem
//   silent   nothing answered, or the answer was not the API's
function ok(data) {
  return { outcome: "ok", data: data, problem: null };
}

function refused(problem) {
  return { outcome: "refused", data: null, problem: problem };
}

function silent(reason) {
  return { outcome: "silent", data: null, problem: null, reason: reason };
}

async function read(path) {
  let answer;
  try {
    answer = await fetch(BASE + path, {
      headers: {
        "Authorization": "Bearer " + CONTRACT_MOCK_TOKEN,
        // Both media types. A refusal is served as application/problem+json,
        // and asking only for application/json gets a 406 instead of the
        // sentence the contract wrote for the reader.
        "Accept": "application/json, application/problem+json",
      },
    });
  } catch (unreachable) {
    return silent(unreachable.message);
  }

  let body = null;
  try {
    body = await answer.json();
  } catch (notJson) {
    // Caddy answers its own 404 as text when a route is missing, so a page
    // that assumed JSON here would report a parse failure and hide the real
    // one, which is that nothing is proxying /v1.
    if (answer.ok) {
      return silent("the answer was not JSON");
    }
    return silent("HTTP " + answer.status + ", and the body was not JSON");
  }

  if (answer.ok) {
    return ok(body);
  }
  return refused(body);
}

// One entry point rather than six named wrappers. Each view section in
// index.html declares the path it reads, so a second list of them here would be
// a second place to keep right.
const api = {
  token: CONTRACT_MOCK_TOKEN,
  read: read,
};
