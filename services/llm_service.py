"""
Сервис для работы с LLM.
"""

import json
from datetime import datetime, timedelta, timezone

import telegramify_markdown

import database
from config import (
    DEFAULT_PROMPT,
    DELAYED_REMINDERS_HOURS,
    DELAYED_REMINDERS_MINUTES,
    FROM_TIME,
    FULL_LEVEL,
    TIMEZONE_OFFSET,
    TO_TIME,
    logger,
)
from database import User
from services.llm_client import send_request_to_openrouter


def log_prompt(chat_id: int, prompt: list[dict], prompt_type: str = "MESSAGE"):
    """
    Логирует промпт с разными уровнями детализации.

    Args:
        chat_id: ID чата пользователя
        prompt: Список сообщений промпта
        prompt_type: Тип промпта (MESSAGE или REMINDER)
    """
    # Системные промпты без истории (DEBUG уровень)
    system_prompts = [msg for msg in prompt if msg.get("role") == "system"]
    logger.debug(
        f"PROMPT_SYSTEM_{prompt_type}{chat_id}: {json.dumps(system_prompts, ensure_ascii=False)}"
    )

    # Полный промпт со всей историей (FULL уровень)
    logger.log(
        FULL_LEVEL,
        f"PROMPT_FULL_{prompt_type}{chat_id}: {json.dumps(prompt, ensure_ascii=False, indent=2)}",
    )


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

    # Подготавливаем промпт для запроса (только последние MAX_CONTEXT сообщений)
    prompt_for_request = user.get_context_for_llm().copy()
    current_date = datetime.now(timezone(timedelta(hours=3))).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # Формируем системный промпт с подстановкой данных
    system_content = DEFAULT_PROMPT.replace("{CURRENTDATE}", current_date)

    # Добавляем имя пользователя если оно есть и не "Not_of_registration"
    if user.name and user.name != "Not_of_registration":
        username_info = f"6. Имя пользователя: {user.name}"
        system_content = system_content.replace("{USERNAME}", username_info)
    else:
        system_content = system_content.replace("{USERNAME}", "")

    prompt_for_request.append(
        {
            "role": "system",
            "content": system_content,
        }
    )

    # Логируем промпт перед отправкой
    log_prompt(chat_id, prompt_for_request, "MESSAGE")

    # Запрашиваем ответ от LLM
    try:
        llm_msg = await send_request_to_openrouter(prompt_for_request)
    except Exception as e:
        logger.error(f"LLM{chat_id} - Критическая ошибка: {e}", exc_info=True)
        return None

    if llm_msg is None or llm_msg.strip() == "":
        logger.error(f"LLM{chat_id} - пустой ответ от LLM")
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
