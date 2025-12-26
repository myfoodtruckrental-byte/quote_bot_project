import os
from dotenv import load_dotenv

load_dotenv()

"""
Configuration for SQL Accounting Integration
"""

SQL_ACCOUNTING_PATH = r"C:\Program Files (x86)\SQLAccounting\bin\SQLACC.exe"
SQL_ACCOUNTING_DATABASE = r"C:\eStream\SQLAccounting\DB\ACC-0004.FDB"
SQL_ACCOUNTING_USER = "ADMIN"
SQL_ACCOUNTING_PASSWORD = os.getenv("SQL_ACCOUNTING_PASSWORD")
SQL_ACCOUNTING_DCF_PATH = r"C:\eStream\SQLAccounting\Share\Local.DCF"
# --- Telegram Bot Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# --- Google Gemini API Configuration ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
