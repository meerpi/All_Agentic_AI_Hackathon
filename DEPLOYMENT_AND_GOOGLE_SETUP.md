# 🚀 Taskmaster Autonomous Agent — Google Cloud Deployment & Credentials Setup Guide

> **Hackathon Edition**: This guide provides the fast-track setup instructions to deploy and host the **Taskmaster Autonomous Agent Engine** on Google Cloud (Cloud Run or Compute Engine VM) and connect it to Google Workspace APIs (Docs, Sheets, Calendar, Gmail, YouTube).

---

## 📌 1. Why Are These Credentials Needed?

Taskmaster is an **autonomous execution engine** that performs real-world actions across Google Workspace services. To interact with your account safely, it relies on standard Google OAuth 2.0 and API authentication:

| File / Credential | What It Is | Why It Is Needed |
|---|---|---|
| **`GEMINI_API_KEY`** | Google AI Studio API Key | Powers the multi-role LLM planning, self-correction, data extraction, and executive report synthesis. |
| **`credentials.json`** | OAuth 2.0 Client ID & Secret | Identifies your application to Google APIs so Google knows who is requesting permission. |
| **`token.json`** | Authorized User Session & Refresh Token | Contains the cryptographic OAuth grant from the user. This allows cloud servers (which have no interactive browser display) to read Gmail, create Google Docs, write to Google Sheets, and query Google Calendar **headlessly without prompting for login popups**. |

---

## ⚡ 2. The Hackathon Fast-Track (Testing Mode)

In production, Google requires domain verification and security reviews for sensitive scopes like Gmail and Google Drive. 

For hackathons, Google provides **Testing Mode**:
- **Zero app verification required**.
- **Zero domain verification required**.
- Works instantly for any email addresses added as **Test Users**.

---

## 🛠️ 3. Step-by-Step Setup Instructions

### Step 1: Create a Google Cloud Project & Enable APIs

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Click the project dropdown at the top navigation bar and select **"New Project"**.
   - Project Name: `taskmaster-agent` (or any name).
   - Click **Create**.
3. In the search bar at the top, search for and **Enable** each of the following 6 APIs:
   - 📄 **Google Docs API**
   - 📊 **Google Sheets API**
   - 📅 **Google Calendar API**
   - 📧 **Gmail API**
   - 🎬 **YouTube Data API v3**
   - 🤖 **Generative Language API** (for Gemini models)

---

### Step 2: Configure OAuth Consent Screen

1. Go to **APIs & Services** ➔ **[OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent)**.
2. Select **External** user type and click **Create**.
3. **App Information**:
   - **App name**: `Taskmaster AI`
   - **User support email**: Enter your email address.
   - **Developer contact email**: Enter your email address.
   - Click **Save and Continue**.
4. **Scopes**:
   - Click **Add or Remove Scopes**.
   - Select the following scopes:
     - `https://www.googleapis.com/auth/documents`
     - `https://www.googleapis.com/auth/spreadsheets`
     - `https://www.googleapis.com/auth/calendar`
     - `https://www.googleapis.com/auth/gmail.modify` (or `gmail.readonly` + `gmail.send`)
     - `https://www.googleapis.com/auth/drive`
     - `https://www.googleapis.com/auth/youtube`
   - Click **Update** ➔ **Save and Continue**.
5. **Test Users** *(⚠️ Crucial Step)*:
   - Under **Test users**, click **+ Add Users**.
   - Add your Google email address (and any teammate email addresses who will test the demo).
   - Click **Save and Continue**.

---

### Step 3: Generate `credentials.json` (OAuth Client ID)

