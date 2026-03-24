import os
import asyncio
import logging
import json
from aiohttp import ClientSession
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ========== ХРАНЕНИЕ СОСТОЯНИЙ ==========
# Для каждого chat_id храним флаг "ожидание вопроса"
waiting_for_question = {}

# ========== ТЕКСТЫ ДЛЯ РАЗДЕЛОВ ==========
CONSTITUTION_TEXT = """📜 *Конституция Республики Келарион* (основные статьи)

*Статья 1.* Республика Келарион — суверенное виртуальное государство.
*Статья 2.* Территория: Discord, Telegram, сайт и другие официальные платформы.
*Статья 3.* Гражданство — цифровая идентичность, не заменяет гражданство реальных стран.
*Статья 7.* Равенство прав.
*Статья 8.* Свобода слова (без пропаганды насилия и оскорблений).
*Статья 9.* Неприкосновенность частной цифровой жизни.
*Статья 10.* Право на участие в управлении (выборы, референдумы).

Полный текст: kelarion.netlify.app"""

CRIMINAL_CODE_TEXT = """⚖️ *Уголовный кодекс* (основные наказания)

*Виды наказаний:*
• Предупреждение
• Штраф (10–1000 кредитов)
• Временный бан (1 день – 6 месяцев)
• Лишение гражданства (1 месяц – 5 лет)
• Перманентный бан (цифровая казнь)

*Некоторые статьи:*
• Ст. 32–33: оскорбление, клевета
• Ст. 35: нарушение приватности
• Ст. 38–39: кража, мошенничество
• Ст. 56–57: взлом, вредоносный код
• Ст. 67: фальшивомонетничество

Полный текст: kelarion.netlify.app"""

CITIZENSHIP_TEXT = """🪪 *Как стать гражданином*

1. Присоединитесь к официальному Discord-серверу
2. Заполните анкету на сайте kelarion.netlify.app
3. Пройдите верификацию и тест
4. Получите роль | Citizen |

Анкета и подробности: kelarion.netlify.app"""

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С TELEGRAM API ==========
async def send_message(chat_id, text, keyboard=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if keyboard:
        payload["reply_markup"] = keyboard
    async with ClientSession() as session:
        await session.post(url, json=payload)

async def send_typing(chat_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendChatAction"
    async with ClientSession() as session:
        await session.post(url, json={"chat_id": chat_id, "action": "typing"})

def main_keyboard():
    """Клавиатура главного меню"""
    return {
        "keyboard": [
            [{"text": "📜 Конституция"}],
            [{"text": "⚖️ Уголовный кодекс"}],
            [{"text": "🪪 Гражданство"}],
            [{"text": "❓ Другой вопрос"}]
        ],
        "resize_keyboard": True
    }

# ========== ОБРАБОТЧИКИ ==========
async def handle_start(chat_id):
    await send_message(
        chat_id,
        "👋 *Добро пожаловать в Республику Келарион!*\n\n"
        "Я — официальный помощник. Выберите раздел или задайте вопрос.",
        keyboard=main_keyboard()
    )

async def handle_other_question(chat_id):
    waiting_for_question[chat_id] = True
    await send_message(
        chat_id,
        "❓ Напишите ваш вопрос, и я постараюсь ответить на основе законов Келариона.\n"
        "Чтобы вернуться в меню, отправьте /start",
        keyboard=main_keyboard()
    )

async def handle_custom_question(chat_id, question_text):
    # Удаляем флаг ожидания
    waiting_for_question.pop(chat_id, None)

    # Показываем, что бот печатает
    await send_typing(chat_id)

    # Формируем промпт (можно тот же SYSTEM_PROMPT, что и ранее)
    system_prompt = """Ты — официальный юридический помощник Республики Келарион.
Отвечай кратко, по делу, на основе Конституции и Уголовного кодекса Келариона.
Если не знаешь — скажи: «В законодательстве это не урегулировано». Не придумывай процедур.
Полные законы на сайте kelarion.netlify.app"""

    try:
        async with ClientSession() as session:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": question_text}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 1000
                }
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    answer = data["choices"][0]["message"]["content"]
                    await send_message(chat_id, answer, keyboard=main_keyboard())
                else:
                    await send_message(chat_id, "⚠️ Ошибка API. Попробуйте позже.", keyboard=main_keyboard())
    except Exception as e:
        logger.error(f"Ошибка Groq: {e}")
        await send_message(chat_id, "⚠️ Техническая ошибка. Попробуйте позже.", keyboard=main_keyboard())

# ========== ОСНОВНОЙ ЦИКЛ ==========
updates_queue = asyncio.Queue()
last_update_id = 0

async def get_updates():
    global last_update_id
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"offset": last_update_id + 1, "timeout": 30}
    async with ClientSession() as session:
        async with session.get(url, params=params) as resp:
            data = await resp.json()
            if data.get("ok"):
                for update in data.get("result", []):
                    last_update_id = update["update_id"]
                    if "message" in update:
                        chat_id = update["message"]["chat"]["id"]
                        text = update["message"].get("text", "")
                        if text:
                            await updates_queue.put((chat_id, text))

async def worker():
    while True:
        chat_id, text = await updates_queue.get()
        try:
            # Команда /start
            if text == "/start":
                await handle_start(chat_id)
                continue

            # Если пользователь в режиме ожидания вопроса
            if waiting_for_question.get(chat_id):
                await handle_custom_question(chat_id, text)
                continue

            # Иначе обрабатываем кнопки
            if text == "📜 Конституция":
                await send_message(chat_id, CONSTITUTION_TEXT, keyboard=main_keyboard())
            elif text == "⚖️ Уголовный кодекс":
                await send_message(chat_id, CRIMINAL_CODE_TEXT, keyboard=main_keyboard())
            elif text == "🪪 Гражданство":
                await send_message(chat_id, CITIZENSHIP_TEXT, keyboard=main_keyboard())
            elif text == "❓ Другой вопрос":
                await handle_other_question(chat_id)
            else:
                # Неизвестный текст — предлагаем меню
                await send_message(
                    chat_id,
                    "Используйте кнопки меню или выберите «Другой вопрос».",
                    keyboard=main_keyboard()
                )
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")

async def main():
    logger.info("Бот Келариона запущен!")
    asyncio.create_task(worker())
    while True:
        try:
            await get_updates()
            await asyncio.sleep(2)  # задержка между запросами
        except Exception as e:
            logger.error(f"Ошибка в цикле: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())