import logging
import os
import asyncio
import sqlite3
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import openai

# Ініціалізація логера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ініціалізація OpenAI API
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("OPENAI_API_KEY не встановлено!")

# Ініціалізація Telegram Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не встановлено!")

# Ініціалізація бази даних
conn = sqlite3.connect("texts.db", check_same_thread=False)
cursor = conn.cursor()

# Створення таблиці для текстів
cursor.execute("""
CREATE TABLE IF NOT EXISTS texts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    text TEXT,
    result TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# Функція для збереження тексту в базу даних
def save_text(chat_id, text, result=None):
    cursor.execute("INSERT INTO texts (chat_id, text, result) VALUES (?, ?, ?)", (chat_id, text, result))
    conn.commit()

# Функція для пошуку збігу тексту
def find_match(text):
    cursor.execute("SELECT * FROM texts WHERE text = ?", (text,))
    return cursor.fetchone()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Перевірити текст на плагіат"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Привіт! Введіть текст для перевірки на плагіат.", reply_markup=reply_markup)

# Перевірка тексту на плагіат
async def check_plagiarism(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    input_text = update.message.text
    logger.info(f"Отримано текст від {chat_id}: {input_text[:50]}...")

    # Перевірка на наявність у базі
    match = find_match(input_text)
    if match:
        await update.message.reply_text(f"Текст уже перевірено раніше:\n{match[3]}")
        return

    # Перевірка тексту через OpenAI API
    try:
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=f"Перевір текст на плагіат: {input_text}",
            max_tokens=150
        )
        result = response["choices"][0]["text"].strip()
    except Exception as e:
        logger.error(f"Помилка перевірки через OpenAI API: {e}")
        result = f"Помилка перевірки через API: {e}"

    # Збереження тексту та результату в базу
    save_text(chat_id, input_text, result)
    await update.message.reply_text(result[:4000])  # Telegram має обмеження на 4000 символів

# Ініціалізація Telegram Application
application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_plagiarism))

if __name__ == "__main__":
    # Запуск бота з використанням long polling
    application.run_polling()
