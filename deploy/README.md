# traceback-coach — always-on, hardened JupyterLab

A reproducible, always-on JupyterLab that runs the `traceback-coach` package and
is reachable only at **`https://lab.<your-domain>`** through a **Cloudflare named
tunnel** — with **zero inbound ports** on the host. Two independent auth gates sit
in front of the lab: **Cloudflare Access** (identity) and a **hashed Jupyter
password** (argon2id). It keeps running when your laptop is off because it lives
on a small always-on host, not a laptop tunnel.

```
  browser ──TLS──▶ Cloudflare edge ──(Access: email allow-list)──▶ tunnel
                                                                     │ outbound only
                                       ┌─────────────────────────────┘
                                       ▼
                              cloudflared (sidecar) ──http://lab:8888──▶ JupyterLab
                                       (compose network, no host ports)
```

## What's in this directory

| File | Role |
|---|---|
| `Dockerfile` | Hardened JupyterLab image; installs the root package via `pip install .`. Non-root user `coach`. |
| `docker-compose.yml` | Two services: `lab` (no host ports) and `cloudflared` (outbound tunnel sidecar). |
| `jupyter_server_config.py` | Jupyter Server 2.x config: hashed password, token disabled, origin/CSP locked to your hostname, fails closed. |
| `.env.example` | Template for `.env`. Copy to `.env` (gitignored) and fill in real secrets. |
| `.gitignore` | Second-layer guarantee that `.env` is never committed. |

> **CRITICAL — image secret hygiene.** The Docker build context is the **repo
> root** and the Dockerfile runs `COPY . /opt/app`. A **repo-root `.dockerignore`**
> (committed at the top of the repo) excludes `deploy/.env`, `.git`, and `.venv`
> from the build context so secrets are **never baked into image layers**. Do not
> delete it. Verify after a build (see §5).

All commands below are run **from the repo root** unless noted, because the Docker
build context is the repo root (so `pip install .` can see `pyproject.toml`).

---

## 1. Provision an always-on host

Use any small Linux box that is always on (NOT your Mac). Good options:

- **Hetzner CX22** (~€4/mo, 2 vCPU / 4 GB) — primary recommendation, x86_64, Ubuntu 24.04.
- **Oracle Cloud Always-Free Ampere A1** ($0, ARM64) — free but ARM (`cloudflared` is multi-arch; build the lab image on the box and it just works).

The steps assume **Ubuntu 24.04 LTS**.

### 1.1 Create a non-root sudo user

```bash
adduser deploy
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy   # copy your SSH key
```
Reconnect as `deploy` for everything below.

### 1.2 Firewall: default-deny inbound (no app ports needed)

The tunnel dials **out**, so nothing inbound is required for Jupyter — keep only SSH.

```bash
sudo apt-get update
sudo apt-get install -y ufw
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw enable
sudo ufw status verbose
```
No `80`/`443`/`8888` rules — by design.

### 1.3 Install Docker Engine + Compose v2 plugin

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update

sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

### 1.4 Post-install: run docker without sudo + start on boot

```bash
sudo usermod -aG docker deploy
newgrp docker
sudo systemctl enable --now docker.service
sudo systemctl enable --now containerd.service
docker run --rm hello-world        # verify engine
docker compose version             # verify the v2 plugin ('docker compose', no hyphen)
```

---

## 2. One-time Cloudflare setup (Zero Trust dashboard)

Do this once in the dashboard at <https://one.dash.cloudflare.com>. The domain
must already be on Cloudflare (proxied).

### 2.1 Create the named tunnel and copy its token

1. **Zero Trust → Networks → Tunnels → Create a tunnel → Cloudflared.**
2. Name it (e.g. `traceback-coach`). Save.
3. On the "Install and run a connector" screen, copy the **token** — the long
   string after `--token` in the shown docker command. This goes into `.env` as
   `TUNNEL_TOKEN`. (You do NOT run the shown command directly; the `cloudflared`
   sidecar in `docker-compose.yml` runs `tunnel --no-autoupdate run` with the token from env.)

### 2.2 Add the public hostname route

In the tunnel's **Public Hostnames** tab → **Add a public hostname**:

- **Subdomain:** `lab`
- **Domain:** `<your-domain>`
- **Path:** (leave blank)
- **Service → Type:** `HTTP`
- **Service → URL:** `lab:8888`   ← the compose service name + port

