"""
Миграция 006: Добавление поля subscription_verified для проверки подписки на каналы.

Поле subscription_verified хранит статус проверки подписки:
- NULL: еще не проверялось (для новых пользователей)
- 0: не подписан на обязательные каналы
- 1: подписан на все обязательные каналы
"""

import aiosqlite

from database import DATABASE_NAME

# Уникальный идентификатор миграции
MIGRATION_ID = "migration_006_add_subscription_verified"


async def upgrade():
    """Применяет миграцию."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Проверяем, существует ли уже столбец
        cursor = await db.execute("PRAGMA table_info(conversations)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if "subscription_verified" not in column_names:
            # Добавляем столбец subscription_verified (0 = не подписан, 1 = подписан, NULL = не проверялось)
            await db.execute(
                """
                ALTER TABLE conversations
                ADD COLUMN subscription_verified INTEGER DEFAULT NULL
                """
            )
            await db.commit()

            return "Добавлено поле subscription_verified"
        return "Поле subscription_verified уже существует"


async def downgrade():
    """Откатывает миграцию."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # SQLite не поддерживает DROP COLUMN напрямую
        # Нужно создать новую таблицу без этого столбца
        await db.execute(
            """
            CREATE TABLE conversations_backup AS
            SELECT id, name, prompt, remind_of_yourself, sub_lvl, sub_id, sub_period, is_admin, active_messages_count, reminder_times
            FROM conversations
            """
        )
        await db.execute("DROP TABLE conversations")
        await db.execute("ALTER TABLE conversations_backup RENAME TO conversations")
        await db.commit()

        return "Удалено поле subscription_verified"

