"""
Миграция 004: Исправление дефолтных значений remind_of_yourself.

Изменяет значение remind_of_yourself с "2077-06-15 22:03:51" на NULL для пользователей,
которые еще не получали напоминаний.

Логика:
- "0" = напоминания отключены
- NULL = еще не отправлялись, можно отправить
- "YYYY-MM-DD HH:MM:SS" = timestamp последнего отправленного напоминания
"""

import aiosqlite

from core.database import DATABASE_NAME

# Уникальный идентификатор миграции
MIGRATION_ID = "migration_004_fix_reminder_defaults"


async def upgrade():
    """Применяет миграцию."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Обновляем дефолтное значение на NULL для пользователей с датой в будущем
        await db.execute(
            """
            UPDATE conversations
            SET remind_of_yourself = NULL
            WHERE remind_of_yourself = '2077-06-15 22:03:51'
            """
        )

        await db.commit()

        # Проверяем результат
        cursor = await db.execute(
            "SELECT COUNT(*) FROM conversations WHERE remind_of_yourself IS NULL"
        )
        count = (await cursor.fetchone())[0]

        return (
            f"Обновлено пользователей: {count} (установлен NULL вместо дефолтной даты)"
        )


async def downgrade():
    """Откатывает миграцию."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Возвращаем дефолтное значение
        await db.execute(
            """
            UPDATE conversations
            SET remind_of_yourself = '2077-06-15 22:03:51'
            WHERE remind_of_yourself IS NULL
            """
        )

        await db.commit()

        return "Откат выполнен: восстановлена дефолтная дата"
