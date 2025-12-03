"""
Вспомогательные утилиты.
"""

import asyncio

from aiogram import types
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramMigrateToChat,
)

from bot_instance import bot
from config import ADMIN_CHAT, MESSAGES_LEVEL, logger


async def keep_typing(chat_id: int, duration: int = 30):
    """
    Периодически показывает статус "печатает..." для чат-бота.

    Args:
        chat_id: ID чата
        duration: Продолжительность в секундах (по умолчанию 30)
    """
    iterations = duration // 3
    for _ in range(iterations):
        await bot.send_chat_action(chat_id=chat_id, action="typing")
        await asyncio.sleep(3)


async def forward_to_debug(message_chat_id: int, message_id: int):
    """
    Пересылает сообщение в отладочный чат с меткой USER ID.
    Пересылка происходит только если TELEGRAM_LOG_LEVEL <= MESSAGES (25).

    Args:
        message_chat_id: ID чата с сообщением
        message_id: ID сообщения
    """
    # Проверяем уровень Telegram логирования
    telegram_level = getattr(logger, "_telegram_level", 100)

    # Пересылаем только если уровень <= MESSAGES (включая INFO, DEBUG, FULL)
    if telegram_level > MESSAGES_LEVEL:
        return

    try:
        # Отправляем метку с USER ID перед пересылкой
        await bot.send_message(ADMIN_CHAT, f"USER{message_chat_id}")
        # Пересылаем сообщение
        await bot.forward_message(
            chat_id=ADMIN_CHAT, from_chat_id=message_chat_id, message_id=message_id
        )
    except TelegramMigrateToChat as e:
        # Чат был преобразован в супергруппу
        new_chat_id = e.migrate_to_chat_id
        logger.warning(
            f"⚠️ ADMIN чат был преобразован в супергруппу!\n"
            f"Старый ID: {ADMIN_CHAT}\n"
            f"Новый ID: {new_chat_id}\n"
            f"❗ Обновите переменную ADMIN_CHAT в .env или GitHub Secrets"
        )
        # Пытаемся отправить в новый чат
        try:
            await bot.send_message(new_chat_id, f"USER{message_chat_id}")
            await bot.forward_message(
                chat_id=new_chat_id, from_chat_id=message_chat_id, message_id=message_id
            )
            logger.info(f"✅ Сообщение успешно отправлено в новый чат {new_chat_id}")
        except Exception as e2:
            logger.error(
                f"❌ Не удалось отправить сообщение в новый чат {new_chat_id}: {e2}"
            )
    except Exception as e:
        # Любые другие ошибки (бот не добавлен в чат, чат не существует и т.д.)
        logger.warning(
            f"⚠️ Не удалось переслать сообщение в ADMIN чат (ID: {ADMIN_CHAT}): {e}\n"
            f"Проверьте:\n"
            f"1. Бот добавлен в ADMIN чат\n"
            f"2. ADMIN_CHAT ID корректный\n"
            f"3. У бота есть права на отправку сообщений"
        )


def is_private_chat(message: types.Message) -> bool:
    """
    Проверяет, является ли сообщение из личного чата.

    Args:
        message: Сообщение от пользователя

    Returns:
        True если это личный чат, False если группа/супергруппа/канал
    """
    return message.chat.type == "private"


async def should_respond_in_chat(message: types.Message) -> bool:
    """
    Проверяет, должен ли бот ответить на сообщение в групповом чате.
    Бот отвечает только если:
    - Сообщение является ответом на сообщение бота
    - Бот упомянут в тексте через @username
    - Бот упомянут через entities (mention/text_mention)

    Args:
        message: Сообщение от пользователя

    Returns:
        True если бот должен ответить, False иначе
    """
    # Если это личный чат, всегда отвечаем
    if is_private_chat(message):
        return True

    # Получаем информацию о боте
    bot_info = await bot.get_me()
    bot_username = bot_info.username

    # Проверяем, является ли сообщение ответом на сообщение бота
    if (
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.is_bot
        and message.reply_to_message.from_user.id == bot_info.id
    ):
        return True

    # Проверяем упоминание бота в тексте
    if message.text and f"@{bot_username}" in message.text:
        return True

    # Проверяем упоминание через entities
    if message.entities:
        for entity in message.entities:
            if entity.type == "mention":
                # Извлекаем упомянутое имя
                mentioned = message.text[entity.offset : entity.offset + entity.length]
                if mentioned == f"@{bot_username}":
                    return True
            elif entity.type == "text_mention":
                # Прямое упоминание пользователя (может быть и ботом)
                if entity.user and entity.user.id == bot_info.id:
                    return True

    # Проверяем упоминание в caption (для фото/видео)
    if message.caption:
        if f"@{bot_username}" in message.caption:
            return True

        # Проверяем entities в caption
        if message.caption_entities:
            for entity in message.caption_entities:
                if entity.type == "mention":
                    mentioned = message.caption[
                        entity.offset : entity.offset + entity.length
                    ]
                    if mentioned == f"@{bot_username}":
                        return True
                elif entity.type == "text_mention":
                    if entity.user and entity.user.id == bot_info.id:
                        return True

    return False


