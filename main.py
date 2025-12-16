import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
import os
from dotenv import load_dotenv
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, PicklePersistence

from config import GEMINI_API_KEY, TELEGRAM_BOT_TOKEN
from bot.handlers import (
    start_command, handle_text, handle_photo, master_callback_handler, reprint_log_command
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

genai.configure(api_key=GEMINI_API_KEY)

def main() -> None:
    """Initializes and runs the Telegram bot."""
    # Create a persistence object
    persistence = PicklePersistence(filepath="persistence.pkl")

    # Build the application with persistence
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).persistence(persistence).build()

    # Command and Message Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("reprintlog", reprint_log_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # A single, master callback query handler
    application.add_handler(CallbackQueryHandler(master_callback_handler))

    print("Ambient Bot (refactored) is running in polling mode...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
