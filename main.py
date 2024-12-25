import logging
import os
import asyncio
import sqlite3
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import openai
import tiktoken  # Для підрахунку токенів

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

def split_text_by_tokens(text, max_tokens=4000):
    """Розбиває текст на частини, які не перевищують max_tokens."""
    tokenizer = tiktoken.get_encoding("cl100k_base")
    tokens = tokenizer.encode(text)
    chunks = [tokens[i:i + max_tokens] for i in range(0, len(tokens), max_tokens)]
    return [tokenizer.decode(chunk) for chunk in chunks]

# Telegram бот
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Перевірити текст на плагіат"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Привіт! Введіть текст для перевірки на плагіат.", reply_markup=reply_markup)

async def check_plagiarism(update: Update, context: ContextTypes.DEFAULT_TYPE):
    input_text = update.message.text
    logger.info(f"Отримано текст для перевірки: {input_text[:50]}...")

    # Перевірка в базі даних
    cached_result = get_saved_result(input_text)
    if cached_result:
        logger.info("Текст знайдено в базі даних.")
        await update.message.reply_text(f"Результати перевірки з кешу:\n{cached_result[:4000]}")
        return

    # Розбиваємо текст на частини, якщо він перевищує обмеження
    text_chunks = split_text_by_tokens(input_text)

    results = []
    for chunk in text_chunks:
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a plagiarism checker."},
                    {"role": "user", "content": f"Перевір текст на плагіат: {chunk}"}
                ],
                max_tokens=4000
            )
            results.append(response["choices"][0]["message"]["content"].strip())
        except Exception as e:
            logger.error(f"Помилка при перевірці тексту: {str(e)}")
            results.append(f"Помилка при обробці тексту: {str(e)}")

    full_result = "\n".join(results)

    # Збереження в базу даних
    save_result(input_text, full_result)

    # Надсилання результату користувачу
    await update.message.reply_text(full_result[:4000])  # Telegram має обмеження у 4000 символів

# Ініціалізація Telegram Application
application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_plagiarism))

if __name__ == "__main__":
    init_db()  # Ініціалізація бази даних
    logger.info("Запуск бота...")
    asyncio.run(application.run_polling())
