"""
Jupyter Server 2.x configuration for the always-on traceback-coach lab.

Security model (defence in depth):
  1. Cloudflare Access sits in FRONT of this server and is the PRIMARY gate.
  2. THIS file adds a second factor: a hashed (argon2id) password. No token.
  3. The server only listens on the internal container/compose network; cloudflared
     reaches it as http://lab:8888. No host port is published.

The password hash is injected at runtime from the JUPYTER_PASSWORD_HASH env var
so no secret is baked into the image. Generate it with:

    python -c "from jupyter_server.auth import passwd; print(passwd())"

That prints something like  argon2:$argon2id$v=19$m=10240,t=10,p=8$....
Put the whole string (quoted) into deploy/.env as JUPYTER_PASSWORD_HASH=...

Public hostname (set in Cloudflare dashboard) is read from PUBLIC_HOSTNAME,
e.g. PUBLIC_HOSTNAME=lab.example.com  -> origin https://lab.example.com.

This config FAILS CLOSED: if a required secret/hostname is missing it raises,
so the server never boots in a silently-open state.
"""

import os

c = get_config()  # noqa: F821  (provided by Jupyter at config-load time)

# --------------------------------------------------------------------------- #
# Network binding (inside the container only)
# --------------------------------------------------------------------------- #
c.ServerApp.ip = "0.0.0.0"          # listen on all container interfaces
c.ServerApp.port = 8888
c.ServerApp.open_browser = False
c.ServerApp.allow_remote_access = True   # required: requests arrive from cloudflared, not localhost
c.ServerApp.base_url = "/"
c.ServerApp.trust_xheaders = True        # honour X-Forwarded-* from cloudflared (internal net only)
c.ServerApp.root_dir = os.environ.get("NB_WORKDIR", "/home/coach/work")

# Default landing experience = JupyterLab.
c.ServerApp.default_url = "/lab"

# --------------------------------------------------------------------------- #
# Authentication  (jupyter-server 2.x: auth lives on IdentityProvider)
# --------------------------------------------------------------------------- #
# Hashed password (argon2id) from the environment. The hashed_password on the
# PasswordIdentityProvider is the SINGLE authoritative secret form. We do NOT
# also set the deprecated ServerApp.password alias, to avoid any precedence
# ambiguity between the two code paths.
_pw_hash = os.environ.get("JUPYTER_PASSWORD_HASH", "").strip()
if not _pw_hash:
    raise RuntimeError(
        "JUPYTER_PASSWORD_HASH is not set. Generate it with "
        "`python -c \"from jupyter_server.auth import passwd; print(passwd())\"` "
        "and put it in deploy/.env"
    )
if not _pw_hash.startswith("argon2:"):
    raise RuntimeError(
        "JUPYTER_PASSWORD_HASH must be a HASH (starts with 'argon2:'), not a "
        "plaintext password. Re-generate it with jupyter_server.auth.passwd()."
    )

c.PasswordIdentityProvider.hashed_password = _pw_hash

# Force password login: explicitly DISABLE token auth so no token-in-URL exists.
c.IdentityProvider.token = ""
c.ServerApp.token = ""              # deprecated alias, kept empty for safety
# Require a password to be configured; refuse to serve with no auth.
c.ServerApp.password_required = True
c.PasswordIdentityProvider.password_required = True
c.PasswordIdentityProvider.allow_password_change = False
# Do NOT permit unauthenticated access to any handler.
c.IdentityProvider.allow_unauthenticated_access = False

# --------------------------------------------------------------------------- #
# Origin / CORS / CSP — lock to the public Cloudflare hostname (FAIL CLOSED)
# --------------------------------------------------------------------------- #
_host = os.environ.get("PUBLIC_HOSTNAME", "").strip()
if not _host:
    raise RuntimeError(
        "PUBLIC_HOSTNAME is not set. It is required so the Jupyter origin/CSP "
        "lock matches the Cloudflare hostname. Set it in deploy/.env, e.g. "
        "PUBLIC_HOSTNAME=lab.example.com"
    )
_origin = f"https://{_host}"

# Only accept WebSocket/XHR whose Origin matches our public URL. Never '*'.
c.ServerApp.allow_origin = _origin
c.ServerApp.local_hostnames = [_host]
# Belt & braces: keep CORS credentials off and do not echo arbitrary origins.
c.ServerApp.allow_credentials = False

# Keep XSRF protection ON. Do NOT disable check_xsrf — that would open CSRF.
c.ServerApp.disable_check_xsrf = False

# Disallow being framed by other sites; restrict CSP to self + our origin.
# frame-ancestors 'self' blocks clickjacking; cloudflared/WS are same-origin so
# this does not break the lab.
_csp = f"frame-ancestors 'self' {_origin}; "

c.ServerApp.tornado_settings = {
    "headers": {
        "Content-Security-Policy": _csp,
        "X-Frame-Options": "SAMEORIGIN",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
    }
}

# --------------------------------------------------------------------------- #
# Misc hardening / quality-of-life
# --------------------------------------------------------------------------- #
c.ServerApp.allow_root = False           # we already run as non-root; belt & braces
c.ServerApp.terminals_enabled = True     # set False to further reduce surface
c.ServerApp.shutdown_no_activity_timeout = 0  # always-on; do not auto-shutdown
