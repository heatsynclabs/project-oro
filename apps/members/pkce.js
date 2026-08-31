// The PKCE half of the authorization code flow, and the one check that says
// whether this browser can do it at all.
//
// Its own file because identity.js reached the 300 line ceiling in rule 6 and
// this is the part of it that knows no OIDC: it is bytes, a digest and base64.

"use strict";

function base64url(bytes) {
  let text = "";
  for (const byte of bytes) {
    text += String.fromCharCode(byte);
  }
  return window.btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function randomText() {
  const bytes = new Uint8Array(32);
  window.crypto.getRandomValues(bytes);
  return base64url(bytes);
}

async function challengeFor(verifier) {
  const digest = await window.crypto.subtle.digest(
    "SHA-256", new TextEncoder().encode(verifier));
  return base64url(new Uint8Array(digest));
}

// crypto.subtle exists only where the browser calls the origin secure, which
// means HTTPS or localhost. A laptop serving plain HTTP under any other
// hostname cannot build the challenge at all, and a member deserves that
// sentence rather than a button that does nothing.
function canBuildAChallenge() {
  return Boolean(window.crypto && window.crypto.subtle);
}
