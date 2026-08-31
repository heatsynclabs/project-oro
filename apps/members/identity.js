// Signing in. This file talks to the identity service and never touches the
// DOM, which is the split api.js already keeps: fetching does not render. It
// does send the browser somewhere, which is not the same as drawing on a page.
//
// Authorization code with PKCE, against the client
// tools/identity/configure.py registers as "Members portal". That client is
// public and holds no secret, because a secret shipped inside a page a browser
// downloads is not a secret. PKCE stands in for one.
//
// tools/identity/flow.py drives these same endpoints from Python and carries
// what was learned about the hosted screens. Nothing here drives a screen: the
// browser goes to the identity service, a person answers there, and the browser
// comes back to this origin with a code in the query string.
//
// session.js holds what comes back. This file is the only caller of it.

"use strict";

// Zitadel generates a client id per instance, so this page cannot carry one and
// nobody can copy one out of the repository. tools/identity/configure.py writes
// this document into the portal directory, which Caddy serves, and that is the
// only way the value gets here.
const CONFIGURATION_PATH = "/identity.json";

let configuration = null;
let endpoints = null;
let renewal = null;

// ---------------------------------------------- what this page has been told

async function readConfiguration() {
  let document_ = null;
  try {
    const answer = await fetch(CONFIGURATION_PATH, {
      headers: { "Accept": "application/json" },
    });
    document_ = answer.ok ? await answer.json() : null;
  } catch (unreadable) {
    return "unconfigured";
  }
  if (!document_ || !document_.issuer || !document_.client_id) {
    return "unconfigured";
  }
  if (document_.redirect_uri !== window.location.origin + "/") {
    // The identity service sends a browser back to the address the client was
    // registered with and to no other. Registered against a different origin, a
    // member lands on a page that is not this one, holding a code this page
    // never sees, and the failure reads as the sign in silently doing nothing.
    return "wrong-origin";
  }
  configuration = document_;
  return "ok";
}

// Every path this file calls is read out of the identity service's own
// discovery document rather than written down here, so a path that moves in a
// later Zitadel is followed rather than guessed.
async function readEndpoints() {
  if (endpoints) {
    return true;
  }
  try {
    const answer = await fetch(configuration.issuer + "/.well-known/openid-configuration");
    if (!answer.ok) {
      return false;
    }
    endpoints = await answer.json();
    return true;
  } catch (unreachable) {
    return false;
  }
}

// ------------------------------------------------------ out, and back again

async function startSignIn(prompt) {
  if (!configuration || !canBuildAChallenge() || !(await readEndpoints())) {
    return false;
  }
  const verifier = randomText();
  const state = randomText();
  session.rememberSignInStart({
    verifier: verifier, state: state, returnTo: window.location.hash,
  });
  const query = new URLSearchParams({
    client_id: configuration.client_id,
    redirect_uri: configuration.redirect_uri,
    response_type: "code",
    // offline_access is what asks for a refresh token. Without it the session
    // ends ten minutes later with nothing to renew it from.
    scope: "openid profile email offline_access",
    state: state,
    // Ask who is signing in, every time. Without it a member is taken straight
    // into whoever used this browser last. README.md carries the measurement.
    prompt: prompt || "select_account",
    code_challenge: await challengeFor(verifier),
    code_challenge_method: "S256",
  });
  window.location.assign(endpoints.authorization_endpoint + "?" + query.toString());
  return true;
}

function codeInAddress() {
  return new URLSearchParams(window.location.search).get("code") || "";
}

// The code is single use, so it comes out of the address before anything can
// reload the page onto it. The fragment goes back to whichever view the member
// was reading, which the redirect drops on the way through.
function tidyTheAddress(returnTo) {
  window.history.replaceState(
    null, "", window.location.pathname + (returnTo || window.location.hash));
}

async function finishSignIn() {
  const arrived = new URLSearchParams(window.location.search);
  const started = session.takeSignInStart();
  if (!started || arrived.get("state") !== started.state) {
    // A code with no start behind it, or one whose state does not match, is not
    // this tab's sign in. Nothing is exchanged.
    tidyTheAddress(started ? started.returnTo : "");
    return false;
  }
  const answer = await tokenRequest({
    grant_type: "authorization_code",
    code: arrived.get("code"),
    redirect_uri: configuration.redirect_uri,
    client_id: configuration.client_id,
    code_verifier: started.verifier,
  });
  tidyTheAddress(started.returnTo);
  return session.remember(answer);
}

