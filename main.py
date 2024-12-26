import logging
import os
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from notion_client import AsyncClient
from dotenv import load_dotenv

# Завантаження змінних середовища
load_dotenv()

# Ініціалізація логера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ініціалізація Notion API
notion_token = os.getenv("NOTION_API_TOKEN")
notion_database_id = os.getenv("NOTION_DATABASE_ID")

if not notion_token:
    raise ValueError("NOTION_API_TOKEN не встановлено!")
if not notion_database_id:
    raise ValueError("NOTION_DATABASE_ID не встановлено!")

notion_client = AsyncClient(auth=notion_token)

# Ініціалізація Telegram Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не встановлено!")

async def save_to_notion(text, result):
    """Зберігає текст та результат у базу даних Notion."""
    try:
        await notion_client.pages.create(
            parent={"database_id": notion_database_id},
            properties={
                "Text": {"title": [{"text": {"content": text}}]},
                "Result": {"rich_text": [{"text": {"content": result}}]},
            },
        )
    except Exception as e:
        logger.error(f"Помилка збереження у Notion: {e}")

async def get_from_notion(text):
    """Перевіряє текст у базі даних Notion та повертає результат."""
    try:
        query = await notion_client.databases.query(
            **{
                "database_id": notion_database_id,
                "filter": {
                    "property": "Text",
                    "rich_text": {"contains": text},
                },
            }
        )
        if query["results"]:
            return query["results"][0]["properties"]["Result"]["rich_text"][0]["text"]["content"]
        return None
    except Exception as e:
        logger.error(f"Помилка отримання даних з Notion: {e}")
        return None

# Telegram бот
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Перевірити текст на плагіат"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Привіт! Введіть текст для перевірки на плагіат.", reply_markup=reply_markup)

async def check_plagiarism(update: Update, context: ContextTypes.DEFAULT_TYPE):
    input_text = update.message.text
    logger.info(f"Отримано текст для перевірки: {input_text[:50]}...")

    # Перевірка у базі Notion
    saved_result = await get_from_notion(input_text)
    if saved_result:
        await update.message.reply_text(f"Результат з бази даних:\n{saved_result}")
        return

    try:
        # Симуляція перевірки (замініть це на ваш API)
        result = f"Перевірка тексту '{input_text}' завершена. Збігів не знайдено."
        await save_to_notion(input_text, result)
        await update.message.reply_text(f"Результат перевірки на плагіат:\n{result}")
    except Exception as e:
        logger.error(f"Помилка при обробці тексту: {e}")
        await update.message.reply_text(f"Помилка при обробці тексту:\n{str(e)}")

# Ініціалізація Telegram Application
application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_plagiarism))

if __name__ == "__main__":
    logger.info("Запуск бота...")
    asyncio.run(application.run_polling())
