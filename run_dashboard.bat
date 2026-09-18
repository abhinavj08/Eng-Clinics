@echo off
echo ================================================================
echo  AI-Based Solar Power Forecasting ^& Anomaly Detection
echo  Chandigarh Engineering College, CGC University Mohali
echo ================================================================
echo.
echo [1/2] Installing dependencies...
python -m pip install -r requirements.txt --quiet
echo.
echo [2/2] Launching dashboard...
cd python_app
python -m streamlit run app.py
pause
