"""
Обработчики администраторских команд.
"""

import asyncio
import contextlib
import re

from aiogram import types
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, ReplyKeyboardRemove

from bot_instance import bot, dp
from config import ADMIN_CHAT, MESSAGES, logger
from database import User
from filters import UserIsAdmin
from services.stats_service import generate_user_stats
from services.subscription_service import is_user_subscribed_to_all
from states import AdminDispatch, AdminDispatchAll, AdminSetReminderTimes


@dp.message(AdminDispatch.input_text)
async def cmd_dispatch_input_text(message: types.Message, state: FSMContext):
    """Обработка ввода текста для отправки конкретному пользователю."""
    data = await state.get_data()
    user_id = data.get("id")

    try:
        await bot.send_message(int(user_id), text=message.text)
    except Exception as e:
        error_msg = f"LLM{message.chat.id} - ошибка при отправке {e}. Вы в главном меню"
        logger.error(error_msg, exc_info=True)

        with contextlib.suppress(Exception):
            await bot.send_message(ADMIN_CHAT, error_msg)

        await message.answer(error_msg)
        await state.clear()
        return

    await message.answer(MESSAGES["adminka_dispatch3"])
    await state.clear()


@dp.message(AdminDispatch.input_id)
async def cmd_dispatch_input_id(message: types.Message, state: FSMContext):
    """Обработка ввода ID пользователя для отправки сообщения."""
    user_input = message.text
    await state.update_data(id=user_input)
    await message.answer(MESSAGES["adminka_dispatch2"])
    await state.set_state(AdminDispatch.input_text)