def fix_nested_markdown(text: str) -> str:
    """
    Исправляет вложенные markdown теги и неэкранированные спецсимволы в Telegram MarkdownV2.

    Обрабатывает:
    1. Вложенные теги одного типа (_, *, ~, `, __, ||)
    2. Неэкранированные специальные символы MarkdownV2

    Обрабатываемые теги:
    - _ (курсив/italic)
    - * (жирный/bold)
    - ~ (зачеркнутый/strikethrough)
    - ` (моноширинный/code)
    - __ (подчеркнутый/underline)
    - || (спойлер/spoiler)

    Экранируемые спецсимволы:
    - > (цитата)
    - # + - = | { } . !

    Args:
        text: Текст с потенциально некорректным markdown

    Returns:
        Исправленный текст
    """
    if not text:
        return text

    # Определяем, является ли символ частью markdown тега
    def is_likely_tag_start(i: int, tag: str) -> bool:
        """Проверяет, похоже ли что символ(ы) начинают тег."""
        # Проверяем длину тега
        if i + len(tag) > len(text):
            return False

        # Проверяем, что это правильный тег
        if text[i:i+len(tag)] != tag:
            return False

        # В начале строки - это может быть тег
        if i == 0:
            next_char = text[i + len(tag)] if i + len(tag) < len(text) else ''
            return next_char and next_char not in ' \n\t'

        prev_char = text[i - 1]
        next_char = text[i + len(tag)] if i + len(tag) < len(text) else ''

        # Открывающий тег обычно идет после пробела/начала и перед не-пробелом
        if prev_char in ' \n\t([{':
            return next_char and next_char not in ' \n\t'

        return False

    def is_likely_tag_end(i: int, tag: str) -> bool:
        """Проверяет, похоже ли что символ(ы) закрывают тег."""
        # Проверяем длину тега
        if i + len(tag) > len(text):
            return False

        # Проверяем, что это правильный тег
        if text[i:i+len(tag)] != tag:
            return False

        # В конце строки - это может быть тег
        if i + len(tag) >= len(text):
            prev_char = text[i - 1] if i > 0 else ''
            return prev_char and prev_char not in ' \n\t'

        prev_char = text[i - 1] if i > 0 else ''
        next_char = text[i + len(tag)]

        # Закрывающий тег обычно идет после не-пробела и перед пробелом/концом
        if prev_char and prev_char not in ' \n\t':
            return next_char in ' \n\t.!?,;:)]}' or i + len(tag) == len(text)

        return False

    # Теги для обработки (от более длинных к коротким, чтобы правильно обработать __ перед _)
    tags = ['||', '__', '_', '*', '~', '`']

    result = []
    stack = []  # Стек открытых тегов: [(tag, position_in_result)]
    i = 0

    while i < len(text):
        matched_tag = None

        # Проверяем все теги
        for tag in tags:
            if text[i:i+len(tag)] == tag:
                matched_tag = tag
                break

        if not matched_tag:
            # Обычный символ
            result.append(text[i])
            i += 1
            continue

        # Нашли потенциальный тег
        tag = matched_tag
        tag_len = len(tag)

        # Проверяем, есть ли этот тег уже в стеке
        tag_in_stack = any(t == tag for t, _ in stack)

        if tag_in_stack:
            # Тег уже открыт, это должен быть закрывающий тег
            if is_likely_tag_end(i, tag):
                # Закрываем тег
                # Ищем соответствующий открывающий тег в стеке
                found = False
                for idx, (stack_tag, _) in enumerate(stack):
                    if stack_tag == tag:
                        # Нашли - закрываем
                        stack.pop(idx)
                        result.append(tag)
                        found = True
                        break

                if not found:
                    # Не нашли в стеке - экранируем
                    result.append('\\')
                    result.append(tag)
            else:
                # Это вложенный тег того же типа - экранируем
                result.append('\\')
                result.append(tag)

            i += tag_len
        else:
            # Тег не в стеке
            if is_likely_tag_start(i, tag):
                # Открываем новый тег
                stack.append((tag, len(result)))
                result.append(tag)
                i += tag_len
            else:
                # Не похоже на тег - оставляем как есть
                result.append(text[i])
                i += 1

    # Если остались незакрытые теги - экранируем их
    while stack:
        tag, pos = stack.pop()
        # Вставляем экранирование перед открывающим тегом
        result.insert(pos, '\\')

    fixed_text = ''.join(result)

    # Шаг 2: Проверяем и экранируем специальные символы MarkdownV2
    # Символы, которые должны быть экранированы вне markdown-тегов
    special_chars = ['>', '#', '+', '-', '=', '{', '}', '.', '!']

    result2 = []
    i = 0
    in_code = False  # Флаг, что мы внутри ` код `

    while i < len(fixed_text):
        char = fixed_text[i]

        # Отслеживаем code блоки (внутри них не экранируем)
        if char == '`' and (i == 0 or fixed_text[i-1] != '\\'):
            in_code = not in_code
            result2.append(char)
            i += 1
            continue

        # Внутри code блоков не трогаем ничего
        if in_code:
            result2.append(char)
            i += 1
            continue

        # Проверяем, нужно ли экранировать символ
        if char in special_chars:
            # Проверяем, не экранирован ли уже
            if i > 0 and fixed_text[i-1] == '\\':
                # Уже экранирован
                result2.append(char)
            else:
                # Экранируем
                result2.append('\\')
                result2.append(char)
            i += 1
        else:
            result2.append(char)
            i += 1

    return ''.join(result2)


