import logging
import os
import threading
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from transformers import AutoTokenizer, AutoModel
from flask import Flask, request, jsonify
from werkzeug.exceptions import HTTPException
from PyPDF2 import PdfReader
from docx import Document as DocxDocument
import openai
import torch
from sklearn.metrics.pairwise import cosine_similarity
import sys

# Ініціалізація Flask
flask_app = Flask(__name__)

# Ініціалізація OpenAI API
openai.api_key = "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"  # Замініть на ваш ключ OpenAI

# Ініціалізація моделі для порівняння текстів
tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/paraphrase-MiniLM-L6-v2")
model = AutoModel.from_pretrained("sentence-transformers/paraphrase-MiniLM-L6-v2")

# Функція для читання PDF-файлу
def read_pdf(file) -> str:
    try:
        reader = PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""  # Перевірка на наявність тексту
        return text
    except Exception as e:
        raise HTTPException(f"Помилка обробки PDF: {str(e)}")

# Функція для читання DOCX-файлу
def read_docx(file) -> str:
    try:
        doc = DocxDocument(file)
        text = ""
        for para in doc.paragraphs:
            text += para.text + "\n"
        return text
    except Exception as e:
        raise HTTPException(f"Помилка обробки DOCX: {str(e)}")

# Функція для читання TXT-файлу
def read_txt(file) -> str:
    try:
        text = file.read().decode("utf-8")
        return text
    except Exception as e:
        raise HTTPException(f"Помилка обробки TXT: {str(e)}")

# Маршрут для завантаження документів через Flask
@flask_app.route('/upload/', methods=['POST'])
def upload_file():
    file = request.files['file']
    file_ext = os.path.splitext(file.filename)[-1].lower()

    # Перевірка формату файлу
    if file_ext == ".pdf":
        text = read_pdf(file)
    elif file_ext == ".txt":
        text = read_txt(file)
    elif file_ext == ".docx":
        text = read_docx(file)
    else:
        return jsonify({"detail": "Формат файлу не підтримується. Завантажте PDF, DOCX або TXT."}), 400

    # Повернення частини тексту
    return jsonify({
        "filename": file.filename,
        "content": text[:1000]  # Перша частина тексту (для тестування)
    })

# Функція для порівняння схожості текстів
def compare_texts(text1: str, text2: str) -> float:
    # Токенізація текстів
    inputs = tokenizer([text1, text2], padding=True, truncation=True, return_tensors="pt")

    # Отримання векторних представлень
    with torch.no_grad():
        embeddings = model(**inputs).last_hidden_state.mean(dim=1)  # Середнє по всіх токенах для кожного тексту

    # Обчислення косинусної схожості
    similarity = cosine_similarity(embeddings[0].numpy().reshape(1, -1), embeddings[1].numpy().reshape(1, -1))
    return similarity[0][0]

# Функція для запиту до GPT для перевірки плагіату
async def ask_gpt(prompt: str) -> str:
    try:
        # Використання OpenAI API для запиту до GPT-4
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "system", "content": "You are a plagiarism detection assistant."},
                      {"role": "user", "content": prompt}]
        )
        return response['choices'][0]['message']['content']
    except Exception as e:
        return f"Помилка під час звернення до OpenAI: {e}"

# Функція перевірки тексту на плагіат через GPT
async def check_for_plagiarism_with_gpt(input_text: str) -> str:
    prompt = f"Чи схожий цей текст на будь-який із відомих? Текст: {input_text}"
    result = await ask_gpt(prompt)
    return f"Результат GPT:\n{result}"

# Функція для команди /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Кнопки для вибору типу задачі
    keyboard = [
        ["Текстове повідомлення", "Текстовий документ"]
    ]
    
    # Визначення розмітки клавіатури
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    # Надсилаємо користувачу вітальне повідомлення з кнопками
    await update.message.reply_text(
        "Привіт! Виберіть тип задачі:",
        reply_markup=reply_markup
    )

# Функція для обробки вибору користувача
async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_choice = update.message.text
    
    if user_choice == "Текстове повідомлення":
        await update.message.reply_text("Надішліть текст для перевірки на плагіат.")
    elif user_choice == "Текстовий документ":
        await update.message.reply_text("Надішліть файл (PDF, DOCX, TXT) для перевірки на плагіат.")
    else:
        await update.message.reply_text("Будь ласка, виберіть одну з опцій: 'Текстове повідомлення' або 'Текстовий документ'.")

# Функція обробки тексту від користувача
async def check_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_text = update.message.text
    # Перевіряємо текст на плагіат через GPT
    result = await check_for_plagiarism_with_gpt(user_text)
    await update.message.reply_text(result)

# Функція для обробки документів, надісланих користувачем
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    file = await context.bot.get_file(update.message.document.file_id)
    file_ext = os.path.splitext(file.file_path)[-1].lower()

    # Завантаження документу
    await file.download("user_document" + file_ext)
    
    # Читання документа відповідно до його формату
    if file_ext == ".pdf":
        with open("user_document.pdf", "rb") as f:
            document_text = read_pdf(f)
    elif file_ext == ".txt":
        with open("user_document.txt", "rb") as f:
            document_text = read_txt(f)
    elif file_ext == ".docx":
        with open("user_document.docx", "rb") as f:
            document_text = read_docx(f)
    else:
        document_text = "Невідомий формат файлу."

    # Перевірка на плагіат через GPT
    result = await check_for_plagiarism_with_gpt(document_text)
    await update.message.reply_text(result)

# Основна функція для запуску бота
async def run_telegram_bot():
    application = ApplicationBuilder().token("7959992406:AAE2ZH_NSzrRtVjwBZIdHkw36hPyint3Znw").build()  # Замініть на ваш токен бота
    application.add_handler(CommandHandler("start", start))

    # Додаємо хендлер для вибору користувача
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_choice))

    # Додаємо хендлер для текстових повідомлень
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_text))

    # Додаємо хендлер для документів
    application.add_handler(MessageHandler(filters.Document.ALL, document_handler))

    # Запускаємо бота
    await application.run_polling()

# Функція для запуску Flask сервера
def run_flask():
    flask_app.run(debug=True, use_reloader=False)

# Основний блок запуску
if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    import nest_asyncio
    nest_asyncio.apply()

    # Запуск Flask сервера в окремому потоці
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # Запуск Telegram бота в уже існуючому event loop
    asyncio.run(run_telegram_bot())