@dp.message(UserIsAdmin(), Command("dispatch"))
async def cmd_dispatch(message: types.Message, state: FSMContext):
    """Команда /dispatch - отправка сообщения конкретному пользователю."""
    await message.answer(
        MESSAGES["adminka_dispatch1"], reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(AdminDispatch.input_id)


@dp.message(AdminDispatchAll.input_text)
async def cmd_dispatch_all_input_text(message: types.Message, state: FSMContext):
    """Обработка ввода текста для массовой рассылки."""
    from aiogram.exceptions import TelegramForbiddenError

    try:
        all_ids = await User.get_ids_from_table()
        success_dispatch = 0
        blocked_users = 0

        for user_id in all_ids:
            try:
                await bot.send_message(user_id, message.text)
                success_dispatch += 1
            except TelegramForbiddenError:
                # Пользователь заблокировал бота - удаляем из БД
                user = User(user_id)
                await user.delete_from_db()
                blocked_users += 1
                logger.info(f"USER{user_id} заблокировал бота, удален из БД")
            except Exception as e:
                # Другие ошибки - просто логируем и продолжаем
                logger.warning(f"Не удалось отправить сообщение USER{user_id}: {e}")
                continue

        result_msg = f"Сообщение отправлено {success_dispatch} пользователям"
        if blocked_users > 0:
            result_msg += f"\nУдалено заблокировавших бота: {blocked_users}"

        logger.info(result_msg)

        with contextlib.suppress(Exception):
            await bot.send_message(ADMIN_CHAT, result_msg)

        await bot.send_message(message.chat.id, result_msg)

    except Exception as e:
        error_msg = f"USER{message.chat.id} - ошибка при отправке {e}. Вы в главном меню"
        logger.error(error_msg, exc_info=True)

        with contextlib.suppress(Exception):
            await bot.send_message(ADMIN_CHAT, error_msg)

        await message.answer(error_msg)
        await state.clear()
        return

    await message.answer(MESSAGES["adminka_dispatch3"])
    await state.clear()


@dp.message(UserIsAdmin(), Command("dispatch_all"))
async def cmd_dispatch_all(message: types.Message, state: FSMContext):
    """Команда /dispatch_all - массовая рассылка всем пользователям."""
    await message.answer(
        MESSAGES["adminka_dispatch_all"], reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(AdminDispatchAll.input_text)


@dp.message(UserIsAdmin(), Command("stats"))
async def cmd_stats(message: types.Message):
    """Команда /stats - просмотр статистики пользователя или всех пользователей."""
    logger.info(f"Команда /stats получена от пользователя {message.chat.id}")
    user_id = None

    # Проверяем, является ли сообщение ответом на другое сообщение
    if message.reply_to_message and message.reply_to_message.text:
        # Пытаемся извлечь USER ID из текста сообщения
        replied_text = message.reply_to_message.text
        logger.debug(f"Проверяем replied_text: {replied_text}")
        match = re.search(r"USER(\d+)", replied_text)
        if match:
            user_id = int(match.group(1))
            logger.info(f"Извлечен user_id: {user_id}")

    # Отправляем сообщение о начале обработки
    if user_id:
        status_msg = await message.answer(
            f"⏳ Собираю статистику для пользователя USER{user_id}..."
        )
    else:
        status_msg = await message.answer(
            "⏳ Собираю статистику по всем пользователям..."
        )

    try:
        # Генерируем статистику
        hourly_graph, weekly_graph, total_messages, total_users = await generate_user_stats(user_id)

        if hourly_graph is None:
            await status_msg.edit_text(
                "❌ Нет данных для отображения статистики. "
                "Возможно, пользователь не отправлял сообщений."
            )
            return

        # Формируем текст с результатами
        if user_id:
            result_text = (
                f"📊 Статистика пользователя USER{user_id}\n"
                f"Всего сообщений: {total_messages}"
            )
        else:
            result_text = (
                f"📊 Общая статистика всех пользователей\n"
                f"Всего пользователей: {total_users}\n"
                f"Всего сообщений: {total_messages}"
            )

        # Отправляем текстовое сообщение
        await status_msg.edit_text(result_text)

        # Отправляем графики
        hourly_file = BufferedInputFile(
            hourly_graph.read(), filename="hourly_stats.png"
        )
        weekly_file = BufferedInputFile(
            weekly_graph.read(), filename="weekly_stats.png"
        )

        await message.answer_photo(
            hourly_file, caption="Средняя статистика по часам суток"
        )
        await message.answer_photo(
            weekly_file, caption="Средняя статистика по дням недели"
        )

        # Проверка подписок пользователей (только если запрос по всем пользователям)
        if not user_id:
            sub_status_msg = await message.answer("⏳ Проверяю подписки пользователей на каналы...")

            try:
                all_user_ids = await User.get_ids_from_table()
                subscribed_count = 0
                not_subscribed_count = 0
                not_checked_count = 0
                checked_users = 0

                for uid in all_user_ids:
                    try:
                        user = User(uid)
                        await user.get_from_db()

                        # Пропускаем пользователей, которые еще не проверялись
                        if user.subscription_verified is None:
                            not_checked_count += 1
                            continue

                        # Проверяем подписку
                        is_subscribed = await is_user_subscribed_to_all(bot, uid)
                        checked_users += 1

                        # Обновляем статус в БД
                        new_status = 1 if is_subscribed else 0

                        if is_subscribed:
                            subscribed_count += 1
                        else:
                            not_subscribed_count += 1

                        # Обновляем в БД если статус изменился
                        if user.subscription_verified != new_status:
                            user.subscription_verified = new_status
                            await user.update_in_db()
                            logger.info(f"USER{uid}: статус подписки обновлен с {user.subscription_verified} на {new_status}")

                        # Небольшая задержка между проверками
                        await asyncio.sleep(0.05)

                    except Exception as e:
                        logger.error(f"Ошибка при проверке подписки USER{uid}: {e}", exc_info=True)
                        continue

                # Формируем отчет по подпискам
                subscription_report = (
                    f"📢 Проверка подписок на каналы:\n\n"
                    f"✅ Подписаны: {subscribed_count}\n"
                    f"❌ Не подписаны: {not_subscribed_count}\n"
                    f"⏸ Не проверялись: {not_checked_count}\n"
                    f"📊 Проверено пользователей: {checked_users}/{len(all_user_ids)}"
                )

                await sub_status_msg.edit_text(subscription_report)
                logger.info(f"Проверка подписок завершена: подписано {subscribed_count}/{checked_users}")

            except Exception as sub_error:
                logger.error(f"Ошибка при проверке подписок: {sub_error}", exc_info=True)
                await sub_status_msg.edit_text(f"❌ Ошибка при проверке подписок: {sub_error}")

    except Exception as e:
        error_msg = f"❌ Ошибка при генерации статистики: {e}"
        await status_msg.edit_text(error_msg)
        # Логируем ошибку
        logger.error(f"Ошибка в cmd_stats: {e}", exc_info=True)

        # Пытаемся отправить в DEBUG чат (с обработкой ошибок)
        try:
            await bot.send_message(ADMIN_CHAT, f"Ошибка в cmd_stats: {e}")
        except Exception as debug_error:
            logger.warning(f"Не удалось отправить ошибку в DEBUG чат: {debug_error}")


@dp.message(AdminSetReminderTimes.input_times)
async def cmd_set_reminder_times_input(message: types.Message, state: FSMContext):
    """Обработка ввода времен напоминаний."""
    data = await state.get_data()
    user_id = data.get("user_id")

    if not user_id:
        await message.answer("❌ Ошибка: не найден ID пользователя")
        await state.clear()
        return

    try:
        # Парсим введенные времена (формат: HH:MM HH:MM HH:MM)
        import re
        times_text = message.text.strip()

        # Извлекаем все времена в формате HH:MM
        time_pattern = r'\b([0-2]?[0-9]):([0-5][0-9])\b'
        matches = re.findall(time_pattern, times_text)

        if not matches:
            await message.answer(
                "❌ Не найдено корректных времен. Введите время в формате HH:MM (например: 09:00 14:30 19:15)"
            )
            return

        # Формируем список времен и валидируем их
        reminder_times = []
        for hour, minute in matches:
            hour_int = int(hour)
            minute_int = int(minute)

            if not (0 <= hour_int <= 23 and 0 <= minute_int <= 59):
                await message.answer(f"❌ Некорректное время: {hour}:{minute}")
                return

            # Форматируем время с ведущими нулями
            time_str = f"{hour_int:02d}:{minute_int:02d}"
            if time_str not in reminder_times:
                reminder_times.append(time_str)

        # Обновляем пользователя в БД
        user = User(user_id)
        await user.get_from_db()
        user.reminder_times = reminder_times
        await user.update_in_db()

        times_display = ", ".join(reminder_times)
        success_msg = f"✅ Времена напоминаний для USER{user_id} обновлены: {times_display}"

        await message.answer(success_msg)
        logger.info(success_msg)

        with contextlib.suppress(Exception):
            await bot.send_message(ADMIN_CHAT, success_msg)

    except Exception as e:
        error_msg = f"❌ Ошибка при обновлении времен напоминаний: {e}"
        logger.error(error_msg, exc_info=True)
        await message.answer(error_msg)

    await state.clear()


@dp.message(UserIsAdmin(), Command("send_reminders"))
async def cmd_send_reminders(message: types.Message):
    """
    Команда /send_reminders - принудительная отправка напоминаний всем пользователям,
    у которых НЕ отключены напоминания.
    """
    from aiogram.exceptions import TelegramForbiddenError

    from services.reminder_service import send_reminder_to_user

    logger.info(f"Команда /send_reminders получена от администратора {message.chat.id}")

    status_msg = await message.answer("⏳ Начинаю отправку напоминаний...")

    try:
        # Получаем всех пользователей с включенными напоминаниями
        import aiosqlite

        from database import DATABASE_NAME, TABLE_NAME

        async with aiosqlite.connect(DATABASE_NAME) as db, db.execute(
            f"SELECT id FROM {TABLE_NAME} WHERE remind_of_yourself != '0'"
        ) as cursor:
            user_ids = [row[0] for row in await cursor.fetchall()]

        if not user_ids:
            await status_msg.edit_text("❌ Нет пользователей с включенными напоминаниями")
            return

        success_count = 0
        blocked_count = 0
        error_count = 0

        for user_id in user_ids:
            try:
                await send_reminder_to_user(user_id)
                success_count += 1
                # Небольшая задержка между отправками, чтобы не превысить лимиты Telegram
                await asyncio.sleep(0.05)
            except TelegramForbiddenError:
                # Пользователь заблокировал бота - удаляем из БД
                user = User(user_id)
                await user.delete_from_db()
                blocked_count += 1
                logger.info(f"USER{user_id} заблокировал бота, удален из БД")
            except Exception as e:
                error_count += 1
                logger.warning(f"Ошибка при отправке напоминания USER{user_id}: {e}")

        result_msg = (
            f"✅ Отправка напоминаний завершена\n\n"
            f"📨 Успешно отправлено: {success_count}\n"
            f"🚫 Заблокировали бота: {blocked_count}\n"
            f"❌ Ошибок: {error_count}\n"
            f"📊 Всего пользователей: {len(user_ids)}"
        )

        await status_msg.edit_text(result_msg)
        logger.info(result_msg.replace("\n", " "))

        with contextlib.suppress(Exception):
            await bot.send_message(ADMIN_CHAT, result_msg)

    except Exception as e:
        error_msg = f"❌ Критическая ошибка при отправке напоминаний: {e}"
        logger.error(error_msg, exc_info=True)
        await status_msg.edit_text(error_msg)

        with contextlib.suppress(Exception):
            await bot.send_message(ADMIN_CHAT, error_msg)


@dp.message(UserIsAdmin(), Command("set_reminder_times"))
async def cmd_set_reminder_times(message: types.Message, state: FSMContext):
    """
    Команда /set_reminder_times - установка времен напоминаний для пользователя.
    Использовать как ответ на сообщение с USER ID.
    """
    logger.info(f"Команда /set_reminder_times получена от пользователя {message.chat.id}")
    user_id = None

    # Проверяем, является ли сообщение ответом на другое сообщение
    if message.reply_to_message and message.reply_to_message.text:
        # Пытаемся извлечь USER ID из текста сообщения
        replied_text = message.reply_to_message.text
        logger.debug(f"Проверяем replied_text: {replied_text}")
        match = re.search(r"USER(\d+)", replied_text)
        if match:
            user_id = int(match.group(1))
            logger.info(f"Извлечен user_id: {user_id}")

    if not user_id:
        await message.answer(
            "❌ Используйте эту команду как ответ на сообщение, содержащее USER ID\n"
            "Например, ответьте на сообщение с текстом вида 'USER123456789'"
        )
        return

    # Сохраняем user_id в состоянии и запрашиваем времена
    await state.update_data(user_id=user_id)
    await message.answer(
        f"📝 Введите времена напоминаний для USER{user_id} в формате МСК\n\n"
        f"Формат: HH:MM HH:MM HH:MM\n"
        f"Например: 09:00 14:30 19:15\n\n"
        f"Можно ввести одно или несколько времен через пробел.",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(AdminSetReminderTimes.input_times)
