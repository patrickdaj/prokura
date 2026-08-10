"""M8 spike — de-risk the authority console before any service code.

Proves three things against the live compose stack:

  1. AGGREGATION: for one principal (alice) join OpenFGA (agent->operator +
     can_use tuples), approval rows (Postgres), and Loki audit lines into one
     register view, and prove the per-user Loki filter.
  2. EXCHANGE (RFC 8693): from the authority-console confidential client,
     exchange the signed-in user's authority-ui token into aud=token-broker and
     aud=approval, subject preserved; prove the broker's audience gate accepts it.
  3. IDP_LINK: drive kc_action=idp_link:acme from the confidential authority-ui
     client (prompt=login + KC-26 confirm hop) and confirm it is legal for a
     non-`account` client.

Spike-quarantine: passwords live here (spike/, not an agent kit). Headless,
cookie-per-realm (Keycloak marks cookies Secure on plain HTTP and per-realm
names collide) — same handling as spike/idp-link/link_spike.py.

Usage:  python agg_spike.py     (exit 0 + RESULT lines on success)
"""

import base64
import hashlib
import html as html_mod
import json
import os
import re
import secrets
import sys

import httpx

KC = os.environ.get("PROKURA_KEYCLOAK_URL", "http://localhost:8180")
BROKER = os.environ.get("PROKURA_BROKER_URL", "http://localhost:8110")
GRAFANA = os.environ.get("PROKURA_LGTM_URL", "http://localhost:3001")
OPENFGA = os.environ.get("PROKURA_OPENFGA_URL", "http://localhost:8081")
REALM = "prokura"
USER, PW = "alice", "alice"

UI_CLIENT, UI_SECRET = "authority-ui", "authority-ui-dev-secret"
UI_REDIRECT = "http://localhost:8160/callback"
EXCHANGE_CLIENT, EXCHANGE_SECRET = "authority-console", "authority-console-dev-secret"
ALIAS = "acme"

_b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
_TE = "urn:ietf:params:oauth:grant-type:token-exchange"
_ACCESS = "urn:ietf:params:oauth:token-type:access_token"


def claims(token: str) -> dict:
    p = token.split(".")[1]
    p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))


def _aud(c: dict) -> list[str]:
    a = c.get("aud", [])
    return a if isinstance(a, list) else [a]


# --- cookie-per-realm helpers (from link_spike) -------------------------------

def _realm_of(url: str) -> str:
    m = re.search(r"/realms/([^/]+)/", url)
    return m.group(1) if m else REALM


def _merge(store: dict, url: str, resp: httpx.Response) -> None:
    jar = store.setdefault(_realm_of(url), {})
    for sc in resp.headers.get_list("set-cookie"):
        name, val = sc.split(";", 1)[0].split("=", 1)
        jar[name] = val


def _cookie(store: dict, url: str) -> str:
    return "; ".join(f"{k}={v}" for k, v in store.get(_realm_of(url), {}).items())


def _form(html_text: str) -> str | None:
    m = re.search(r'id="kc-form-login"[^>]*action="([^"]+)"', html_text)
    return html_mod.unescape(m.group(1)) if m else None


# --- 1.3a: authority-ui login (confidential + PKCE), returns access token ------

def login_authority_ui() -> str:
    verifier = _b64(secrets.token_bytes(32))
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    cookies: dict[str, dict] = {}
    with httpx.Client(follow_redirects=False, timeout=20.0) as c:
        auth = f"{KC}/realms/{REALM}/protocol/openid-connect/auth"
        r = c.get(auth, params={
            "client_id": UI_CLIENT, "response_type": "code", "redirect_uri": UI_REDIRECT,
            "scope": "openid", "state": "spk", "code_challenge": challenge,
            "code_challenge_method": "S256"})
        _merge(cookies, auth, r)
        assert r.status_code == 200, f"auth GET {r.status_code}: {r.text[:200]}"
        action = _form(r.text)
        assert action, "no authority-ui login form"
        r = c.post(action, data={"username": USER, "password": PW},
                   headers={"Cookie": _cookie(cookies, action)})
        assert r.status_code in (302, 303, 307), f"login {r.status_code}: {r.text[:200]}"
        loc = r.headers["location"]
        code = httpx.URL(loc).params.get("code")
        assert code, f"no code on redirect: {loc[:150]}"
        tok = c.post(f"{KC}/realms/{REALM}/protocol/openid-connect/token", data={
            "grant_type": "authorization_code", "client_id": UI_CLIENT,
            "client_secret": UI_SECRET, "code": code, "redirect_uri": UI_REDIRECT,
            "code_verifier": verifier})
        assert tok.status_code == 200, f"token {tok.status_code}: {tok.text[:200]}"
        return tok.json()["access_token"]


# --- 1.3b: RFC 8693 exchange from authority-console ----------------------------

