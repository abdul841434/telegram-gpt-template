"""
Миграция: Выделение сообщений в отдельную таблицу.

Переносит все сообщения из поля prompt (JSON) в отдельную таблицу messages.
Добавляет поле active_messages_count для управления контекстом.
"""

import json
import os

import aiosqlite
from dotenv import load_dotenv

load_dotenv()
TABLE_NAME = os.environ.get("TABLE_NAME", "users")


async def migrate(db: aiosqlite.Connection):
    """
    Создает таблицу messages и переносит туда все сообщения.
    Добавляет поле active_messages_count в таблицу users.
    """
    print("  📝 Создаем таблицу messages...")
    
    # Создаем таблицу messages
    await db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    
    # Создаем индексы для быстрого поиска
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_user_id 
        ON messages(user_id)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_timestamp 
        ON messages(timestamp)
    """)
    
    print("  📦 Переносим сообщения из prompt в messages...")
    
    # Получаем всех пользователей с их историей
    async with db.execute(f"SELECT id, prompt FROM {TABLE_NAME}") as cursor:
        users = await cursor.fetchall()
    
    total_messages = 0
    users_migrated = 0
    
    for user_id, prompt_json in users:
        if not prompt_json or prompt_json == "[]":
            continue
        
        try:
            messages = json.loads(prompt_json)
            
            if not messages:
                continue
            
            # Переносим каждое сообщение в таблицу messages
            for message in messages:
                role = message.get("role")
                content = message.get("content")
                timestamp = message.get("timestamp")
                
                if role and content:
                    await db.execute(
                        """
                        INSERT INTO messages (user_id, role, content, timestamp)
                        VALUES (?, ?, ?, ?)
                        """,
                        (user_id, role, content, timestamp)
                    )
                    total_messages += 1
            
            users_migrated += 1
            
        except json.JSONDecodeError:
            print(f"  ⚠️  Ошибка парсинга JSON для пользователя {user_id}")
            continue
    
    await db.commit()
    
    print(f"  📊 Перенесено {total_messages} сообщений от {users_migrated} пользователей")
    
    # Добавляем поле active_messages_count в таблицу users
    print("  🔧 Добавляем поле active_messages_count в таблицу users...")
    
    # Проверяем, существует ли уже это поле
    async with db.execute(f"PRAGMA table_info({TABLE_NAME})") as cursor:
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
    
    if "active_messages_count" not in column_names:
        # Добавляем новое поле (NULL = все сообщения активны)
        await db.execute(f"""
            ALTER TABLE {TABLE_NAME} 
            ADD COLUMN active_messages_count INTEGER DEFAULT NULL
        """)
        await db.commit()
        print("  ✅ Поле active_messages_count добавлено")
    else:
        print("  ⏭️  Поле active_messages_count уже существует")
    
    # Очищаем старое поле prompt (оставляем пустым для обратной совместимости)
    print("  🧹 Очищаем старое поле prompt...")
    await db.execute(f"UPDATE {TABLE_NAME} SET prompt = '[]'")
    await db.commit()
    
    print("  ✅ Миграция завершена успешно!")

