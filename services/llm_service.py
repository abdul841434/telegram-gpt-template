"""
Сервис для работы с LLM.
"""
from datetime import datetime, timezone, timedelta

import telegramify_markdown

from bot_instance import bot
from config import (
    logger, 
    DEBUG_CHAT, 
    DEFAULT_PROMPT, 
    DELAYED_REMINDERS_HOURS,
    DELAYED_REMINDERS_MINUTES,
    TIMEZONE_OFFSET,
    FROM_TIME,
    TO_TIME
)
from database import User
import database
from services.llm_client import send_request_to_openrouter


async def process_user_message(chat_id: int, message_text: str) -> str | None:
    """
    Обрабатывает сообщение пользователя через LLM.
    
    Args:
        chat_id: ID чата пользователя
        message_text: Текст сообщения
        
    Returns:
        Отформатированный ответ от LLM или None при ошибке
    """
    user = User(chat_id)
    await user.get_from_db()
    
    # Добавляем сообщение пользователя в историю
    await user.update_prompt("user", message_text)
    
    # Подготавливаем промпт для запроса
    prompt_for_request = user.prompt.copy()
    current_date = datetime.now(
        timezone(timedelta(hours=3))
    ).strftime("%Y-%m-%d %H:%M:%S")
    prompt_for_request.append({
        "role": "system",
        "content": DEFAULT_PROMPT.replace("{CURRENTDATE}", current_date)
    })
    
    # Запрашиваем ответ от LLM
    try:
        llm_msg = await send_request_to_openrouter(prompt_for_request)
    except Exception as e:
        await bot.send_message(
            DEBUG_CHAT,
            f"LLM{chat_id} - Критическая ошибка: {e}"
        )
        return None
    
    if llm_msg is None or llm_msg.strip() == "":
        await bot.send_message(DEBUG_CHAT, f"LLM{chat_id} - пустой ответ от LLM")
        return None
    
    # Сохраняем ответ в историю
    await user.update_prompt("assistant", llm_msg)
    logger.debug(f"LLM_RAWOUTPUT{chat_id}:{llm_msg}")
    
    # Конвертируем в Telegram Markdown
    converted = telegramify_markdown.markdownify(
        llm_msg,
        max_line_length=None,
        normalize_whitespace=False,
    )
    
    # Обновляем время следующего напоминания
    user.remind_of_yourself = await database.time_after(
        DELAYED_REMINDERS_HOURS,
        DELAYED_REMINDERS_MINUTES,
        TIMEZONE_OFFSET,
        FROM_TIME,
        TO_TIME,
    )
    await user.update_in_db()
    
    return converted