async def send_message_with_fallback(
    chat_id: int, text: str, **kwargs
) -> types.Message:
    """
    Отправляет сообщение с MARKDOWN_V2 форматированием.

    Стратегия при ошибке:
    1. Если бот заблокирован (Forbidden) - сразу пробрасываем ошибку
    2. Если ошибка парсинга markdown - пробуем исправить и отправить снова
    3. Если не помогло - отправляем без форматирования

    Args:
        chat_id: ID чата для отправки
        text: Текст сообщения (уже сконвертированный через telegramify_markdown)
        **kwargs: Дополнительные параметры для send_message

    Returns:
        Отправленное сообщение

    Raises:
        TelegramForbiddenError: Если бот заблокирован пользователем
        Exception: Если не удалось отправить сообщение ни одним способом
    """
    try:
        return await bot.send_message(
            chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2, **kwargs
        )
    except TelegramForbiddenError:
        # Бот заблокирован - сразу пробрасываем, не пытаемся исправить markdown
        raise
    except TelegramBadRequest as e:
        # Проверяем, это ошибка парсинга markdown или что-то другое
        error_message = str(e).lower()
        if "can't parse entities" in error_message or "can't find end" in error_message:
            # Это ошибка парсинга - пробуем исправить
            try:
                logger.warning(
                    f"CHAT{chat_id} - ошибка парсинга Markdown: {e}. "
                    f"Пробуем исправить markdown..."
                )
                fixed_text = fix_nested_markdown(text)

                return await bot.send_message(
                    chat_id=chat_id, text=fixed_text, parse_mode=ParseMode.MARKDOWN_V2, **kwargs
                )
            except TelegramForbiddenError:
                # Даже после исправления получили Forbidden - пробрасываем
                raise
            except Exception as e2:
                # Исправление не помогло - отправляем без форматирования
                try:
                    logger.warning(
                        f"CHAT{chat_id} - исправление не помогло: {e2}. "
                        f"Отправляем без форматирования."
                    )
                    kwargs.pop("parse_mode", None)
                    return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
                except TelegramForbiddenError:
                    # И здесь Forbidden - пробрасываем
                    raise
                except Exception:
                    # Если и это не сработало - пробрасываем исходную ошибку
                    logger.error(
                        f"CHAT{chat_id} - не удалось отправить сообщение: {e}"
                    )
                    raise
        else:
            # Это не ошибка парсинга - пробрасываем как есть
            raise
    except Exception:
        # Любая другая ошибка - пробрасываем
        raise
