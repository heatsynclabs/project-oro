// What the browser holds between one request and the next: the tokens, and the
// half finished sign in a member is in the middle of. Nothing here calls the
// network and nothing here touches the DOM. identity.js is the file that talks
// to the identity service, and it is the only caller of this one.
//
// sessionStorage rather than localStorage, and the choice costs something
// either way.
//
// What it buys: the tokens belong to one browser tab and are gone when that tab
// closes. The lab has machines in it that several members use, and a token that
// outlives the person who signed in is the thing that matters there.
//
// What it costs: anything that can run JavaScript on this origin can read them.
// A script injected into this page could take the access token and the refresh
// token and use them from somewhere else until the refresh token is next
// rotated, which is at most ten minutes of reading plus however long the refresh
// token lasts. Keeping the access token in a variable and nothing on disk would
// narrow that and would sign a member out on every reload, which is the thing
// this portal is being changed to stop doing. What keeps the exposure small is
// that this page loads no third party script and fetches nothing from another
// origin. apps/members/README.md carries the same paragraph where a person
// deciding this is likely to look for it.

"use strict";

const TOKENS = "oro.members.tokens";
const IN_PROGRESS = "oro.members.signing-in";

// An access token lasts ten minutes, read off a real one in
// tools/identity/tests/check_identity.py. Renewing a minute before it expires
// means a member reading down a long page is not thrown out between one view
// and the next, and a minute is wide enough for a slow connection to finish.
const RENEW_WITH_SECONDS_LEFT = 60;

function held(key) {
  try {
    return JSON.parse(window.sessionStorage.getItem(key));
  } catch (unreadable) {
    // A browser told to refuse storage throws on the read rather than answering
    // null, and a member with that setting should meet a signed out portal
    // rather than a broken one.
    return null;
  }
}

function keep(key, value) {
  try {
    window.sessionStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch (refused) {
    return false;
  }
}

function drop(key) {
  try {
    window.sessionStorage.removeItem(key);
  } catch (refused) {
    return;
  }
}

function tokens() {
  return held(TOKENS);
}

// What the token endpoint answered, kept in the shape the rest of this portal
// reads. expires_in is seconds from now, and now is what the browser thinks it
// is: a machine whose clock is wrong renews early or late by the size of the
// error, and the identity service is the one that decides either way.
function remember(answer) {
  if (!answer || !answer.access_token) {
    return false;
  }
  return keep(TOKENS, {
    access: answer.access_token,
    refresh: answer.refresh_token || null,
    identity: answer.id_token || null,
    expiresAt: Date.now() + (Number(answer.expires_in) || 0) * 1000,
  });
}

function forgetTokens() {
  drop(TOKENS);
}

function signedIn() {
  return Boolean(tokens());
}

function needsRenewal() {
  const current = tokens();
  return Boolean(current) && current.expiresAt - Date.now() <= RENEW_WITH_SECONDS_LEFT * 1000;
}

// The verifier and the state, kept only while the browser is away at the
// identity service, plus the view the member was reading. The redirect back
// carries a query string and no fragment, so without this a sign in from the
// cards view lands on the record view.
function rememberSignInStart(start) {
  return keep(IN_PROGRESS, start);
}

function takeSignInStart() {
  const start = held(IN_PROGRESS);
  drop(IN_PROGRESS);
  return start;
}

const session = {
  tokens: tokens,
  remember: remember,
  forgetTokens: forgetTokens,
  signedIn: signedIn,
  needsRenewal: needsRenewal,
  rememberSignInStart: rememberSignInStart,
  takeSignInStart: takeSignInStart,
};
