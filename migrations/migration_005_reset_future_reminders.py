"""
Миграция 005: Сброс remind_of_yourself с датами в будущем.

Устаревшая логика устанавливала remind_of_yourself на время в будущем
(когда должно было прийти следующее напоминание). Новая логика использует
расписание reminder_times, а remind_of_yourself хранит timestamp последнего
отправленного напоминания.

Эта миграция сбрасывает все даты в будущем на NULL.
"""

from datetime import datetime, timedelta, timezone

import aiosqlite

from database import DATABASE_NAME, TABLE_NAME, TIMEZONE_OFFSET

# Уникальный идентификатор миграции
MIGRATION_ID = "migration_005_reset_future_reminders"


async def upgrade():
    """Применяет миграцию."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Получаем текущее время в МСК
        now_msk = datetime.now(timezone(timedelta(hours=TIMEZONE_OFFSET)))
        current_time_str = now_msk.strftime("%Y-%m-%d %H:%M:%S")

        # Сбрасываем все remind_of_yourself с датами в будущем на NULL
        # Исключаем "0" (напоминания отключены)
        await db.execute(
            f"""
            UPDATE {TABLE_NAME}
            SET remind_of_yourself = NULL
            WHERE remind_of_yourself != '0'
            AND remind_of_yourself > ?
            """,
            (current_time_str,)
        )

        await db.commit()

        # Проверяем результат
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE remind_of_yourself IS NULL"
        )
        count_null = (await cursor.fetchone())[0]

        cursor = await db.execute(
            f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE remind_of_yourself = '0'"
        )
        count_disabled = (await cursor.fetchone())[0]

        return (
            f"Сброшено пользователей с датами в будущем. "
            f"NULL: {count_null}, отключено: {count_disabled}"
        )


async def downgrade():
    """Откатывает миграцию."""
    # Откат невозможен, так как мы не сохраняли старые значения
    return "Откат невозможен: старые значения не сохранялись"

