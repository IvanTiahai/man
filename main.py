import logging
import os
from io import BytesIO
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from transformers import AutoTokenizer, AutoModel
from flask import Flask, request, jsonify
import openai
from sklearn.metrics.pairwise import cosine_similarity
from docx import Document
from PyPDF2 import PdfReader

# Ініціалізація Flask
flask_app = Flask(__name__)

# Ініціалізація OpenAI API
openai.api_key = os.getenv("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")
if not openai.api_key:
    raise ValueError("OPENAI_API_KEY не встановлено!")

# Ініціалізація Telegram Token
TELEGRAM_TOKEN = os.getenv("7959992406:AAE2ZH_NSzrRtVjwBZIdHkw36hPyint3Znw")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не встановлено!")

# Ініціалізація моделі для порівняння текстів
tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/paraphrase-MiniLM-L6-v2")
model = AutoModel.from_pretrained("sentence-transformers/paraphrase-MiniLM-L6-v2")

# Функція для читання PDF
def read_pdf(file) -> str:
    try:
        reader = PdfReader(file)
        text = "".join(page.extract_text() or "" for page in reader.pages)
        return text
    except Exception as e:
        return f"Помилка обробки PDF: {str(e)}"

# Функція для читання DOCX
def read_docx(file) -> str:
    try:
        document = Document(file)
        text = "".join(paragraph.text + "\n" for paragraph in document.paragraphs)
        return text
    except Exception as e:
        return f"Помилка обробки DOCX: {str(e)}"

# Функція для читання TXT
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

# Основний цикл
async def start_bot():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    await application.run_polling()

# Запуск Flask через Uvicorn
if __name__ == "__main__":
    import asyncio
    from uvicorn import Config, Server

    async def main():
        flask_task = asyncio.create_task(Server(Config(app=flask_app, host="0.0.0.0", port=5000)).serve())
        telegram_task = asyncio.create_task(start_bot())
        await asyncio.gather(flask_task, telegram_task)

    asyncio.run(main())