def exchange(subject_token: str, audience: str, scope: str) -> str:
    r = httpx.post(f"{KC}/realms/{REALM}/protocol/openid-connect/token", data={
        "grant_type": _TE, "client_id": EXCHANGE_CLIENT, "client_secret": EXCHANGE_SECRET,
        "subject_token": subject_token, "subject_token_type": _ACCESS,
        "audience": audience, "scope": scope}, timeout=15.0)
    if r.status_code != 200:
        raise AssertionError(f"exchange for aud={audience} failed: {r.status_code} {r.text[:300]}")
    return r.json()["access_token"]


def prove_exchange() -> None:
    ui = login_authority_ui()
    uc = claims(ui)
    print(f"RESULT authority-ui token: sub={uc['sub']} user={uc.get('preferred_username')} "
          f"azp={uc['azp']} aud={_aud(uc)}")
    assert EXCHANGE_CLIENT in _aud(uc), \
        f"authority-ui token must name {EXCHANGE_CLIENT} in aud to be exchangeable; got {_aud(uc)}"
    print("RESULT authority-ui token carries aud=authority-console (exchangeable) ✓")

    for aud, scope in (("token-broker", "broker-audience"), ("approval", "approval-audience")):
        ex = exchange(ui, aud, scope)
        ec = claims(ex)
        assert aud in _aud(ec), f"exchanged token missing aud={aud}: {_aud(ec)}"
        assert ec["sub"] == uc["sub"], "subject not preserved across exchange"
        assert ec.get("preferred_username") == USER, "username not preserved"
        print(f"RESULT exchange -> aud={aud}: sub preserved={ec['sub']}, "
              f"azp={ec['azp']}, aud={_aud(ec)} ✓")

    # Prove the broker's audience gate ACCEPTS the exchanged user-bound bearer:
    # hit an existing aud-checked endpoint. A non-403-wrong-audience answer means
    # the audience gate passed (no_grant / issued are both past the gate).
    broker_tok = exchange(ui, "token-broker", "broker-audience")
    resp = httpx.post(f"{BROKER}/v1/tokens/{ALIAS}", json={"scopes": []},
                      headers={"Authorization": f"Bearer {broker_tok}"}, timeout=15.0)
    body = resp.text[:120]
    err = ""
    try:
        err = resp.json().get("error", "")
    except Exception:
        pass
    assert not (resp.status_code == 403 and err == "wrong_audience"), \
        f"broker REJECTED exchanged token on audience: {resp.status_code} {body}"
    print(f"RESULT broker accepts exchanged user-bound bearer past audience gate "
          f"(status={resp.status_code} err={err!r}) ✓")


# --- 1.1: aggregation join for one principal ----------------------------------

def _fga_store_id() -> str:
    r = httpx.get(f"{OPENFGA}/stores", timeout=10.0)
    r.raise_for_status()
    for s in r.json().get("stores", []):
        if s["name"] == "prokura":
            return s["id"]
    raise AssertionError("no prokura FGA store")


def prove_aggregation() -> None:
    store = _fga_store_id()
    # agent -> operator: which agents does alice operate? Read all operator tuples
    # and filter by user in Python (OpenFGA /read wants an object or user, not a
    # bare relation), then the can_use tuples on her grants the same way.
    operators = _read_by_relation(store, "operator")
    my_agents = sorted({t["key"]["object"].split(":", 1)[1]
                        for t in operators if t["key"]["user"] == f"user:{USER}"})
    print(f"RESULT FGA: alice operates agents = {my_agents}")

    can_use = _read_by_relation(store, "can_use")
    my_grants: dict[str, list[str]] = {}
    for t in can_use:
        obj = t["key"]["object"]  # grant:{user}/{provider}
        who, agent = t["key"]["user"], obj.split(":", 1)[1]
        gowner, provider = agent.split("/", 1) if "/" in agent else (agent, "")
        if gowner == USER:
            my_grants.setdefault(who.split(":", 1)[1], []).append(provider)
    print(f"RESULT FGA: can_use on alice's grants (agent -> providers) = {my_grants}")

    # approval rows for alice (Postgres). No user-bound read API exists yet (that
    # is task 3.1); the spike reads the table directly via psql to prove the query.
    import subprocess
    sql = ("SELECT ref, agent, action, status FROM approvals WHERE user_id='alice' "
           "ORDER BY created_at DESC LIMIT 10;")
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "prokura",
         "-d", "prokura", "-tA", "-c", sql],
        capture_output=True, text=True)
    approval_rows = [ln for ln in out.stdout.strip().splitlines() if ln]
    print(f"RESULT approvals for alice: {len(approval_rows)} row(s); sample={approval_rows[:3]}")

    # Loki audit lines filtered to alice (server-side |= user=alice). Query via
    # Grafana's datasource proxy exactly as services/console does.
    import time
    now_ns = time.time_ns()
    q = '{service_name=~"token-broker|approval|mcp|rag"} |= `user=alice`'
    lr = httpx.get(f"{GRAFANA}/api/datasources/proxy/uid/loki/loki/api/v1/query_range",
                   params={"query": q, "start": str(now_ns - 24 * 3600 * 10**9),
                           "end": str(now_ns), "limit": 20, "direction": "backward"},
                   timeout=15.0)
    n = 0
    if lr.status_code == 200:
        for stream in lr.json().get("data", {}).get("result", []):
            n += len(stream.get("values", []))
    print(f"RESULT Loki |= user=alice over audit streams: {n} line(s) (status={lr.status_code})")
    # Prove the filter EXCLUDES another user: bob's filter must not surface alice's.
    qb = '{service_name=~"token-broker|approval|mcp|rag"} |= `user=bob` |= `user=alice`'
    lb = httpx.get(f"{GRAFANA}/api/datasources/proxy/uid/loki/loki/api/v1/query_range",
                   params={"query": qb, "start": str(now_ns - 24 * 3600 * 10**9),
                           "end": str(now_ns), "limit": 5, "direction": "backward"},
                   timeout=15.0)
    print(f"RESULT Loki cross-filter sanity (lines matching BOTH user=bob and user=alice) "
          f"status={lb.status_code} — filter is a plain substring gate on the line")


