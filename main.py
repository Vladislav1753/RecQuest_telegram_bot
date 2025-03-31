import logging
import asyncio
import random
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
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
# Mapping for category names without emojis
category_names = {
    "🎬 Movies": "movies",
    "🎮 Games": "games",
    "📺 TV Shows": "TV shows",
    "📚 Books": "books",
    "🎌 Anime": "anime"
}

# Random recommendation prompts for each category
random_prompts = {
    "🎬 Movies": ["popular movie", "cult classic", "hidden gem movie", "must-watch film", "critically acclaimed movie"],
    "🎮 Games": ["popular game", "classic video game", "indie game", "award-winning game", "hidden gem game"],
    "📺 TV Shows": ["popular TV show", "must-watch series", "critically acclaimed show", "hidden gem TV series", "binge-worthy show"],
    "📚 Books": ["bestselling book", "classic novel", "must-read book", "award-winning book", "hidden gem book"],
    "🎌 Anime": ["popular anime", "classic anime", "must-watch anime", "critically acclaimed anime", "hidden gem anime"]
}

category_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=category)] for category in categories],
    resize_keyboard=True
)

# Клавиатура с кнопкой возврата в главное меню
back_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔙 Back to Main Menu")]
    ],
    resize_keyboard=True
)

# Инлайн кнопка "More"
more_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="More recommendations", callback_data="more")]
    ]
)

# Комбинированная клавиатура с командой /random
combined_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔙 Back to Main Menu"), KeyboardButton(text="/random")]
    ],
    resize_keyboard=True,
    input_field_placeholder="Enter title or genre..."
)

# Глобальный словарь для хранения состояний пользователей
user_states = {}

# Global variable for the chat session
gemini_chat = None

