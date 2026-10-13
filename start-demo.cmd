@echo off
rem Starts the FSA Training Hub demo: database, API and front end, each in its own window.
rem Double-click this file, wait about a minute, then open http://localhost:3210
rem Close the three windows to stop the demo. Anything already running is left as it is.

cd /d "%~dp0"

netstat -ano | findstr /r /c:":5433 .*LISTENING" >nul
if errorlevel 1 (
  start "Training Hub - database" cmd /k "cd /d "%~dp0tools\devdb" && npm start"
  timeout /t 8 /nobreak >nul
) else (
  echo Database already running on port 5433.
)

netstat -ano | findstr /r /c:":8210 .*LISTENING" >nul
if errorlevel 1 (
  start "Training Hub - API" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python manage.py runserver 127.0.0.1:8210"
) else (
  echo API already running on port 8210.
)

netstat -ano | findstr /r /c:":3210 .*LISTENING" >nul
if errorlevel 1 (
  start "Training Hub - web" cmd /k "cd /d "%~dp0web" && npm run dev"
) else (
  echo Front end already running on port 3210.
)

echo.
echo Starting. Open http://localhost:3210 in about a minute.
echo Sign-in details are in demo-logins.txt in this folder.
timeout /t 5 >nul
