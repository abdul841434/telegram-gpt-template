"""
Миграция 010: Добавление поля referral_code.

Добавляет поле referral_code в таблицу conversations для хранения
реферального кода, по которому пользователь перешел в бота.

Изменения:
- Добавление колонки referral_code TEXT (nullable) в таблицу conversations
- У всех существующих пользователей значение будет NULL
"""

import aiosqlite

from database import DATABASE_NAME

# Уникальный идентификатор миграции
MIGRATION_ID = "migration_010_add_referral_code"


async def upgrade():
    """Применяет миграцию."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Проверяем, существует ли уже колонка
        cursor = await db.execute("PRAGMA table_info(conversations)")
        columns = await cursor.fetchall()
        column_names = [column[1] for column in columns]

        if "referral_code" in column_names:
            return "Колонка referral_code уже существует"

        # Добавляем колонку referral_code
        await db.execute(
            "ALTER TABLE conversations ADD COLUMN referral_code TEXT DEFAULT NULL"
        )
        await db.commit()

        return "Добавлена колонка referral_code в таблицу conversations"


async def downgrade():
    """
    Откатывает миграцию.

    Примечание: SQLite не поддерживает DROP COLUMN напрямую,
    поэтому откат требует пересоздания таблицы.
    """
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Проверяем, существует ли колонка
        cursor = await db.execute("PRAGMA table_info(conversations)")
        columns = await cursor.fetchall()
        column_names = [column[1] for column in columns]

        if "referral_code" not in column_names:
            return "Колонка referral_code не существует"

        # Создаем временную таблицу без колонки referral_code
        await db.execute(
            """
            CREATE TABLE conversations_temp (
                id INTEGER PRIMARY KEY,
                name TEXT,
                prompt JSON,
                remind_of_yourself TEXT,
                sub_lvl INTEGER,
                sub_id TEXT,
                sub_period INTEGER,
                is_admin INTEGER,
                active_messages_count INTEGER,
                reminder_times TEXT DEFAULT '["19:15"]',
                subscription_verified INTEGER
            )
            """
        )

        # Копируем данные (без referral_code)
        await db.execute(
            """
            INSERT INTO conversations_temp
            SELECT id, name, prompt, remind_of_yourself, sub_lvl, sub_id,
                   sub_period, is_admin, active_messages_count, reminder_times,
                   subscription_verified
            FROM conversations
            """
        )

        # Удаляем старую таблицу
        await db.execute("DROP TABLE conversations")

        # Переименовываем временную таблицу
        await db.execute("ALTER TABLE conversations_temp RENAME TO conversations")

        await db.commit()

        return "Колонка referral_code удалена из таблицы conversations"

