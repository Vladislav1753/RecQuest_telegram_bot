import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import google.generativeai as genai
from constants import TELEGRAM_TOKEN, GEMINI_API_KEY
import re

# Настройки API
genai.configure(api_key=GEMINI_API_KEY)

# Инициализация бота и диспетчера
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Клавиатура для выбора категории
categories = ["🎬 Movies", "🎮 Games", "📺 TV Shows", "📚 Books", "🎌 Anime"]
category_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=category)] for category in categories],
    resize_keyboard=True
)

# Глобальный словарь для хранения состояний пользователей
user_states = {}


@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()

    if user_id not in user_states:
        await message.answer("Choose a category:", reply_markup=category_keyboard)
        user_states[user_id] = {"step": "choose_category"}
        return

    state = user_states[user_id]

    if state["step"] == "choose_category":
        if text in categories:
            state["category"] = text
            state["step"] = "ask_query"
            await message.answer(f"Enter a {text.lower()} title or genre:")
        else:
            await message.answer("Please select a category from the keyboard.")

    elif state["step"] == "ask_query":
        state["query"] = text
        state["step"] = "recommendations"
        recommendations = await get_gemini_recommendations(state["category"], text)
        await message.answer("\n".join(recommendations))
        del user_states[user_id]  # Сбрасываем состояние

def clean_text_response(text):
    """Clean up text response by removing markdown formatting"""
    text = re.sub(r'[\*_]{1,2}([^*_]+)[\*_]{1,2}', r'\1', text)
    return text#.strip()


async def get_gemini_recommendations(category, query):
    """Функция получения рекомендаций от Gemini API"""
    try:
        prompt = f"Recommend some {category.lower()} similar to: {query}. Do not use markdown formatting. Keep the answer brief, up to 5 recommendations."
        model = genai.GenerativeModel("gemini-2.5-pro-exp-03-25")
        chat = model.start_chat(history=[])
        response = chat.send_message(prompt)

        if not response or not hasattr(response, "text") or not response.text.strip():
            return ["No recommendations found."]

        recommendations = [rec.strip() for rec in response.text.split("\n") if rec.strip()]
        return recommendations[:5] if recommendations else ["No recommendations found."]

    except Exception as e:
        logging.error(f"Error getting recommendations: {e}")
        return ["Sorry, I couldn't generate recommendations at the moment."]


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