1. Go to **APIs & Services** ➔ **[Credentials](https://console.cloud.google.com/apis/credentials)**.
2. Click **+ Create Credentials** at the top ➔ select **OAuth client ID**.
3. In the **Application type** dropdown, select **Desktop app**.
   - Name: `Taskmaster Desktop Client`
   - Click **Create**.
4. A modal will pop up with your client details. Click **Download JSON**.
5. Rename the downloaded file to `credentials.json` and place it in the root directory of the project:
   ```bash
   mv ~/Downloads/client_secret_*.json ./credentials.json
   ```

---

### Step 4: Generate `token.json` (One-Time Local Authorization)

Cloud containers and remote servers cannot open a desktop browser window for OAuth login. Therefore, generate the token **once locally on your laptop** before deploying:

1. Clone the repository and navigate into it:
   ```bash
   git clone https://github.com/Tejas-Ranjeet/All_Agentic_AI_Hackathon.git
   cd All_Agentic_AI_Hackathon
   ```
2. Put `credentials.json` in the root folder.
3. Install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
4. Run the one-time authorization command:
   ```bash
   python3 -c "from agent.tools.google_auth import get_google_credentials; get_google_credentials()"
   ```
5. Your default web browser will open:
   - Choose the Google account you added as a **Test User** in Step 2.
   - Click **"Continue"** (or click *Advanced ➔ Go to Taskmaster AI (unsafe)*).
   - Allow the permissions.
6. The terminal will output:
   ```text
   Google OAuth consent completed successfully.
   ```
7. A `token.json` file will now be generated in your project root. **Keep this file alongside `credentials.json`**.

---

### Step 5: Get a Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Click **Create API Key**.
3. Select your Google Cloud project (or generate a default key).
4. Copy the key for your `.env` file.

---

### Step 6: Create Your `.env` File

Create a `.env` file in the project root:

```ini
# ==========================================
# Taskmaster Autonomous Agent Configuration
# ==========================================

# Gemini API Keys (from aistudio.google.com)
GEMINI_API_KEY=AIzaSyYourActualKeyHere
GEMINI_BACKUP_API_KEY=  # Optional backup key for high-availability failover

# Model Architecture
GEMINI_MODEL=gemini-3.5-flash
MAIN_MODEL=gemini-3.5-flash
RESEARCH_MODEL=gemini-3.1-flash-lite
FALLBACK_MODEL=gemini-3.6-flash
MOCK_GEMINI=false

# Server Settings
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO

# Autonomous Browser Configuration (Set true for cloud deployment)
BROWSER_HEADLESS=true
BROWSER_TIMEOUT_MS=30000

# Optional External Integrations (Leave blank if not used)
SLACK_WEBHOOK_URL=
SLACK_BOT_TOKEN=
JIRA_BASE_URL=
JIRA_EMAIL=
JIRA_API_TOKEN=
JIRA_PROJECT_KEY=
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
```

---

## ☁️ 4. Deploying to Google Cloud

### Option A: Deploy to Google Cloud Run (Recommended — Serverless Container)

1. Make sure your local folder contains:
   - `credentials.json`
   - `token.json`
   - `.env`
   - `Dockerfile`
2. Ensure your `Dockerfile` installs Chromium for Playwright web scraping:
   ```dockerfile
   FROM python:3.12-slim
   ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
   WORKDIR /app
   RUN apt-get update && apt-get install -y --no-install-recommends curl \
       && rm -rf /var/lib/apt/lists/*
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   RUN python -m playwright install --with-deps chromium
   COPY . .
   ENV PORT=8080
   EXPOSE $PORT
   CMD uvicorn app:app --host 0.0.0.0 --port $PORT
   ```
3. Deploy using the Google Cloud CLI (`gcloud`):
   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID

   gcloud run deploy taskmaster-agent \
     --source . \
     --platform managed \
     --region us-central1 \
     --allow-unauthenticated \
     --memory 2Gi \
     --cpu 2 \
     --timeout 300s \
     --set-env-vars BROWSER_HEADLESS=true
   ```
4. `gcloud` will provide a public HTTPS URL: `https://taskmaster-agent-xxxx.a.run.app`.

---

### Option B: Deploy to a Google Compute Engine (GCE) VM

1. In the GCP Console, go to **Compute Engine** ➔ **VM instances** ➔ **Create instance**.
   - Machine Type: `e2-standard-2` (2 vCPUs, 8 GB RAM).
   - Boot Disk: Ubuntu 24.04 LTS (25 GB disk).
   - Firewall: Check **Allow HTTP traffic** and **Allow HTTPS traffic**.
2. SSH into the VM:
   ```bash
   sudo apt update && sudo apt install -y python3-pip python3-venv git
   git clone https://github.com/Tejas-Ranjeet/All_Agentic_AI_Hackathon.git
   cd All_Agentic_AI_Hackathon
   
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   python3 -m playwright install --with-deps chromium
   ```
3. Copy your `credentials.json`, `token.json`, and `.env` files into the VM directory.
4. Start the application:
   ```bash
   nohup uvicorn app:app --host 0.0.0.0 --port 8000 > taskmaster.log 2>&1 &
   ```
5. Open your browser to `http://<VM_EXTERNAL_IP>:8000`.

---

## 🔍 5. Verification & Testing

Once running, verify that all services and tools are operational:

1. **Health Check**:
   ```bash
   curl -s http://localhost:8000/api/health
   ```
   *Expected Response:*
   ```json
   {
     "status": "HEALTHY",
     "registered_tools_count": 16,
     "mock_mode": false
   }
   ```

2. **Open the Agent Chat Workspace**:
   - Navigate to `http://localhost:8000/chat` (or `https://<your-cloud-run-url>/chat`).
   - Interact directly with the autonomous agent to execute real-world tasks:
     - 📄 **Google Docs**: Creates a live Google Doc on your Google Drive.
     - 📊 **Google Sheets**: Creates a spreadsheet with sample rows on Google Drive.
     - 📅 **Calendar**: Fetches upcoming events from your calendar.
     - 📧 **Gmail**: Reads recent emails from your inbox.
     - 🌐 **Web Scraping & Browser**: Drives live browser sessions and synthesizes content.

---

## 🛡️ Security Note

- **Never commit `credentials.json`, `token.json`, or `.env` to public GitHub repositories.**
- These files are already listed in `.gitignore` to prevent accidental credential leaks.