async def setup_gemini():
    """Initialize and configure the model when the bot starts."""
    global gemini_chat
    model = genai.GenerativeModel("gemini-2.5-pro-exp-03-25")

    # Start a chat session with predefined instructions
    gemini_chat = model.start_chat(
        history=[
            {
                "role": "user",
                "parts": [
                    "You are an assistant that recommends movies, TV shows, games, books, and anime. "
                    "You should always provide up to 5 recommendations and avoid using markdown. "
                    "Your responses should be relatively brief. "
                    "Format: "
                    "1. Recommendation Title - short review and some reasons it's similar to what the user sent. "
                    "2. Recommendation Title - short review and some reasons it's similar to what the user sent. "
                    "... and so on."
                ]
            }
        ]
    )
    print("Gemini initialized!")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Handle the /start command."""
    await message.answer("Welcome to the Recommendation Bot! Choose a category:", reply_markup=category_keyboard)
    user_id = message.from_user.id
    user_states[user_id] = {"step": "choose_category", "previous_recommendations": set()}

@dp.message(Command("random"))
async def cmd_random(message: types.Message):
    """Handle the /random command."""
    user_id = message.from_user.id
    
    if user_id not in user_states:
        await message.answer("Please choose a category first:", reply_markup=category_keyboard)
        user_states[user_id] = {"step": "choose_category", "previous_recommendations": set()}
        return
    
    state = user_states[user_id]
    
    if "category" not in state:
        await message.answer("Please choose a category first:", reply_markup=category_keyboard)
        state["step"] = "choose_category"
        return
    
    # Get a random prompt for the selected category
    category = state["category"]
    prompts = random_prompts.get(category, ["popular"])
    random_prompt = random.choice(prompts)
    
    # Show loading message
    loading_message = await message.answer(f"Finding a random {category_names.get(category, category.lower())} recommendation...")
    
    # Get recommendation
    state["query"] = random_prompt  # Save the query for "More" button
    state["previous_recommendations"] = set()  # Reset previous recommendations
    recommendations = await get_gemini_recommendations(category, random_prompt, state["previous_recommendations"])
    
    # Update previous recommendations
    for rec in recommendations:
        title_match = re.match(r'^\d+\.\s+([^-]+)\s+-', rec)
        if title_match:
            state["previous_recommendations"].add(title_match.group(1).strip())
    
    # Delete loading message and send recommendations
    await bot.delete_message(chat_id=message.chat.id, message_id=loading_message.message_id)
    await message.answer(f"Random {category_names.get(category, category.lower())} recommendations:", reply_markup=more_keyboard)
    await message.answer("\n".join(recommendations))
    await message.answer("Need something else?", reply_markup=combined_keyboard)

@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Handle back to main menu command
    if text == "🔙 Back to Main Menu":
        await message.answer("Choose a category:", reply_markup=category_keyboard)
        user_states[user_id] = {"step": "choose_category", "previous_recommendations": set()}
        return
        
    # Handle /random command through keyboard
    if text == "/random":
        # Create a fake message for the command handler
        fake_message = types.Message(
            message_id=message.message_id,
            date=message.date,
            chat=message.chat,
            from_user=message.from_user,
            content_type=message.content_type,
            text="/random"
        )
        await cmd_random(fake_message)
        return

    if user_id not in user_states:
        await message.answer("Choose a category:", reply_markup=category_keyboard)
        user_states[user_id] = {"step": "choose_category", "previous_recommendations": set()}
        return

    state = user_states[user_id]

    if state["step"] == "choose_category":
        if text in categories:
            state["category"] = text
            state["step"] = "ask_query"
            # Use the clean category name from the mapping
            category_name = category_names.get(text, text.lower().replace("🎬 ", "").replace("🎮 ", "").replace("📺 ", "").replace("📚 ", "").replace("🎌 ", ""))
            await message.answer(f"Enter a {category_name} title or genre:", reply_markup=combined_keyboard)
        else:
            await message.answer("Please select a category from the keyboard.")

    elif state["step"] == "ask_query":
        state["query"] = text
        state["step"] = "recommendations"
        state["previous_recommendations"] = set()  # Reset previous recommendations
        
        # Show loading message
        loading_message = await message.answer("Searching for recommendations...")
        
        recommendations = await get_gemini_recommendations(state["category"], text, state["previous_recommendations"])
        
        # Update previous recommendations
        for rec in recommendations:
            title_match = re.match(r'^\d+\.\s+([^-]+)\s+-', rec)
            if title_match:
                state["previous_recommendations"].add(title_match.group(1).strip())
        
        # Delete loading message and send recommendations
        await bot.delete_message(chat_id=message.chat.id, message_id=loading_message.message_id)
        await message.answer("\n".join(recommendations), reply_markup=more_keyboard)
        # Keep the back button available
        await message.answer("Need something else?", reply_markup=combined_keyboard)

@dp.callback_query(lambda c: c.data == "more")
async def handle_more_button(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    
    if user_id not in user_states:
        await callback_query.message.answer("Session expired. Please start over:", reply_markup=category_keyboard)
        user_states[user_id] = {"step": "choose_category", "previous_recommendations": set()}
        await callback_query.answer()
        return
    
    state = user_states[user_id]
    
    if "category" in state and "query" in state:
        # Show loading message
        loading_message = await callback_query.message.answer("Searching for more recommendations...")
        
        # Get more recommendations while avoiding previous ones
        recommendations = await get_gemini_recommendations(
            state["category"], 
            state["query"], 
            state["previous_recommendations"]
        )
        
        # Update previous recommendations
        for rec in recommendations:
            title_match = re.match(r'^\d+\.\s+([^-]+)\s+-', rec)
            if title_match:
                state["previous_recommendations"].add(title_match.group(1).strip())
        
        # Delete loading message and send recommendations
        await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=loading_message.message_id)
        await callback_query.message.answer("\n".join(recommendations), reply_markup=more_keyboard)
    else:
        await callback_query.message.answer("Something went wrong. Please start over:", reply_markup=category_keyboard)
        user_states[user_id] = {"step": "choose_category", "previous_recommendations": set()}
    
    await callback_query.answer()

def clean_text_response(text):
    """Clean up text response by removing markdown formatting"""
    text = re.sub(r'[\*_]{1,2}([^*_]+)[\*_]{1,2}', r'\1', text)
    return text#.strip()

async def get_gemini_recommendations(category, query, previous_recommendations=None):
    """Fetch recommendations from the pre-configured model, avoiding previous recommendations."""
    try:
        if gemini_chat is None:
            await setup_gemini()  # Initialize if not already set up

        # Create prompt with instruction to avoid previous recommendations
        prompt = f"{category}: {query}"
        if previous_recommendations and len(previous_recommendations) > 0:
            avoid_list = ", ".join(previous_recommendations)
            prompt += f"\nPlease provide 5 new recommendations that are NOT in this list: {avoid_list}"

        response = gemini_chat.send_message(prompt)

        if not response or not hasattr(response, "text") or not response.text.strip():
            return ["No recommendations found."]

        recommendations = [rec.strip() for rec in response.text.split("\n") if rec.strip()]
        return recommendations[:5] if recommendations else ["No recommendations found."]

    except Exception as e:
        logging.error(f"Error getting recommendations: {e}")
        return ["Sorry, I couldn't generate recommendations at the moment."]

async def main():
    """Start the bot and initialize Gemini."""
    await setup_gemini()  # Initialize Gemini once on startup
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())