"""
Миграция: Добавление поля reminder_times для списка времен напоминаний.

Добавляет поле reminder_times (JSON массив времен в формате HH:MM МСК).
По умолчанию ["19:15"].
"""

import json
import os

import aiosqlite
from dotenv import load_dotenv

load_dotenv()
TABLE_NAME = os.environ.get("TABLE_NAME", "users")


async def migrate(db: aiosqlite.Connection):
    """
    Добавляет поле reminder_times в таблицу users.
    """
    print("  🔧 Добавляем поле reminder_times в таблицу users...")

    # Проверяем, существует ли уже это поле
    async with db.execute(f"PRAGMA table_info({TABLE_NAME})") as cursor:
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

    if "reminder_times" not in column_names:
        # Добавляем новое поле с дефолтным значением ["19:15"]
        default_times = json.dumps(["19:15"])
        await db.execute(f"""
            ALTER TABLE {TABLE_NAME}
            ADD COLUMN reminder_times TEXT DEFAULT '{default_times}'
        """)

        # Обновляем существующие записи
        await db.execute(f"""
            UPDATE {TABLE_NAME}
            SET reminder_times = '{default_times}'
            WHERE reminder_times IS NULL
        """)

        await db.commit()
        print("  ✅ Поле reminder_times добавлено (по умолчанию ['19:15'])")
    else:
        print("  ⏭️  Поле reminder_times уже существует")

    print("  ✅ Миграция завершена успешно!")