async function tokenRequest(form) {
  if (!(await readEndpoints())) {
    return null;
  }
  try {
    const answer = await fetch(endpoints.token_endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(form).toString(),
    });
    return answer.ok ? await answer.json() : null;
  } catch (unreachable) {
    return null;
  }
}

// ---------------------------------------------------------- keeping it alive

// The refresh token rotates: spending one invalidates it and hands back
// another, which tools/identity/tests proves. Two views renewing at the same
// moment would spend the same token twice and the second would be refused, so
// every caller waits on the one renewal already running.
function renew() {
  if (renewal) {
    return renewal;
  }
  const tokens = session.tokens();
  if (!tokens || !tokens.refresh) {
    return Promise.resolve(null);
  }
  renewal = tokenRequest({
    grant_type: "refresh_token",
    refresh_token: tokens.refresh,
    client_id: configuration.client_id,
  }).then((answer) => {
    renewal = null;
    if (!session.remember(answer)) {
      // The refresh token was refused, so this session is over. Forgetting it
      // is what turns the next call into a signed out page rather than a run of
      // refusals a member cannot act on.
      session.forgetTokens();
      return null;
    }
    return session.tokens().access;
  });
  return renewal;
}

async function accessToken() {
  const tokens = session.tokens();
  // No configuration means no client id to renew against, so a session left in
  // this tab from before cannot be kept alive and the page says signed out
  // rather than showing records under a chip that names nobody.
  if (!tokens || !configuration) {
    return null;
  }
  return session.needsRenewal() ? renew() : tokens.access;
}

// Who this is, from the identity service rather than from reading the token,
// because a token this page has not verified is not something to put a person's
// name on screen from. Two callers and two uses: the chip in the app bar shows
// the name, and a first sign in sends both to POST /me.
const NOBODY = { name: "", email: "" };

async function whoIsSignedIn() {
  const token = await accessToken();
  if (!token || !(await readEndpoints())) {
    return NOBODY;
  }
  try {
    const answer = await fetch(endpoints.userinfo_endpoint, {
      headers: { "Authorization": "Bearer " + token },
    });
    if (!answer.ok) {
      return NOBODY;
    }
    const person = await answer.json();
    return {
      name: person.name || person.preferred_username || person.email || "",
      email: person.email || "",
    };
  } catch (unreachable) {
    return NOBODY;
  }
}

// Dropping the tokens here and leaving the session standing at the identity
// service would mean the next person at this machine signs in with one click
// and no password. So the browser is sent there to end it as well.
async function signOut() {
  const tokens = session.tokens();
  session.forgetTokens();
  if (!tokens || !configuration || !(await readEndpoints())) {
    window.location.assign("/");
    return;
  }
  const query = new URLSearchParams({
    post_logout_redirect_uri: configuration.redirect_uri,
    client_id: configuration.client_id,
  });
  if (tokens.identity) {
    query.set("id_token_hint", tokens.identity);
  }
  window.location.assign(endpoints.end_session_endpoint + "?" + query.toString());
}

// One call for main.js to make before anything else reads anything: take the
// configuration, finish a sign in that is arriving, and answer with the state
// the chrome has a sentence for.
async function begin() {
  const read = await readConfiguration();
  if (read !== "ok") {
    return read;
  }
  if (!canBuildAChallenge()) {
    return "insecure-origin";
  }
  if (codeInAddress() && !(await finishSignIn())) {
    // A code came back and this page could not turn it into a session. That is
    // worth a sentence: signed out with no explanation reads as the button
    // having done nothing.
    return "sign-in-failed";
  }
  return session.signedIn() ? "signed-in" : "signed-out";
}

const identity = {
  begin: begin,
  startSignIn: startSignIn,
  // Joining is the same request with prompt=create, which opens
  // Registration rather than the account chooser. README.md has why.
  startJoin: function () { return startSignIn("create"); },
  signOut: signOut,
  signedIn: session.signedIn,
  accessToken: accessToken,
  whoIsSignedIn: whoIsSignedIn,
};
