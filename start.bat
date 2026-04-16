@echo off
echo ========================================
echo   Word Document Generator Service
echo ========================================
echo.

cd /d "%~dp0"

echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Starting service on http://localhost:8000
echo.
echo API Documentation: http://localhost:8000/docs
echo Health Check: http://localhost:8000/health
echo.
echo Press Ctrl+C to stop the service
echo ========================================
echo.

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
