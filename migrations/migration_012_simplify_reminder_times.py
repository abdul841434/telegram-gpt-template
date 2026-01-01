"""
Миграция 012: Упрощение reminder_times - одно время и дни недели.

Изменения:
- Заменяет reminder_times (список времен) на reminder_time (одно время в формате "HH:MM")
- Добавляет reminder_weekdays (JSON массив дней недели: 0=Понедельник, 6=Воскресенье)
- Если reminder_weekdays пустой [], то напоминания во все дни недели
- При миграции берется первое время из списка reminder_times
- Удаляется старое поле reminder_times
"""

import json

import aiosqlite

from core.database import DATABASE_NAME

# Уникальный идентификатор миграции
MIGRATION_ID = "migration_012_simplify_reminder_times"


async def upgrade():
    """Применяет миграцию."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Проверяем структуру таблицы
        cursor = await db.execute("PRAGMA table_info(conversations)")
        columns = await cursor.fetchall()
        column_names = [column[1] for column in columns]

        # Проверяем, существует ли уже новое поле
        if "reminder_time" in column_names:
            return "Поля reminder_time и reminder_weekdays уже существуют"

        # Добавляем новое поле reminder_time
        await db.execute(
            "ALTER TABLE conversations ADD COLUMN reminder_time TEXT DEFAULT '19:15'"
        )
        await db.commit()

        # Добавляем новое поле reminder_weekdays
        await db.execute(
            "ALTER TABLE conversations ADD COLUMN reminder_weekdays TEXT DEFAULT '[]'"
        )
        await db.commit()

        # Конвертируем существующие reminder_times в reminder_time
        # Берем первое время из списка, если список не пустой
        cursor = await db.execute(
            "SELECT id, reminder_times FROM conversations WHERE reminder_times IS NOT NULL"
        )
        rows = await cursor.fetchall()

        updated_count = 0
        for user_id, reminder_times_json in rows:
            try:
                reminder_times = json.loads(reminder_times_json) if reminder_times_json else []
                if reminder_times and len(reminder_times) > 0:
                    # Берем первое время
                    reminder_time = reminder_times[0]
                    # Валидируем формат
                    if ":" in reminder_time and len(reminder_time.split(":")) == 2:
                        hour, minute = reminder_time.split(":")
                        if 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59:
                            await db.execute(
                                "UPDATE conversations SET reminder_time = ? WHERE id = ?",
                                (reminder_time, user_id),
                            )
                            updated_count += 1
            except (json.JSONDecodeError, ValueError, AttributeError) as e:
                # Если не удалось распарсить, оставляем дефолтное значение "19:15"
                print(f"  ⚠️  Ошибка при конвертации reminder_times для USER{user_id}: {e}")

        await db.commit()

        # Удаляем старое поле reminder_times
        # SQLite не поддерживает DROP COLUMN напрямую, поэтому пересоздаем таблицу
        # Сначала создаем временную таблицу без reminder_times
        await db.execute(
            """
            CREATE TABLE conversations_temp (
                id INTEGER PRIMARY KEY,
                name TEXT,
                prompt TEXT,
                remind_of_yourself TEXT,
                sub_lvl INTEGER,
                sub_id TEXT,
                sub_period INTEGER,
                is_admin INTEGER,
                active_messages_count INTEGER,
                reminder_time TEXT DEFAULT '19:15',
                reminder_weekdays TEXT DEFAULT '[]',
                subscription_verified INTEGER,
                referral_code TEXT,
                is_active INTEGER DEFAULT 1
            )
            """
        )

        # Копируем данные (без reminder_times)
        await db.execute(
            """
            INSERT INTO conversations_temp
            SELECT id, name, prompt, remind_of_yourself, sub_lvl, sub_id,
                   sub_period, is_admin, active_messages_count, reminder_time,
                   reminder_weekdays, subscription_verified, referral_code, is_active
            FROM conversations
            """
        )

        # Удаляем старую таблицу
        await db.execute("DROP TABLE conversations")

        # Переименовываем временную таблицу
        await db.execute("ALTER TABLE conversations_temp RENAME TO conversations")

        # Восстанавливаем индекс на is_active, если он был
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_is_active ON conversations(is_active)"
        )

        await db.commit()

        return (
            f"Миграция завершена: заменено reminder_times на reminder_time и reminder_weekdays. "
            f"Обновлено {updated_count} пользователей."
        )


async def downgrade():
    """
    Откатывает миграцию.

    Восстанавливает reminder_times из reminder_time (создает список с одним временем).
    """
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Проверяем структуру таблицы
        cursor = await db.execute("PRAGMA table_info(conversations)")
        columns = await cursor.fetchall()
        column_names = [column[1] for column in columns]

        if "reminder_times" in column_names:
            return "Поле reminder_times уже существует"

        # Добавляем обратно reminder_times
        await db.execute(
            "ALTER TABLE conversations ADD COLUMN reminder_times TEXT DEFAULT '[\"19:15\"]'"
        )
        await db.commit()

        # Конвертируем reminder_time обратно в reminder_times (список)
        cursor = await db.execute(
            "SELECT id, reminder_time FROM conversations WHERE reminder_time IS NOT NULL"
        )
        rows = await cursor.fetchall()

        updated_count = 0
        for user_id, reminder_time in rows:
            if reminder_time:
                # Создаем список с одним временем
                reminder_times = json.dumps([reminder_time])
                await db.execute(
                    "UPDATE conversations SET reminder_times = ? WHERE id = ?",
                    (reminder_times, user_id),
                )
                updated_count += 1

        await db.commit()

        # Удаляем новые поля (через пересоздание таблицы)
        await db.execute(
            """
            CREATE TABLE conversations_temp (
                id INTEGER PRIMARY KEY,
                name TEXT,
                prompt TEXT,
                remind_of_yourself TEXT,
                sub_lvl INTEGER,
                sub_id TEXT,
                sub_period INTEGER,
                is_admin INTEGER,
                active_messages_count INTEGER,
                reminder_times TEXT DEFAULT '["19:15"]',
                subscription_verified INTEGER,
                referral_code TEXT,
                is_active INTEGER DEFAULT 1
            )
            """
        )

        await db.execute(
            """
            INSERT INTO conversations_temp
            SELECT id, name, prompt, remind_of_yourself, sub_lvl, sub_id,
                   sub_period, is_admin, active_messages_count, reminder_times,
                   subscription_verified, referral_code, is_active
            FROM conversations
            """
        )

        await db.execute("DROP TABLE conversations")
        await db.execute("ALTER TABLE conversations_temp RENAME TO conversations")

        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_is_active ON conversations(is_active)"
        )

        await db.commit()

        return (
            f"Откат завершен: восстановлено reminder_times. "
            f"Обновлено {updated_count} пользователей."
        )

