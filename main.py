import logging
import os
import asyncio
import sqlite3
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import openai
from dotenv import load_dotenv
import aiohttp
import textdistance

# Завантаження змінних середовища
load_dotenv()

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

def normalize_text(text):
    """Нормалізація тексту для точного порівняння."""
    return " ".join(text.split()).lower()

def get_saved_result(text):
    text = normalize_text(text) # Нормалізація тексту
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT result FROM texts WHERE text = ?", (text,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def save_result(text, result):
    """Зберігає текст і результат у базу."""
    text = normalize_text(text) # Нормалізація тексту
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO texts (text, result) VALUES (?, ?)", (text, result))
    conn.commit()
    conn.close()

def find_similar_texts(input_text):
    """Знаходить схожі тексти в базі даних."""
    input_text = normalize_text(input_text)
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT text, result FROM texts")
    all_texts = cursor.fetchall()
    conn.close()

    similar_texts = []
    for saved_text, saved_result in all_texts:
        similarity = textdistance.jaro_winkler.normalized_similarity(input_text, saved_text)
        if similarity > 0.7:  # Поріг схожості
            similar_texts.append((saved_text, similarity, saved_result))
    return similar_texts


# Telegram бот
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Перевірити текст на плагіат"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Привіт! Введіть текст для перевірки на плагіат.", reply_markup=reply_markup)

openai_api_available = True #якщо ліміт вичерпано зберігаємо у змінній

async def check_plagiarism(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global openai_api_available
    input_text = update.message.text
    logger.info(f"Отримано текст для перевірки: {input_text[:50]}...")

    # Перевірка у локальній базі
    saved_result = get_saved_result(input_text)
    if saved_result:
        await update.message.reply_text(f"Результат з бази даних:\n{saved_result}")
        return

    # Результати перевірки
    results = []

    # Перевірка схожих текстів б локальній базі даних
    try:
        similar_texts = find_similar_texts(input_text)  # Використовуємо функцію пошуку схожих текстів
        if similar_texts:
            results.append("Схожі тексти в базі:")
            for saved_text, similarity, saved_result in similar_texts:
                results.append(
                    f"Текст: {saved_text}\nСхожість: {similarity:.2f}\nРезультат: {saved_result}"
                )
        else:
            results.append("У базі не знайдено схожих текстів.")
    except Exception as e:
        logger.error(f"Помилка при пошуку схожих текстів: {e}")
        results.append(f"Помилка при пошуку схожих текстів: {str(e)}")

    # 1. Перевірка через Google
    try:
        query = "+".join(input_text.split()[:10])  # Використання перших 10 слів для пошуку
        search_url = f"https://www.google.com/search?q={query}"

        async with aiohttp.ClientSession() as session:
            async with session.get(search_url, headers={"User-Agent": "Mozilla/5.0"}) as response:
                if response.status == 200:
                    html_content = await response.text()

                    # Проста перевірка наявності результатів
                    if "Результати пошуку" in html_content or "Search Results" in html_content:
                        google_result = f"Ймовірно, текст або його частини можуть бути знайдені у пошукових системах. Спробуйте перевірити це за посиланням: {search_url}"
                    else:
                        google_result = "Текст унікальний або результати не знайдені."

                    results.append(f"Google: {google_result}")
                else:
                    results.append(f"Помилка доступу до Google: {response.status}")
    except Exception as e:
        logger.error(f"Помилка при перевірці через Google: {e}")
        results.append(f"Помилка при перевірці через Google: {str(e)}")

    # 2. Перевірка через OpenAI API
    if openai_api_available:
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",  # Використовуйте безкоштовну модель
                messages=[
                    {"role": "system", "content": "You are a plagiarism checker."},
                    {"role": "user", "content": f"Перевір текст на плагіат: {input_text}"}
                ],
                max_tokens=1000
            )
            openai_result = response["choices"][0]["message"]["content"].strip()
            results.append(f"OpenAI: {openai_result}")
        except Exception as e:
            logger.error(f"Помилка при перевірці через OpenAI: {e}")
            results.append(f"Помилка при перевірці через OpenAI: {str(e)}")
            if "quota" in str(e).lower():
                openai_api_available = False
    else:
        results.append("OpenAI API недоступний через вичерпаний ліміт.")
    # 3. Перевірка за допомогою TextDistance
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT text, result FROM texts")
        all_texts = cursor.fetchall()
        conn.close()

        similarity_results = []
        for saved_text, saved_result in all_texts:
            # Розрахунок схожості
            similarity = textdistance.jaro_winkler.normalized_similarity(input_text, saved_text)
            if similarity > 0.7:  # Встановлюємо поріг схожості
                similarity_results.append(
                    f"Збіг знайдено з текстом:\n'{saved_text}'\n(Схожість: {similarity:.2f})\nРезультат збереженої перевірки:\n{saved_result}"
                )
        
        if similarity_results:
            results.append("TextDistance:\n" + "\n\n".join(similarity_results))
        else:
            results.append("TextDistance: Збігів у базі даних не знайдено.")
    except Exception as e:
        logger.error(f"Помилка при перевірці через TextDistance: {e}")
        results.append(f"Помилка при перевірці через TextDistance: {str(e)}")


    # Збереження результатів у базу
    final_result = "\n\n".join(results)
    save_result(input_text, final_result)

    # Відправлення результату
    await update.message.reply_text(f"Результати перевірки:\n{final_result}")


# async def check_plagiarism(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     input_text = update.message.text
#     logger.info(f"Отримано текст для перевірки: {input_text[:50]}...")

#     # Перевірка у локальній базі
#     saved_result = get_saved_result(input_text)
#     if saved_result:
#         await update.message.reply_text(f"Результат з бази даних:\n{saved_result}")
#         return

#     try:
#         # Запит до OpenAI API
#         response = openai.ChatCompletion.create(
#             model="gpt-4",
#             messages=[
#                 {"role": "system", "content": "You are a plagiarism checker."},
#                 {"role": "user", "content": f"Перевір текст на плагіат: {input_text}"}
#             ],
#             max_tokens=4000  # Підтримка великих текстів
#         )
#         result = response["choices"][0]["message"]["content"].strip()

#         # Збереження результату у базу
#         save_result(input_text, result)

#         # Відправлення результату
#         await update.message.reply_text(f"Результат перевірки:\n{result}")
#     except Exception as e:
#         logger.error(f"Помилка при обробці тексту: {e}")
#         await update.message.reply_text(f"Помилка при обробці тексту:\n{str(e)}")

# Ініціалізація Telegram Application
application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_plagiarism))

if __name__ == "__main__":
    init_db()  # Ініціалізація бази даних
    logger.info("Запуск бота...")
    asyncio.run(application.run_polling())
