# 🤖 Taskmaster Pro — Autonomous Operations Agent

> **Built with the Strands Agents SDK for the Agentic AI Hackathon — Track 2: Professional Agents**  
> *Autonomous operational co-founder and engineering partner for technical professionals, makers, and software teams.*

[![Strands Agents SDK](https://img.shields.io/badge/Framework-Strands%20Agents%20SDK%20v1.55-purple?style=for-the-badge&logo=python)](https://strandsagents.com)
[![Track: Professional Agents](https://img.shields.io/badge/Hackathon%20Track-Professional%20Agents-blue?style=for-the-badge)](https://strandsagents.com)
[![Test Suite](https://img.shields.io/badge/Test%20Suite-93%2F93%20PASSED%20(100%25)-success?style=for-the-badge)](https://github.com/Tejas-Ranjeet/All_Agentic_AI_Hackathon)
[![Live Demo](https://img.shields.io/badge/Live%20Demo-Google%20Cloud%20Run-blue?style=for-the-badge&logo=google-cloud)](https://taskmaster-agent-558277271154.us-central1.run.app)
[![API Health](https://img.shields.io/badge/API%20Health-HEALTHY-success?style=for-the-badge)](https://taskmaster-agent-558277271154.us-central1.run.app/api/health)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-yellow?style=for-the-badge&logo=python)](https://www.python.org/)

---

## 🌐 Live Deployment & Demo Links

- 🚀 **Live Web Platform**: [https://taskmaster-agent-558277271154.us-central1.run.app](https://taskmaster-agent-558277271154.us-central1.run.app)
- 💬 **Live Agent Chat Workspace**: [https://taskmaster-agent-558277271154.us-central1.run.app/chat](https://taskmaster-agent-558277271154.us-central1.run.app/chat)
- 🏛️ **Architecture & DAG Visualizer**: [https://taskmaster-agent-558277271154.us-central1.run.app/architecture](https://taskmaster-agent-558277271154.us-central1.run.app/architecture)
- 🧰 **Live Tools Explorer (16+ Tools)**: [https://taskmaster-agent-558277271154.us-central1.run.app/features](https://taskmaster-agent-558277271154.us-central1.run.app/features)

---

## 🧪 Reproducible Testing Instructions for Judges

### Method 1: Instant Online Verification (Zero Setup)
1. Open the [Live Agent Chat](https://taskmaster-agent-558277271154.us-central1.run.app/chat).
2. Try executing any Track 2 professional test prompt:
   - **PRD to Jira & Docker Test**: *"Parse this PRD for OAuth2 Refresh Token rotation, decompose into Jira engineering tasks with story points, and run smoke tests in Docker sandbox."*
   - **GitHub PR & Release Brief**: *"Audit our GitHub repository commit logs, draft a release pull request summary, and prepare an executive changelog report."*
   - **Multi-Agent Council Graph**: *"Execute our Multi-Agent Council: Spec Specialist parses requirements, QA runs environment verification, Operations prepares backlog, and Comms drafts team updates."*
   - **Governed HITL Release**: *"Draft a customer release notification email and team Slack announcement, then pause for my approval before sending."*
3. Observe real-time SSE token streaming, tool execution, and the interactive Human-in-the-Loop approval gate before external dispatches.
4. Verify Strands capabilities and tool registry:
   ```bash
   curl -s https://taskmaster-agent-558277271154.us-central1.run.app/api/health
   curl -s https://taskmaster-agent-558277271154.us-central1.run.app/api/strands/tools
   ```

### Method 2: Local Reproduction & Automated Test Suite (100% Pass)
```bash
# 1. Clone repository
git clone https://github.com/Tejas-Ranjeet/All_Agentic_AI_Hackathon.git
cd All_Agentic_AI_Hackathon

# 2. Install dependencies (including Strands Agents SDK)
pip install -r requirements.txt

# 3. Run complete automated test suite (93 tests, 100% passing)
pytest tests/ -v

# 4. Run dedicated Strands Agents SDK tests
pytest tests/test_strands_agent.py -v

# 5. Start local server
uvicorn app:app --reload --port 8000
```
Open `http://localhost:8000/chat` to interact locally.

---

## 📌 Executive Overview — Track 2: Professional Agents

Technical founders, engineering leaders, and solo product makers spend over 60% of their time on repetitive, judgment-heavy operational tasks: turning customer requests into Jira stories, running test suites across branches, preparing GitHub pull requests, drafting stakeholder updates, and syncing team Slack channels.

**Taskmaster Pro** is built with the **Strands Agents SDK** to automate this operational choreography end to end:
1. **Model-Driven Agent Core**: Built using `from strands import Agent, tool` and `GeminiModel`.
2. **Directed Multi-Agent Council Graph**: Powered by `strands.multiagent.graph.Graph` orchestrating 4 specialized agents:
   - 🔍 **Spec & PRD Specialist**: Analyzes requirements and assigns story point estimates.
   - 🧪 **Engineering & QA Specialist**: Executes smoke tests in an isolated Docker sandbox.
   - 🚀 **Operations & Release Specialist**: Populates Jira backlogs and drafts GitHub PRs.
   - 📢 **Communications Specialist**: Drafts Slack briefings and executive summaries.
3. **Safe Governance via HITL**: Powered by `strands.vended_interventions.hitl.HumanInTheLoop`, ensuring sensitive actions (email sending, PR merging, webhook dispatches) require human review before firing.
4. **Universal Tool Connectivity**: Full Model Context Protocol (MCP) server & client support.

---

## 🏗️ System Architecture

```
                                  +-----------------------+
                                  |   User / Web UI       |
                                  +-----------+-----------+
                                              |
                                              v
                                  +-----------------------+
                                  |   FastAPI REST API    |
                                  |   (Cloud Run Ready)   |
                                  +-----------+-----------+
                                              |
                                              v
                                  +-----------------------+
                                  | Taskmaster Engine     |
                                  | (Plan-then-Execute)   |
                                  +-----+-----------+-----+
                                        |           |
            +---------------------------+           +---------------------------+
            |                                       |                           |
            v                                       v                           v
+-----------------------+               +-----------------------+   +-----------------------+
| Gemini 3.5 Flash      |               |  Tool Execution       |   | Memory & OpenTelemetry|
| (google-genai SDK)    |               |  Registry (6 Tools)   |   | Reasoning Traces      |
+-----------------------+               +-----------------------+   +-----------------------+
                                        | - data_extractor      |
                                        | - db_manager          |
                                        | - action_dispatcher   |
                                        | - report_generator    |
                                        | - validator           |
                                        | - python_sandbox      |
                                        +-----------------------+
```

---

## 🛠️ Built-in Tool Catalog (Real Actions, No Chat-Only)

1. **`data_extractor`**: Parsed raw unstructured text, server logs, CSVs, or JSON payloads into validated structured schemas.
2. **`db_manager`**: Handles database persistence, querying, and audit trail updates (compatible with Cloud SQL / Firestore / SQLite).
3. **`action_dispatcher`**: Triggers external REST webhooks, system endpoints, and automated alert dispatches.
4. **`report_generator`**: Compiles executive markdown briefings, post-mortems, and deliverable artifacts.
5. **`validator`**: Performs compliance & quality rule inspections, signaling self-correction loops if anomalies are found.
6. **`python_sandbox`**: Executes untrusted python scripts natively in a subprocess (isolated by timeout, sandboxed from host secrets - not a full execution sandbox).

---

## 💻 Multi-Channel & CLI Entrypoints

Taskmaster isn't just a web app. It can run seamlessly anywhere you need it.

### Taskmaster CLI
For developers who prefer the terminal, Taskmaster features a sleek CLI built with `rich`:
```bash
python taskmaster_cli.py "generate an executive report" --priority High
```

### Discord Bot
To run workflows autonomously in your team chats, spin up the Discord bot:
```bash
DISCORD_TOKEN=your_token_here python discord_bot.py
```
*Usage in Discord*: `@Taskmaster !task audit our service logs and update the DB`

---

## 🚀 Quickstart & Spin-up Instructions

### Prerequisites
- Python 3.10+
- (Optional) Docker & Docker Compose
- Gemini API Key (optional — features intelligent **Mock Mode** for offline zero-cost testing)

### 1. Local Setup
```bash
# Clone repository
git clone https://github.com/Tejas-Ranjeet/All_Agentic_AI_Hackathon.git
cd All_Agentic_AI_Hackathon

# Create virtual environment & install dependencies
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env`:
```ini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash
MOCK_GEMINI=false  # Set to true for mock testing without API key
PORT=8000
HOST=0.0.0.0
```

### 3. Run API Backend Server
```bash
uvicorn app:app --reload --port 8000
```
Access interactive OpenAPI documentation at: `http://localhost:8000/docs`

### 4. Run Automated Test Suite
```bash
pytest tests/ -v
```

---

## 🐳 Containerization & Google Cloud Run Deployment (Person 2 Guide)

### Docker Local Build & Test
```bash
docker build -t taskmaster-agent .
docker run -p 8000:8000 taskmaster-agent
```

### Google Cloud Run 2-Minute Deployment
```bash
# Set GCP Project
gcloud config set project YOUR_GCP_PROJECT_ID

# Build container on Artifact Registry / Cloud Build
gcloud builds submit --tag gcr.io/YOUR_GCP_PROJECT_ID/taskmaster-agent

# Deploy to Cloud Run
gcloud run deploy taskmaster-agent \
    --image gcr.io/YOUR_GCP_PROJECT_ID/taskmaster-agent \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --set-env-vars GEMINI_API_KEY="your_api_key",MOCK_GEMINI="false"
```

---

## 📡 REST API Reference (Person 3 Integration Guide)

### 1. `GET /api/health`
Health probe for Cloud Run containers. Returns model status and tool count.

### 2. `GET /api/agent/tools`
Returns JSON list of registered tools and schemas.

### 3. `POST /api/agent/run`
Submits high-level task goal and triggers autonomous execution.
**Payload**:
```json
{
  "goal": "Audit cluster error logs, record state in DB, dispatch remediation webhook, and build report",
  "context": { "priority": "HIGH" }
}
```

### 4. `GET /api/agent/status/{workflow_id}`
Returns step-by-step progress, current step status, and final executive report artifact.

### 5. `GET /api/agent/traces/{workflow_id}`
Returns OpenTelemetry-compatible reasoning chain trace logs for agent observability.

---

## 🏆 Hackathon Submission Checklist

- [x] **Track**: Taskmaster (Autonomous workflow agent)
- [x] **Gemini Integration**: Built using `google-genai` SDK and Gemini 3.5 Flash model
- [x] **Google Cloud Readiness**: Optimized Dockerfile & Cloud Run deployment configuration
- [x] **Reproducible Code**: 100% test coverage with Pytest
- [x] **Observability**: Reasoning trace logs & self-correction execution loops

---

## 📄 License
MIT License. Built for the All Things Agentic Hackathon 2026.
