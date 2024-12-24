import logging
import os
import asyncio
from io import BytesIO
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from transformers import AutoTokenizer, AutoModel
from flask import Flask, request, jsonify, abort
import openai
import torch
from sklearn.metrics.pairwise import cosine_similarity
from docx import Document  # Для роботи з DOCX
import nest_asyncio
from gunicorn.app.base import BaseApplication  # Для продакшн-сервера

# Ініціалізація Nest Asyncio
nest_asyncio.apply()

# Ініціалізація Flask
flask_app = Flask(__name__)

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

# Головний маршрут для перевірки роботи сервера
@flask_app.route("/")
def home():
    return "Сервер працює успішно!", 200

# Маршрут для отримання запитів вебхука
@flask_app.route("/telegram-webhook", methods=["POST"])
def webhook():
    if request.method == "POST":
        json_update = request.get_json()
        application.update_queue.put(json_update)
        return "OK", 200

# Ініціалізація моделі для порівняння текстів
tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/paraphrase-MiniLM-L6-v2")
model = AutoModel.from_pretrained("sentence-transformers/paraphrase-MiniLM-L6-v2")

# Обмеження розміру файлу для Flask
@flask_app.before_request
def limit_file_size():
    if request.content_length and request.content_length > 16 * 1024 * 1024:  # 16 MB
        abort(413, description="Файл занадто великий.")

# Функції для читання файлів
def read_pdf(file) -> str:
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(file)
        text = "".join(page.extract_text() or "" for page in reader.pages)
        return text
    except Exception as e:
        return f"Помилка обробки PDF: {str(e)}"

def read_docx(file) -> str:
    try:
        document = Document(file)
        text = "".join(paragraph.text + "\n" for paragraph in document.paragraphs)
        return text
    except Exception as e:
        return f"Помилка обробки DOCX: {str(e)}"

def read_txt(file) -> str:
    try:
        return file.read().decode("utf-8")
    except Exception as e:
        return f"Помилка обробки TXT: {str(e)}"

# Flask маршрут для завантаження файлів
@flask_app.route('/upload/', methods=['POST'])
def upload_file():
    try:
        file = request.files['file']
        file_ext = os.path.splitext(file.filename)[-1].lower()
        buffer = BytesIO(file.read())  # Зберігаємо файл в пам'яті

        if file_ext == ".pdf":
            text = read_pdf(buffer)
        elif file_ext == ".txt":
            text = buffer.getvalue().decode("utf-8")
        elif file_ext == ".docx":
            text = read_docx(buffer)
        else:
            return jsonify({"detail": "Формат файлу не підтримується"}), 400

        return jsonify({"filename": file.filename, "content": text[:1000]})
    except Exception as e:
        return jsonify({"detail": f"Помилка: {str(e)}"}), 500

# Telegram бот
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Текстове повідомлення", "Текстовий документ"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Привіт! Виберіть тип задачі:", reply_markup=reply_markup)

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Ви написали: {update.message.text}")

# Основний цикл
async def main():
    global application
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    await application.bot.delete_webhook()
    await application.bot.set_webhook(WEBHOOK_URL + "/telegram-webhook")

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    port = int(os.getenv("PORT", 5000))  # Порт для сервера
    flask_app.run(host="0.0.0.0", port=port, threaded=True)

# Запуск через Gunicorn
class FlaskAppWrapper(BaseApplication):
    def __init__(self, app, options=None):
        self.app = app
        self.options = options or {}
        super().__init__()

    def load_config(self):
        for key, value in self.options.items():
            self.cfg.set(key, value)

    def load(self):
        return self.app

if __name__ == "__main__":
    options = {
        "bind": f"0.0.0.0:{os.getenv('PORT', '5000')}",
        "workers": 4,
    }
    FlaskAppWrapper(flask_app, options).run()
