<p align="center">
  <img src="https://raw.githubusercontent.com/sshivasai/Carole.ai/master/frontend/public/branding/logo-full-dark-animated.gif" alt="Carole.ai Logo" width="280" />
 
</p>

# Carole.ai

**AI AGENTS. REAL WORK.**

Carole.ai is an advanced AI-powered assistant and development environment with a robust suite of features including Hybrid GraphRAG, zero-cost meeting integration, MCP (Model Context Protocol) expansion, and a native real-time Kanban board.

## Install

Carole.ai includes its production web interface in the Python package, so Node.js
is not required at runtime. Python 3.11 or 3.12 is supported.

```bash
pip install carole.ai
caroleai
```

Carole.ai opens at [http://127.0.0.1:8000](http://127.0.0.1:8000) and stores
persistent application data in `~/.carole`. For an isolated application install,
you can use `pipx install carole.ai`. Browser automation additionally requires
the one-time command `playwright install chromium`.

## Features

- **Hybrid GraphRAG**: Combines Dense (LanceDB) and Sparse memory retrieval, mapped alongside a real-time `networkx` Code Graph for unparalleled context awareness.
- **Zero-Cost Meeting Integration**: Seamlessly integrates with Google Meet via Playwright DOM caption scraping and native chat injection.
- **MCP Expansion**: Features a universal Model Context Protocol firewall and dynamic ToolRegistry, expanding the ecosystem of available models and tools securely.
- **Native Real-Time Kanban**: EventBus-driven split-screen project management for dynamic task tracking and synchronization.

## Local Setup Instructions

Follow these steps to get Carole.ai running locally.

### 1. Prerequisites
- Docker and Docker Compose
- Node.js (v22 recommended)
- Python (v3.11 or later)

### 2. Environment Variables
Create a `.env` file in the root directory (or update the existing one) with the necessary variables. At a minimum, you'll need:

```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
# Optional recovery override. Normally the first account is the local owner.
# CAROLE_OWNER_ID=your_account_uuid
# Add other required API keys or database URLs as needed
```

### 3. Start the Backend (FastAPI)
The backend requires Python and FastAPI. We recommend using a virtual environment.

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

### 4. Start the Frontend (Next.js)
The frontend is built with Next.js. Open a new terminal window to start it.

```bash
cd frontend
npm install
npm run dev
```

### 5. Access the Application
- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)


## Instance owner and upgrade notes

The first account created is automatically the local instance owner. An operator
can optionally set `CAROLE_OWNER_ID` to an account UUID as a recovery override.
The instance owner controls host capabilities:
terminal/shell access, Git, browser automation, plugins, MCP servers, external
workspace paths, and instance settings/model/prompt administration. These
operations are unavailable until an owner is configured. Project ownership alone
does not grant access to the host machine. Host tools run with the backend OS
account's privileges; this is not an OS sandbox for untrusted tenants.

File, search, Git, and history APIs require an owned project UUID. Clients must
use the backend Git API; the former Next.js Git endpoint returns HTTP 410.
Attachments require authenticated downloads. Google accounts must reconnect
through Settings after upgrading: credentials are now stored separately per
account, and the old shared token is not reused. The OAuth start request must
include browser credentials so its callback can verify the initiating browser.

Docker stores application data in the `carole_data` volume at `/data/carole`.
Back up and copy any existing `.carole` data into that volume before switching an
existing deployment; creating the volume does not migrate old data. An explicit
`DATABASE_URL` or `CAROLE_HOME_DIR` override must point to persistent storage.
Playwright browsers are installed at a path available to the non-root app user.

See [runtime repair notes](docs/RUNTIME_REPAIRS.md) for the implementation changes
and verification boundaries.
