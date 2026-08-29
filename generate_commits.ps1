$ErrorActionPreference = "Stop"

git init

# Commit 1
git add README.md requirements.txt .gitignore .env.example
git commit -m "Initial commit: Project structure, dependencies, and configuration"

# Commit 2
git add Dockerfile docker-compose.yml
git commit -m "ci: Add Docker configuration and containerization setup"

# Commit 3
git add app.py run_server.bat
git commit -m "feat: Implement FastAPI backend and server launcher"

# Commit 4
git add static/style.css static/js/
git commit -m "ui: Add styling and frontend scripts"

# Commit 5
git add static/index.html
git commit -m "ui: Implement Taskmaster dashboard interface"

# Commit 6
git add agent/llm_client.py agent/prompts.py
git commit -m "feat(ai): Implement Gemini SDK client and ReAct prompts"

# Commit 7
git add agent/orchestrator.py
git commit -m "feat(ai): Implement core Taskmaster autonomous orchestrator"

# Commit 8
git add agent/
git commit -m "refactor: Finalize agent pipeline and error handling"

# Commit 9
git add tests/
git commit -m "test: Add comprehensive unit tests for agent logic"

# Commit 10
git add .
git commit -m "chore: Clean up loose files and optimize imports"

git branch -M main

Write-Host "Local repository initialized with 10 commits!"
