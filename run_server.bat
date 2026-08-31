@echo off
echo =========================================================
echo  Starting Taskmaster Autonomous Agent Control Center...
echo =========================================================
echo.
echo Local URL:   http://localhost:8000/chat
echo Network URL: http://172.25.248.209:8000/chat
echo Swagger Docs: http://localhost:8000/docs
echo.
.\venv\Scripts\python.exe app.py
pause
