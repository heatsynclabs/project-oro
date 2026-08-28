"""Signing in the way a member does, with no browser.

The hosted screens are not driven here. What is driven is the protocol
underneath them: an authorization request, a session that has already passed a
password check, and the exchange that turns the two into tokens. That is the
same code path the screens use, and it is the only way to reach a refresh token
from a script.

Separate from api.py because that file is calls to the management API and this
is one flow through the OIDC endpoints, and together they were over the file
ceiling in rule 6.
"""
from __future__ import annotations

import base64
import hashlib
import http.cookiejar
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request

from api import BASE, Answer, post_form

# Three screens today. The bound is loose enough that adding one does not
# break this and tight enough that a screen returning itself fails rather than
# hangs.
SCREEN_LIMIT = 8


class _LocalhostCookies(http.cookiejar.DefaultCookiePolicy):
    """Keep cookies for a host with no dot in its name.

    The default policy refuses them, and "localhost" has no dot. Without this
    the login screens answer 200 and render an internal error, because the
    authorization request is bound to a user agent cookie that was never kept.
    A check written without it reports a working sign in as broken. Measured
    both ways on 2026-08-28.
    """

    def set_ok_domain(self, cookie, request) -> bool:
        return True

    def return_ok_domain(self, cookie, request) -> bool:
        return True


def browser(redirects=None) -> urllib.request.OpenerDirector:
    """An opener that keeps cookies and follows redirects, as a browser does.

    A redirect handler is passed in at build time rather than added afterwards.
    Adding one leaves the default in place beside it and the default answers
    first, which is how an earlier version of this followed the redirect back
    to a portal nothing was serving and reported a completed sign in as a
    connection error.
    """
    jar = http.cookiejar.CookieJar(_LocalhostCookies())
    handlers = [urllib.request.HTTPCookieProcessor(jar)]
    if redirects is not None:
        handlers.append(redirects)
    return urllib.request.build_opener(*handlers)


def fetch_page(path: str, opener=None) -> tuple[int, str]:
    opener = opener or browser()
    try:
        with opener.open(BASE + path) as answer:
            return answer.status, answer.read().decode(errors="replace")
    except urllib.error.HTTPError as refused:
        return refused.code, refused.read().decode(errors="replace")


def sign_in_through_the_screens(client_id: str, origin: str,
                                login: str, password: str) -> Answer:
    """Sign a member in the way a member does, through the hosted screens.

    Nothing about the number of screens or their addresses is written down
    here. Each page is read, the field it asks for is answered if this function
    knows the answer, and anything it merely offers is skipped. So a screen
    added or reordered still passes, and a check does not turn red over a path
    that moved. Today that is three screens: the login name, the password, and
    a prompt to set up a second factor.
    """
    catcher = _CatchCallback(origin)
    opener = browser(catcher)
    verifier = base64.urlsafe_b64encode(os.urandom(40)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    status, page = fetch_page(_authorize_path(client_id, origin, challenge), opener)
    if status != 200:
        raise AssertionError(f"the sign in page answered {status}")

    # Bounded, because a screen that keeps returning itself is a loop and the
    # failure a reader needs to see is which screen, not a hung suite.
    for _ in range(SCREEN_LIMIT):
        if catcher.code:
            break
        page = _submit(opener, page, _answer_for(page, login, password))
    if not catcher.code:
        raise AssertionError(
            f"the screens did not reach a code within {SCREEN_LIMIT} steps")
    return post_form("/oauth/v2/token", {
        "grant_type": "authorization_code", "code": catcher.code,
        "redirect_uri": origin + "/", "client_id": client_id,
        "code_verifier": verifier})


def _answer_for(page: str, login: str, password: str) -> dict:
    """What to put into the screen in front of us.

    A screen that asks for something we hold gets it. A screen that asks for
    anything else is skipped, which is what the second factor prompt is: an
    offer rather than a requirement, and MFA is deliberately later per
    docs/plan/order-of-operations.md.
    """
    # A password field first, and by its type rather than by its name. The
    # password screen carries the login name as a hidden field too, so matching
    # on names alone answers the password screen with a login name and the same
    # screen comes back for as long as the loop is allowed to run.
    if re.search(r'<input[^>]*type="password"', page):
        return {"password": password}
    if re.search(r'<input[^>]*name="loginName"', page):
        return {"loginName": login}
    return {"skip": "true"}


class _CatchCallback(urllib.request.HTTPRedirectHandler):
    """Stop at the redirect back to the portal and keep the code out of it.

    Nothing is listening on that origin during a check, so following it would
    turn a completed sign in into a connection error.
    """

    def __init__(self, origin: str):
        self.origin = origin
        self.code = ""

    # noqa: PLR0913 is not ours to fix. This signature is
    # urllib.request.HTTPRedirectHandler's, and narrowing it would mean the
    # standard library calls a method that does not accept what it passes.
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # noqa: PLR0913
        if newurl.startswith(self.origin):
            found = urllib.parse.parse_qs(urllib.parse.urlparse(newurl).query)
            self.code = found.get("code", [""])[0]
            return None
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _submit(opener, page: str, answers: dict) -> str:
    """Post the form on this page, keeping every hidden field it carries.

    The hidden fields are the cross site token and the authorization request
    id. Dropping either turns a working sign in into an internal error.
    """
    action = re.search(r'<form[^>]*action="([^"]+)"', page)
    if not action:
        raise AssertionError("the page in front of us carries no form")
    fields = dict(re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', page))
    fields.update(answers)
    try:
        with opener.open(BASE + action.group(1),
                         urllib.parse.urlencode(fields).encode()) as answer:
            return answer.read().decode(errors="replace")
    except urllib.error.HTTPError as refused:
        return refused.read().decode(errors="replace")


def _authorize_path(client_id: str, origin: str, challenge: str) -> str:
    return "/oauth/v2/authorize?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": origin + "/",
        "response_type": "code", "scope": "openid profile offline_access",
        "code_challenge": challenge, "code_challenge_method": "S256"})


def sign_in_page(client_id: str, origin: str) -> tuple[int, str]:
    query = urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": origin + "/",
        "response_type": "code", "scope": "openid",
        "code_challenge": secrets.token_urlsafe(32), "code_challenge_method": "S256"})
    return fetch_page("/oauth/v2/authorize?" + query)
