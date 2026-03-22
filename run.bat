@echo off
cd /d D:\AI_Study\helpdesk_ai
call .\.venv\Scripts\activate
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
pause
