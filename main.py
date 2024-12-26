import logging
import os
import asyncio
import sqlite3
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
from dotenv import load_dotenv

# Завантаження змінних середовища
load_dotenv()

# Ініціалізація логера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ініціалізація OpenAI API
api_key = os.environ['OPENAI_API_KEY']
if not api_key:
    raise ValueError("OPENAI_API_KEY не встановлено!")

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
    logger.info(f"Отримано текст для перевірки: {input_text[:50]}...")

    # Перевірка у локальній базі
    saved_result = get_saved_result(input_text)
    if saved_result:
        await update.message.reply_text(f"Результат з бази даних:\n{saved_result}")
        return

    try:
        # Запит до  API
        response = ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a plagiarism checker."},
                {"role": "user", "content": f"Перевір текст на плагіат: {input_text}"}
            ],
            max_tokens=4000  # Підтримка великих текстів
        )
        result = response["choices"][0]["message"]["content"].strip()

        # Збереження результату у базу
        save_result(input_text, result)

        # Відправлення результату
        await update.message.reply_text(f"Результат перевірки:\n{result}")
    except Exception as e:
        logger.error(f"Помилка при обробці тексту: {e}")
        await update.message.reply_text(f"Помилка при обробці тексту:\n{str(e)}")

# Ініціалізація Telegram Application
application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_plagiarism))

if __name__ == "__main__":
    init_db()  # Ініціалізація бази даних
    logger.info("Запуск бота...")
    asyncio.run(application.run_polling())