Cloudflare auto-creates the `lab` DNS CNAME to the tunnel — no A record, no open port.

### 2.3 Create the Cloudflare Access application + policy (PRIMARY gate)

1. **Settings → Authentication → Login methods:** ensure **One-time PIN** is
   present (optionally add **Google** as an IdP).
2. **Access → Applications → Add an application → Self-hosted.**
   - **Application name:** `traceback-coach lab`
   - **Session duration:** e.g. `24h` (shorter = more re-auth)
   - **Public hostname:** subdomain `lab`, domain `<your-domain>`, path blank
     (this MUST match `PUBLIC_HOSTNAME` / the tunnel route).
3. **Add a policy → Action: Allow.**
   - **Include → Emails →** list the exact allowed addresses (e.g. `you@example.com`).
   - Do **NOT** use "Include → Login Methods: One-Time PIN" alone — that lets
     anyone request a PIN. Restrict by **Emails** (or **Emails ending in** your domain).
4. (Recommended) Add a **second policy → Action: Block → Include → Everyone** is
   NOT needed; Access denies by default. But DO confirm the default action is
   not "Bypass" / "Service Auth" and that no "Everyone" Allow rule exists.

Unauthenticated requests are now stopped at Cloudflare's edge and never reach the host.

---

## 3. Generate the Jupyter password hash (second gate)

Generate it anywhere with Python + jupyter-server (it prompts twice, so the
plaintext is never in shell history):

```bash
python -c "from jupyter_server.auth import passwd; print(passwd())"
# -> argon2:$argon2id$v=19$m=10240,t=10,p=8$<salt>$<hash>
```

Don't have jupyter-server locally? Generate it inside a throwaway container on the host:

```bash
docker run --rm -it python:3.12-slim sh -c \
  "pip install -q jupyter-server argon2-cffi && \
   python -c 'from jupyter_server.auth import passwd; print(passwd())'"
```

Copy the FULL `argon2:...` string for the next step. The config refuses to start
unless the value begins with `argon2:` (i.e. it rejects a pasted plaintext).

---

## 4. Clone the repo and configure secrets

The GitHub repo is **private**; authenticate with `gh auth login` or a deploy key/PAT.
Use the actual remote for your fork (the package metadata references
`github.com/dive4dec/jupyter-hermes-personalities`; substitute your real remote):

```bash
sudo apt-get install -y git
git clone <your-private-repo-url> hermes-package
cd hermes-package

cp deploy/.env.example deploy/.env
nano deploy/.env          # fill in the three values, save
chmod 600 deploy/.env     # tighten perms; .env is gitignored
```

`deploy/.env` holds:

```dotenv
TUNNEL_TOKEN=<token from step 2.1>
PUBLIC_HOSTNAME=lab.<your-domain>
LAB_DOMAIN=lab.<your-domain>
JUPYTER_PASSWORD_HASH=argon2:$argon2id$v=19$m=10240,t=10,p=8$<salt>$<hash>
```

> The `$` in the hash are LITERAL in `.env` (dotenv does not expand them). Paste
> the hash exactly as printed.

Confirm the secret file is ignored by BOTH gitignores before anything else:

```bash
git check-ignore -v deploy/.env    # must print a matching .gitignore rule
git status --porcelain | grep -i '\.env$' || echo "OK: no .env staged/tracked"
```

---

## 5. Bring the stack up (and verify the invariants)

```bash
# from the repo root
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml ps     # both 'lab' and 'cloudflared' Up
docker compose -f deploy/docker-compose.yml logs -f cloudflared   # look for "Registered tunnel connection"
```

**Verify no secret was baked into the image** (must print nothing):

```bash
docker run --rm --entrypoint sh traceback-coach-lab:latest -c \
  'find /opt/app -maxdepth 2 -name ".env" -o -name ".git" 2>/dev/null'
# (empty output = good; .dockerignore did its job)
```

**Verify no host port is published** (must show no 8888/0.0.0.0 bindings):

```bash
docker compose -f deploy/docker-compose.yml ps        # PORTS column must be blank for 'lab'
sudo ss -tlnp | grep -E ':8888|:443|:80' || echo "OK: nothing listening on host"
```

Once the tunnel is registered, browse to **`https://lab.<your-domain>`**:
1. Cloudflare Access prompts for your email (OTP or Google SSO).
2. Then JupyterLab's password page (the argon2 password you set).
3. You land in `/lab` with the notebooks available (`00_start_here.ipynb` first).

