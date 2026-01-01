"""
Миграция 007: Добавление таблицы chat_verifications для хранения информации о верификации чатов.

Таблица chat_verifications хранит информацию о том, кто из участников подтвердил подписку для чата:
- chat_id: ID чата (отрицательное число)
- verified_by_user_id: ID пользователя, который подтвердил подписку
- verified_at: Дата и время верификации
- user_name: Имя пользователя-верификатора (для удобства)
"""

import aiosqlite

from core.database import DATABASE_NAME

# Уникальный идентификатор миграции
MIGRATION_ID = "migration_007_add_chat_verifications"


async def upgrade():
    """Применяет миграцию."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Проверяем, существует ли уже таблица
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chat_verifications'"
        )
        table_exists = await cursor.fetchone()

        if not table_exists:
            # Создаем таблицу chat_verifications
            await db.execute(
                """
                CREATE TABLE chat_verifications (
                    chat_id INTEGER PRIMARY KEY,
                    verified_by_user_id INTEGER NOT NULL,
                    verified_at TEXT NOT NULL,
                    user_name TEXT
                )
                """
            )
            await db.commit()

            return "Создана таблица chat_verifications"
        return "Таблица chat_verifications уже существует"


async def downgrade():
    """Откатывает миграцию."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("DROP TABLE IF EXISTS chat_verifications")
        await db.commit()

        return "Удалена таблица chat_verifications"
