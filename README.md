<p align="center">
  <img src="https://raw.githubusercontent.com/sshivasai/Carole.ai/master/frontend/public/branding/logo-full.png" alt="Carole.ai logo" width="320" />
</p>

<h1 align="center">Carole.ai</h1>
<p align="center"><strong>AI AGENTS. REAL WORK.</strong></p>

Carole.ai is a local AI agent workspace with chat, project tools, memory, MCP
integrations, browser automation, and a Kanban board. The PyPI package includes
the built web interface: one `caroleai` command runs the FastAPI backend and
serves the frontend from the same address.

## Install and run

Use Python 3.11 or 3.12. A virtual environment is recommended:

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install carole.ai
caroleai
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The first account created
becomes the local instance owner. Application data is stored in `~/.carole` by
default. Node.js and Docker are **not** required for the PyPI installation.

You can also install the command with `pipx install carole.ai`. To use browser
automation, install the Chromium browser once with `playwright install chromium`.
Connect an AI model provider in the app's settings or supply its API key through
your environment.

Run `caroleai --help` for options including `--port`, `--data-dir`, and
`--no-browser`. The command binds to `127.0.0.1` by default. Keep it local unless
you have deliberately secured access: the instance owner can use host-level
capabilities such as shell, Git, plugins, and browser automation.

For persistent login sessions, set a stable, random `JWT_SECRET` in your
environment or `.env` file before starting Carole.ai. Without one, a new secret
is generated on each restart and existing sessions are invalidated. Never commit
API keys or secrets to this repository.

## Features

- Hybrid GraphRAG memory with LanceDB and a `networkx` code graph.
- MCP integrations and a dynamic tool registry.
- Browser and meeting workflows, including Google Meet integration.
- Real-time Kanban and project-management tools.

## Develop from source

The [public GitHub repository](https://github.com/sshivasai/Carole.ai) contains
both the FastAPI backend and the Next.js frontend. The following is for
contributors working on the source; it is **not** needed to run the PyPI package.

Prerequisites: Python 3.11 or 3.12 and Node.js 22. From the repository root,
create a Python environment and install the backend requirements:

```bash
python -m venv .venv
# Activate .venv for your shell, then:
python -m pip install -r backend/requirements.txt
cd backend
uvicorn main:app --reload
```

In another terminal, start the frontend:

```bash
cd frontend
npm ci
npm run dev
```

The development frontend is at [http://localhost:3000](http://localhost:3000),
the API at [http://localhost:8000](http://localhost:8000), and API documentation
at [http://localhost:8000/docs](http://localhost:8000/docs). Set provider API
keys in your own local environment if you want to use model-backed features.

Source, bug reports, and contributions are available through
[GitHub](https://github.com/sshivasai/Carole.ai) and its
[issue tracker](https://github.com/sshivasai/Carole.ai/issues).

## Instance owner and upgrade notes

The first account created is automatically the local instance owner. An operator
can optionally set `CAROLE_OWNER_ID` to an account UUID as a recovery override.
The instance owner controls host capabilities: terminal/shell access, Git,
browser automation, plugins, MCP servers, external workspace paths, and
instance settings/model/prompt administration. These operations are unavailable
until an owner is configured. Project ownership alone does not grant access to
the host machine. Host tools run with the backend OS account's privileges; this
is not an OS sandbox for untrusted tenants.

File, search, Git, and history APIs require an owned project UUID. Clients must
use the backend Git API; the former Next.js Git endpoint returns HTTP 410.
Attachments require authenticated downloads. Google accounts must reconnect
through Settings after upgrading: credentials are now stored separately per
account, and the old shared token is not reused. The OAuth start request must
include browser credentials so its callback can verify the initiating browser.

Docker stores application data in the `carole_data` volume at `/data/carole`.
Back up and copy any existing `.carole` data into that volume before switching
an existing deployment; creating the volume does not migrate old data. An
explicit `DATABASE_URL` or `CAROLE_HOME_DIR` override must point to persistent
storage. Playwright browsers are installed at a path available to the non-root
app user.
