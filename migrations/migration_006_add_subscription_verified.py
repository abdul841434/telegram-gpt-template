"""
Миграция 006: Добавление поля subscription_verified для проверки подписки на каналы.

Поле subscription_verified хранит статус проверки подписки:
- NULL: еще не проверялось (для новых пользователей)
- 0: не подписан на обязательные каналы
- 1: подписан на все обязательные каналы
"""

import aiosqlite

from database import DATABASE_NAME, TABLE_NAME

# Уникальный идентификатор миграции
MIGRATION_ID = "migration_006_add_subscription_verified"


async def upgrade():
    """Применяет миграцию."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Проверяем, существует ли уже столбец
        cursor = await db.execute(f"PRAGMA table_info({TABLE_NAME})")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if "subscription_verified" not in column_names:
            # Добавляем столбец subscription_verified (0 = не подписан, 1 = подписан, NULL = не проверялось)
            await db.execute(
                f"""
                ALTER TABLE {TABLE_NAME}
                ADD COLUMN subscription_verified INTEGER DEFAULT NULL
                """
            )
            await db.commit()
            
            return "Добавлено поле subscription_verified"
        else:
            return "Поле subscription_verified уже существует"


async def downgrade():
    """Откатывает миграцию."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # SQLite не поддерживает DROP COLUMN напрямую
        # Нужно создать новую таблицу без этого столбца
        await db.execute(
            f"""
            CREATE TABLE {TABLE_NAME}_backup AS
            SELECT id, name, prompt, remind_of_yourself, sub_lvl, sub_id, sub_period, is_admin, active_messages_count, reminder_times
            FROM {TABLE_NAME}
            """
        )
        await db.execute(f"DROP TABLE {TABLE_NAME}")
        await db.execute(f"ALTER TABLE {TABLE_NAME}_backup RENAME TO {TABLE_NAME}")
        await db.commit()
        
        return "Удалено поле subscription_verified"

