import logging
import os
import asyncio
import sqlite3
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Завантаження змінних середовища
load_dotenv()

# Ініціалізація логера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ініціалізація OpenAI API
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY не встановлено!")
client = AsyncOpenAI(api_key=api_key)

# Ініціалізація Telegram Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не встановлено!")

# Ініціалізація бази даних SQLite
db_file = "texts.db"

def init_db():
    """Ініціалізація бази даних SQLite."""
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
    """Перевіряє наявність тексту в базі і повертає результат."""
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT result FROM texts WHERE text = ?", (text,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def save_result(text, result):
    """Зберігає текст і результат у базу."""
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO texts (text, result) VALUES (?, ?)", (text, result))
    conn.commit()
    conn.close()

# Telegram бот
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Перевірити текст на плагіат"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Привіт! Введіть текст для перевірки на плагіат.", reply_markup=reply_markup)

async def check_plagiarism(update: Update, context: ContextTypes.DEFAULT_TYPE):
    input_text = update.message.text
    logger.info(f"Received text for plagiarism check: {input_text[:50]}...")

    # Check in the local database
    saved_result = get_saved_result(input_text)
    if saved_result:
        await update.message.reply_text(f"Result from database:\n{saved_result}")
        return

    try:
        # Request to OpenAI API
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


# Ініціалізація Telegram Application
application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_plagiarism))

if __name__ == "__main__":
    init_db()  # Ініціалізація бази даних
    logger.info("Запуск бота...")
    asyncio.run(application.run_polling())
