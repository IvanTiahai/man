import logging
import os
import asyncio
import sqlite3
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import openai  # Import the OpenAI library
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenAI API
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("OPENAI_API_KEY is not set!")

# Initialize Telegram Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN is not set!")

# Initialize SQLite database
db_file = "texts.db"

def init_db():
    """Initialize SQLite database."""
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS texts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT UNIQUE,
            result TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_saved_result(text):
    """Check if the text exists in the database and return the result."""
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT result FROM texts WHERE text = ?", (text,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def save_result(text, result):
    """Save the text and result to the database."""
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO texts (text, result) VALUES (?, ?)", (text, result))
    conn.commit()
    conn.close()

# Telegram bot handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Check text for plagiarism"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Hello! Please enter the text you'd like to check for plagiarism.", reply_markup=reply_markup)

async def check_plagiarism(update: Update, context: ContextTypes.DEFAULT_TYPE):
    input_text = update.message.text
    logger.info(f"Received text for plagiarism check: {input_text[:50]}...")

    # Check in the local database
    saved_result = get_saved_result(input_text)
    if saved_result:
        await update.message.reply_text(f"Result from database:\n{saved_result}")
        return

    try:
        # Request to OpenAI API using text-davinci-003
        response = openai.Completion.create(
            model="text-davinci-003",
            prompt=f"Check the following text for plagiarism:\n\n{input_text}",
            max_tokens=200,
            temperature=0.0  # Set temperature to 0 for deterministic output
        )
        result = response.choices[0].text.strip()

        # Save the result in the database
        save_result(input_text, result)

        # Send the result to the user
        await update.message.reply_text(f"Plagiarism check result:\n{result}")
    except Exception as e:
        logger.error(f"Error processing text: {e}")
        await update.message.reply_text(f"Error processing text:\n{str(e)}")

# Initialize Telegram Application
application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_plagiarism))

if __name__ == "__main__":
    init_db()  # Initialize the database
    logger.info("Starting the bot...")
    asyncio.run(application.run_polling())
