"""
Миграция 008: Переименование таблицы users в conversations.

Переименование отражает реальное использование таблицы: она хранит данные не только
о пользователях (с положительными ID), но и о чатах (с отрицательными ID).
Новое название "conversations" более точно описывает суть - это контекст беседы
(личной или групповой) с ботом.

Изменения:
- Переименование таблицы users -> conversations
- Данные сохраняются полностью (все записи, индексы, связи)
"""

import aiosqlite

from core.database import DATABASE_NAME

# Уникальный идентификатор миграции
MIGRATION_ID = "migration_008_rename_users_to_conversations"


async def upgrade():
    """Применяет миграцию."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Проверяем, существует ли таблица users
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        )
        users_table_exists = await cursor.fetchone()

        # Проверяем, существует ли уже таблица conversations
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='conversations'"
        )
        conversations_table_exists = await cursor.fetchone()

        if users_table_exists and not conversations_table_exists:
            # Переименовываем таблицу users в conversations
            await db.execute("ALTER TABLE users RENAME TO conversations")
            await db.commit()
            return "Таблица users переименована в conversations"
        if conversations_table_exists:
            return "Таблица conversations уже существует"
        return "Таблица users не найдена (возможно, уже переименована)"


async def downgrade():
    """Откатывает миграцию."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Проверяем, существует ли таблица conversations
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='conversations'"
        )
        conversations_table_exists = await cursor.fetchone()

        if conversations_table_exists:
            # Переименовываем обратно
            await db.execute("ALTER TABLE conversations RENAME TO users")
            await db.commit()
            return "Таблица conversations переименована обратно в users"
        return "Таблица conversations не найдена"
