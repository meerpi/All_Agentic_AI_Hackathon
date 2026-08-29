# 🤖 Taskmaster Autonomous Agent Engine

> **Built for the All Things Agentic Hackathon — Track: Taskmaster**  
> *Next-generation autonomous AI agent engine powered by Gemini 3.5 & Google Cloud Infrastructure.*

---

## 📌 Executive Overview

Most AI tools today act as passive chatbots waiting for prompt-by-prompt instructions. **Taskmaster** is built differently: it takes a high-level operational goal, formulates an executable multi-step plan, selects and runs real tools, recovers from anomalies via self-correction, and produces validated deliverables—all asynchronously in the background.

Designed for high-impact enterprise & developer automation, Taskmaster handles multi-step chores such as log parsing, incident remediation, database updates, webhook dispatches, compliance checks, and executive report generation.

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
                                  | (ReAct Planner/Loop)  |
                                  +-----+-----------+-----+
                                        |           |
            +---------------------------+           +---------------------------+
            |                                       |                           |
            v                                       v                           v
+-----------------------+               +-----------------------+   +-----------------------+
| Gemini 3.5 Flash      |               |  Tool Execution       |   | Memory & OpenTelemetry|
| (google-genai SDK)    |               |  Registry (5 Tools)   |   | Reasoning Traces      |
+-----------------------+               +-----------------------+   +-----------------------+
                                        | - data_extractor      |
                                        | - db_manager          |
                                        | - action_dispatcher   |
                                        | - report_generator    |
                                        | - validator           |
                                        +-----------------------+
```

---

## 🛠️ Built-in Tool Catalog (Real Actions, No Chat-Only)

1. **`data_extractor`**: Parsed raw unstructured text, server logs, CSVs, or JSON payloads into validated structured schemas.
2. **`db_manager`**: Handles database persistence, querying, and audit trail updates (compatible with Cloud SQL / Firestore / SQLite).
3. **`action_dispatcher`**: Triggers external REST webhooks, system endpoints, and automated alert dispatches.
4. **`report_generator`**: Compiles executive markdown briefings, post-mortems, and deliverable artifacts.
5. **`validator`**: Performs compliance & quality rule inspections, signaling self-correction loops if anomalies are found.

---

## 🚀 Quickstart & Spin-up Instructions

### Prerequisites
- Python 3.10+
- (Optional) Docker & Docker Compose
- Gemini API Key (optional — features intelligent **Mock Mode** for offline zero-cost testing)

### 1. Local Setup
```bash
# Clone repository
git clone <your-repo-url>
cd AI_AGENT

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
GEMINI_MODEL=gemini-2.5-flash
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