---

## 6. Day-2 operations

**Autostart on reboot** is already covered by `systemctl enable docker` (§1.4) +
`restart: unless-stopped` on both services. Verify with `sudo reboot`, reconnect,
`docker compose -f deploy/docker-compose.yml ps`.

**Update code / rebuild:**
```bash
cd ~/hermes-package
git pull
docker compose -f deploy/docker-compose.yml up -d --build
docker image prune -f
```

**Update the tunnel image only** (image is version-pinned in compose; bump the
tag deliberately, then):
```bash
docker compose -f deploy/docker-compose.yml pull cloudflared
docker compose -f deploy/docker-compose.yml up -d
```

**Logs:**
```bash
docker compose -f deploy/docker-compose.yml logs -f            # both
docker compose -f deploy/docker-compose.yml logs -f lab        # Jupyter
docker compose -f deploy/docker-compose.yml logs -f cloudflared
```

**Back up the notebooks volume** (named volume `traceback-coach_notebooks`; confirm with `docker volume ls`):
```bash
docker run --rm \
  -v traceback-coach_notebooks:/data:ro \
  -v "$PWD":/backup \
  busybox tar czf /backup/notebooks-$(date +%F).tgz -C /data .
```
Restore:
```bash
docker run --rm \
  -v traceback-coach_notebooks:/data \
  -v "$PWD":/backup \
  busybox sh -c "cd /data && tar xzf /backup/notebooks-YYYY-MM-DD.tgz"
```
Copy the `.tgz` off-host (scp/rclone) for safety; consider a weekly cron.

**Rotate the Jupyter password:** re-run the `passwd()` command, replace
`JUPYTER_PASSWORD_HASH` in `deploy/.env`, then
`docker compose -f deploy/docker-compose.yml up -d` (recreates `lab`).

**Rotate the tunnel token:** Zero Trust → Networks → Tunnels → your tunnel →
**Refresh token**; paste the new value into `.env`; restart `cloudflared`.

---

## 7. SECURITY checklist

Three INDEPENDENT gates, plus host hygiene:

- [ ] **Gate 1 — Cloudflare Access** application protects `lab.<domain>` with an
      **Allow** policy that **Includes specific Emails** (not "any OTP login",
      not "Everyone"). No "Bypass"/"Service Auth" default. Session duration short.
- [ ] **Gate 2 — TLS at the edge.** `https://lab.<domain>` is proxied (orange
      cloud); the host↔Cloudflare leg is the encrypted outbound tunnel.
- [ ] **Gate 3 — Jupyter argon2 password.** `JUPYTER_PASSWORD_HASH` is set and
      starts with `argon2:`; token auth disabled (`IdentityProvider.token=""`,
      `password_required=True`, `disable_check_xsrf=False`). No token-in-URL.
- [ ] **No secret in the image.** Repo-root `.dockerignore` excludes
      `deploy/.env`, `.git`, `.venv`; verified with the `find /opt/app` check (§5).
- [ ] **Zero inbound ports.** `ufw` default-deny incoming (only SSH); compose
      publishes **no** `ports:` (only internal `expose: 8888`); cloudflared is
      outbound-only; `ss -tlnp` shows nothing on 80/443/8888.
- [ ] **Secrets never in git.** `deploy/.env` exists only on the host, `chmod 600`,
      matched by BOTH the repo-root `.gitignore` and `deploy/.gitignore`. Only
      `.env.example` (placeholders) is committed. `git check-ignore -v deploy/.env` passes.
- [ ] **Container hardening.** `lab` runs as non-root `coach` (uid 1000),
      `cap_drop: ALL`, `no-new-privileges`, CPU/memory/pids limits,
      `restart: unless-stopped`, notebooks in a named volume.
- [ ] **PUBLIC_HOSTNAME matches everywhere** and is REQUIRED — the config fails
      closed without it. Same `lab.<domain>` in the Access app, the tunnel route,
      and `.env` (locks `allow_origin` / WebSocket handshake; never `*`).
- [ ] **Pinned tunnel image.** `cloudflared` is a fixed version, not `:latest`.
- [ ] **Host hygiene.** SSH key-only (consider moving SSH behind Cloudflare
      Tunnel too). Rebuild monthly for base-image CVE fixes.
- [ ] **Incident response.** If any secret leaks, rotate BOTH the tunnel token and
      the Jupyter password immediately; history-scrubbing alone is insufficient.
