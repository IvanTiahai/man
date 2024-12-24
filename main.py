import logging
import os
import asyncio
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

# URL для вебхуків
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Наприклад, https://ваш-домен.com/telegram-webhook
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL не встановлено!")

# Telegram бот
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Перевірити текст на плагіат"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Привіт! Введіть текст для перевірки на плагіат.", reply_markup=reply_markup)

async def check_plagiarism(update: Update, context: ContextTypes.DEFAULT_TYPE):
    input_text = update.message.text
    logger.info(f"Отримано текст для перевірки: {input_text[:50]}...")

    paragraphs = input_text.split("\n\n")
    results = []

    for paragraph in paragraphs:
        if len(paragraph.strip()) > 10:  # Ігноруємо короткі фрагменти
            try:
                response = openai.Completion.create(
                    engine="text-davinci-003",
                    prompt=f"Перевір текст на плагіат: {paragraph}",
                    max_tokens=150
                )
                results.append({
                    "paragraph": paragraph,
                    "result": response["choices"][0]["text"].strip()
                })
            except Exception as e:
                results.append({
                    "paragraph": paragraph,
                    "result": f"Помилка: {str(e)}"
                })

    # Формування звіту
    report = "Результати перевірки на плагіат:\n"
    for result in results:
        report += f"Фрагмент: {result['paragraph'][:50]}...\nРезультат: {result['result']}\n\n"

    # Надсилання результату користувачу
    await update.message.reply_text(report[:4000])  # Telegram має обмеження у 4000 символів

# Ініціалізація Telegram Application    
application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_plagiarism))

# Асинхронне встановлення вебхука
async def setup_webhook():
    await application.bot.set_webhook(WEBHOOK_URL)

if __name__ == "__main__":
    asyncio.run(setup_webhook())
    logger.info("Telegram бот запущено!")