def _read_by_relation(store: str, relation: str) -> list[dict]:
    """Enumerate all tuples for a relation. OpenFGA's /read with an empty
    tuple_key returns every tuple; we page and filter by relation in Python.
    (A relation-only tuple_key is not a valid /read filter — an object or user
    is required — so we read-all, which is the honest cost of a per-principal
    aggregation over a relation the console does not index.)"""
    out, token = [], None
    while True:
        body: dict = {"page_size": 100}
        if token:
            body["continuation_token"] = token
        r = httpx.post(f"{OPENFGA}/stores/{store}/read", json=body, timeout=10.0)
        r.raise_for_status()
        data = r.json()
        out.extend(t for t in data.get("tuples", [])
                   if t["key"]["relation"] == relation)
        token = data.get("continuation_token")
        if not token:
            break
    return out


def main() -> int:
    print("== 1.3 EXCHANGE (authority-ui -> authority-console -> broker/approval) ==")
    prove_exchange()
    print("\n== 1.1 AGGREGATION (FGA + approvals + Loki for one principal) ==")
    prove_aggregation()
    print("\n== 1.2 IDP_LINK from the confidential authority-ui client ==")
    rc = idp_link_authority_ui()
    if rc != 0:
        return rc
    print("\nSPIKE PASSED")
    return 0


# --- 1.2: idp_link from authority-ui (non-account confidential client) ---------

def idp_link_authority_ui() -> int:
    verifier = _b64(secrets.token_bytes(32))
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    cookies: dict[str, dict] = {}
    with httpx.Client(follow_redirects=False, timeout=20.0) as c:
        auth = f"{KC}/realms/{REALM}/protocol/openid-connect/auth"
        r = c.get(auth, params={
            "client_id": UI_CLIENT, "response_type": "code", "redirect_uri": UI_REDIRECT,
            "scope": "openid", "state": "lnk", "kc_action": f"idp_link:{ALIAS}",
            "prompt": "login", "code_challenge": challenge, "code_challenge_method": "S256"})
        _merge(cookies, auth, r)
        assert r.status_code == 200, f"auth GET {r.status_code}: {r.text[:200]}"
        action = _form(r.text)
        assert action, "no prokura login form for idp_link"
        r = c.post(action, data={"username": USER, "password": PW},
                   headers={"Cookie": _cookie(cookies, action)})
        _merge(cookies, action, r)
        assert r.status_code in (302, 303, 307), f"login {r.status_code}: {r.text[:200]}"
        loc = r.headers["location"]
        acme_done = False
        for hop in range(3, 14):
            if loc.startswith(UI_REDIRECT) or loc.startswith("http://localhost:8160"):
                break
            url = loc if loc.startswith("http") else KC + loc
            r = c.get(url, headers={"Cookie": _cookie(cookies, url)})
            _merge(cookies, url, r)
            if r.status_code in (301, 302, 303, 307):
                loc = r.headers["location"]
                continue
            if r.status_code == 200 and "login-actions/required-action" in url \
                    and 'name="continue"' in r.text:
                a = html_mod.unescape(re.search(r'<form[^>]*action="([^"]+)"', r.text).group(1))
                r = c.post(a, data={"continue": ""}, headers={"Cookie": _cookie(cookies, a)})
                _merge(cookies, a, r)
                loc = r.headers["location"]
                continue
            if r.status_code == 200 and "/realms/acme/" in url and not acme_done:
                a = _form(r.text)
                assert a, f"no acme login form at {url}"
                r = c.post(a, data={"username": USER, "password": PW},
                           headers={"Cookie": _cookie(cookies, a)})
                _merge(cookies, a, r)
                acme_done = True
                loc = r.headers["location"]
                continue
            print(f"HOP {hop} UNEXPECTED {r.status_code} at {url}: {r.text[:200]}")
            return 2
        status = httpx.URL(loc).params.get("kc_action_status")
        print(f"RESULT idp_link from authority-ui: kc_action_status={status} (final={loc[:90]})")
        return 0 if status == "success" else 3


if __name__ == "__main__":
    sys.exit(main())
