# syntax=docker/dockerfile:1
#
# traceback-coach :: always-on JupyterLab image
# ---------------------------------------------
# Build context MUST be the REPO ROOT (so `pip install .` sees pyproject.toml):
#
#   docker compose -f deploy/docker-compose.yml build
#       (compose sets context: .. and dockerfile: deploy/Dockerfile)
#
# SECRET SAFETY: this Dockerfile does `COPY . /opt/app`. That is ONLY safe
# because a repo-root `.dockerignore` excludes deploy/.env, .git, .venv, etc.
# from the build context. Do NOT remove that .dockerignore.
#
# Hardening highlights:
#   - slim Python base
#   - dedicated non-root user (uid/gid 1000)
#   - app installed into a venv owned by that user
#   - no secrets baked in (password hash supplied at runtime via env -> config)
#   - listens only on the internal compose network; cloudflared reaches it as http://lab:8888

FROM python:3.12-slim

# --- OS layer: minimal, no recommends, clean apt cache ----------------------
# tini = proper PID 1 (reaps zombie kernels); curl used only for the healthcheck.
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends tini curl \
    && rm -rf /var/lib/apt/lists/*

# --- Non-root user ----------------------------------------------------------
ARG NB_USER=coach
ARG NB_UID=1000
ARG NB_GID=1000
RUN groupadd --gid ${NB_GID} ${NB_USER} \
    && useradd --uid ${NB_UID} --gid ${NB_GID} --create-home --shell /bin/bash ${NB_USER}

# --- Python environment -----------------------------------------------------
# Use an explicit venv so the non-root user owns every installed file.
ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JUPYTER_PORT=8888

RUN python -m venv ${VIRTUAL_ENV} \
    && chown -R ${NB_UID}:${NB_GID} ${VIRTUAL_ENV}

# Install JupyterLab first (cached layer), then the local package.
# jupyter-server 2.x / JupyterLab 4.x. argon2-cffi is needed so the
# hashed-password (argon2id) auth path works at runtime.
RUN pip install --upgrade "pip==24.*" \
    && pip install \
        "jupyterlab>=4.0,<5.0" \
        "jupyter-server>=2.0,<3.0" \
        "argon2-cffi>=21.3"

# --- App install ------------------------------------------------------------
WORKDIR /opt/app
# Copy package sources + build metadata, then install. The repo-root
# .dockerignore guarantees deploy/.env, .git and .venv are NOT in the context,
# so nothing secret is copied here. hatchling reads pyproject.toml at /opt/app.
COPY --chown=${NB_UID}:${NB_GID} . /opt/app
RUN pip install .

# The hermes-agent the SDK drives (heavy; its own cached layer so an SDK bump
# below doesn't reinstall it). The SDK notebooks run LIVE on the lab against it.
RUN pip install "hermes-agent[acp]"

# hermes-acp-sdk — pinned so the lab tracks a known-good release deterministically
# (an unpinned build once resolved to a stale version mid-PyPI-propagation). Bump
# this pin to ship a newer SDK. Safety comes from the key, not from omission:
# OPENROUTER_API_KEY (from deploy/.env) MUST be a $0-spend-limit key, so even
# though it is readable in the lab it can only ever call FREE models.
RUN pip install "hermes-acp-sdk[tools]==0.1.1"

# --- Runtime layout ---------------------------------------------------------
# Working dir for notebooks (mounted as a named volume in compose) and the
# server config that compose/Dockerfile point Jupyter at.
ENV NB_HOME=/home/${NB_USER} \
    NB_WORKDIR=/home/${NB_USER}/work \
    JUPYTER_CONFIG=/etc/jupyter/jupyter_server_config.py

# Two clearly separated folders so the two packages' notebooks don't get mixed up:
#   work/traceback-coach/  — the coach demo + CS1302 lessons
#   work/hermes-acp-sdk/   — the SDK demos (00_start_here runs offline here)
RUN mkdir -p ${NB_WORKDIR}/traceback-coach ${NB_WORKDIR}/hermes-acp-sdk ${NB_HOME}/.hermes /etc/jupyter \
    && cp /opt/app/*.ipynb ${NB_WORKDIR}/traceback-coach/ \
    && cp /opt/app/deploy/sdk-notebooks/*.ipynb ${NB_WORKDIR}/hermes-acp-sdk/ \
    && cp /opt/app/deploy/hermes-config.yaml ${NB_HOME}/.hermes/config.yaml \
    && cp /opt/app/deploy/jupyter_server_config.py ${JUPYTER_CONFIG} \
    && chown -R ${NB_UID}:${NB_GID} ${NB_HOME} /etc/jupyter

# Drop privileges.
USER ${NB_USER}
WORKDIR ${NB_WORKDIR}

EXPOSE 8888

# Container-local healthcheck (compose network only; not published to host).
# Use the ungated /login page and DON'T use `-f`: a password-gated server
# answers /api/status with 403, which `curl -f` would wrongly treat as down.
# `curl -s` exits 0 on any HTTP response, so this checks reachability.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -s -o /dev/null http://localhost:8888/login || exit 1

ENTRYPOINT ["tini", "--"]
# JUPYTER_TOKEN/JUPYTER_PASSWORD env is intentionally NOT set here; auth is the
# hashed password injected via the config file from JUPYTER_PASSWORD_HASH.
CMD ["jupyter", "lab", \
     "--config=/etc/jupyter/jupyter_server_config.py", \
     "--no-browser"]
