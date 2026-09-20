@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv" python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if not exist ".env" (
  copy .env.example .env >nul
  echo Created .env. Add GEMINI_API_KEY and TAVILY_API_KEY, then run again.
  pause
  exit /b 1
)
start "Hackathon Intelligence - ADK" cmd /k "cd /d "%~dp0" && call .venv\Scripts\activate.bat && adk web . --host 127.0.0.1 --port 8000"
start "Hackathon Intelligence - API" cmd /k "cd /d "%~dp0" && call .venv\Scripts\activate.bat && uvicorn hackathon_intelligence.api:app --host 127.0.0.1 --port 8080 --reload"
start "Hackathon Intelligence - Streamlit" cmd /k "cd /d "%~dp0" && call .venv\Scripts\activate.bat && streamlit run streamlit_app.py --server.port 8501"
echo ADK: http://127.0.0.1:8000
 echo API: http://127.0.0.1:8080/docs
 echo Streamlit: http://localhost:8501
endlocal
