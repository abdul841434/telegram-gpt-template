import asyncio
import json
import os
from datetime import UTC, datetime, timedelta, timezone

import aiosqlite
from dotenv import load_dotenv

load_dotenv()
LLM_TOKEN = os.environ.get("LLM_TOKEN")
DEBUG = bool(os.environ.get("DEBUG"))
DEBUG_CHAT = int(os.environ.get("DEBUG_CHAT"))
DATABASE_NAME = os.environ.get("DATABASE_NAME")
TABLE_NAME = os.environ.get("TABLE_NAME")
MAX_CONTEXT = int(os.environ.get("MAX_CONTEXT"))
MAX_STORAGE = int(os.environ.get("MAX_STORAGE", "100"))
DELAYED_REMINDERS_HOURS = int(os.environ.get("DELAYED_REMINDERS_HOURS"))
DELAYED_REMINDERS_MINUTES = int(os.environ.get("DELAYED_REMINDERS_MINUTES"))
TIMEZONE_OFFSET = int(os.environ.get("TIMEZONE_OFFSET"))
FROM_TIME = int(os.environ.get("FROM_TIME"))
TO_TIME = int(os.environ.get("TO_TIME"))


class User:
    def __init__(
        self,
        id,
        name=None,
        prompt=None,
        remind_of_yourself="2077-06-15 22:03:51",
        sub_lvl=0,
        sub_id=0,
        sub_period=-1,
        is_admin=0,
        active_messages_count=None,
    ):
        if prompt is None:
            prompt = []
        self.id = id
        self.name = name
        self.prompt = prompt  # Оставляем для обратной совместимости
        self.remind_of_yourself = remind_of_yourself
        self.sub_lvl = sub_lvl
        self.sub_id = sub_id
        self.sub_period = sub_period
        self.is_admin = is_admin
        self.active_messages_count = active_messages_count  # NULL = все, 0 = забыть, N = последние N

    def __repr__(self):
        return f"User(id={self.id}, \n name={self.name}, \n prompt={self.prompt}, \n remind_of_yourself={self.remind_of_yourself}, \n sub_lvl={self.sub_lvl}, \n sub_id={self.sub_id}, \n sub_period={self.sub_period}, \n is_admin={self.is_admin})"

    async def get_from_db(self):
        async with aiosqlite.connect(DATABASE_NAME) as db:
            cursor = await db.cursor()
            sql = f"SELECT * FROM {TABLE_NAME} WHERE id = ?"
            await cursor.execute(sql, (self.id,))
            row = await cursor.fetchone()
            if row:
                self.id = row[0]
                self.name = row[1]
                self.prompt = json.loads(row[2])
                self.remind_of_yourself = row[3]
                self.sub_lvl = row[4]
                self.sub_id = row[5]
                self.sub_period = row[6]
                self.is_admin = row[7]
                self.active_messages_count = row[8] if len(row) > 8 else None

    async def __call__(self, user_id):
        async with aiosqlite.connect(DATABASE_NAME) as db:
            cursor = await db.cursor()
            sql = f"SELECT * FROM {TABLE_NAME} WHERE id = ?"
            await cursor.execute(sql, (user_id,))
            row = await cursor.fetchone()
            if row:
                return User(
                    id=row[0],
                    name=row[1],
                    prompt=json.loads(row[2]),
                    remind_of_yourself=row[3],
                    sub_lvl=row[4],
                    sub_id=row[5],
                    sub_period=row[6],
                    is_admin=row[7],
                    active_messages_count=row[8] if len(row) > 8 else None,
                )
            return None

    async def get_ids_from_table():
        async with (
            aiosqlite.connect(DATABASE_NAME) as db,
            db.execute(f"SELECT id FROM {TABLE_NAME}") as cursor,
        ):
            rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def save_for_db(self):
        async with aiosqlite.connect(DATABASE_NAME) as db:
            cursor = await db.cursor()
            sql_insert = f"""
                        INSERT INTO {TABLE_NAME} (id, name, prompt, remind_of_yourself, sub_lvl, sub_id, sub_period, is_admin, active_messages_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
            values = (
                self.id,
                self.name,
                json.dumps(self.prompt),
                self.remind_of_yourself,
                self.sub_lvl,
                self.sub_id,
                self.sub_period,
                self.is_admin,
                self.active_messages_count,
            )
            await cursor.execute(sql_insert, values)
            await db.commit()
            await cursor.close()

    async def update_prompt(self, role, new_request):
        """
        Добавляет новое сообщение в таблицу messages.
        Старые сообщения (больше MAX_STORAGE) автоматически удаляются.
        """
        # Получаем текущее время с учетом часового пояса
        current_time = datetime.now(timezone(timedelta(hours=TIMEZONE_OFFSET)))
        timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")

        async with aiosqlite.connect(DATABASE_NAME) as db:
            # Добавляем новое сообщение
            await db.execute(
                """
                INSERT INTO messages (user_id, role, content, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (self.id, role, new_request, timestamp)
            )
            
            # Проверяем количество сообщений и удаляем старые, если превышен лимит
            async with db.execute(
                "SELECT COUNT(*) FROM messages WHERE user_id = ?",
                (self.id,)
            ) as cursor:
                count = (await cursor.fetchone())[0]
            
            if count > MAX_STORAGE:
                # Удаляем самые старые сообщения, оставляя только MAX_STORAGE последних
                await db.execute(
                    """
                    DELETE FROM messages 
                    WHERE user_id = ? 
                    AND id NOT IN (
                        SELECT id FROM messages 
                        WHERE user_id = ? 
                        ORDER BY id DESC 
                        LIMIT ?
                    )
                    """,
                    (self.id, self.id, MAX_STORAGE)
                )
            
            await db.commit()

    async def get_context_for_llm(self):
        """
        Возвращает сообщения для отправки в LLM с учетом active_messages_count:
        - NULL: возвращает последние MAX_CONTEXT сообщений
        - 0: возвращает пустой список (забыть всё)
        - N: возвращает последние N сообщений (но не больше MAX_CONTEXT)
        """
        async with aiosqlite.connect(DATABASE_NAME) as db:
            # Определяем сколько сообщений нужно получить
            if self.active_messages_count == 0:
                # Забыть всё
                return []
            elif self.active_messages_count is None:
                # Все сообщения (но не больше MAX_CONTEXT)
                limit = MAX_CONTEXT
            else:
                # Последние N сообщений (но не больше MAX_CONTEXT)
                limit = min(self.active_messages_count, MAX_CONTEXT)
            
            # Получаем сообщения
            async with db.execute(
                """
                SELECT role, content, timestamp 
                FROM messages 
                WHERE user_id = ? 
                ORDER BY id DESC 
                LIMIT ?
                """,
                (self.id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
            
            # Переворачиваем список (самые старые сначала)
            messages = [
                {
                    "role": row[0],
                    "content": row[1],
                    "timestamp": row[2]
                }
                for row in reversed(rows)
            ]
            
            return messages

    async def update_in_db(self):
        async with aiosqlite.connect(DATABASE_NAME) as db:
            cursor = await db.cursor()
            sql_query = f"""
                UPDATE {TABLE_NAME}
                SET name = ?, prompt = ?, remind_of_yourself = ?, sub_lvl = ?, sub_id = ?, sub_period = ?, is_admin = ?, active_messages_count = ?
                WHERE id = ?
            """
            values = (
                self.name,
                json.dumps(self.prompt),
                self.remind_of_yourself,
                self.sub_lvl,
                self.sub_id,
                self.sub_period,
                self.is_admin,
                self.active_messages_count,
                self.id,
            )
            await cursor.execute(sql_query, values)
            await db.commit()
            await cursor.close()


async def check_db():
    async with aiosqlite.connect(DATABASE_NAME) as db:
        async with db.cursor() as cursor:
            await cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                    id INTEGER PRIMARY KEY,  --  ID is now the PRIMARY KEY and NOT AUTOINCREMENT
                    name TEXT,
                    prompt JSON,
                    remind_of_yourself TEXT,
                    sub_lvl INTEGER,
                    sub_id TEXT,
                    sub_period INTEGER,
                    is_admin INTEGER
                )
                """
            )
        await db.commit()
        return "Бд подгружена успешно"


async def user_exists(user_id):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.cursor()
        sql = f"SELECT EXISTS(SELECT 1 FROM {TABLE_NAME} WHERE id = ?)"
        await cursor.execute(sql, (user_id,))
        result = (await cursor.fetchone())[0]
        await cursor.close()
    await db.close()

    return bool(result)


async def time_after(
    after_hours, after_minute, timezone_offset, lower_limit, upper_limit
):
    now_utc = datetime.now(UTC)
    now_localized = now_utc + timedelta(hours=timezone_offset)
    future_time = now_localized + timedelta(hours=after_hours, minutes=after_minute)
    future_hour = future_time.hour
    if lower_limit <= upper_limit:
        if lower_limit <= future_hour <= upper_limit:
            future_time = future_time.replace(
                hour=upper_limit, minute=0, second=0, microsecond=0
            )
    else:
        if lower_limit <= future_hour or future_hour < upper_limit:
            future_time = future_time.replace(
                hour=upper_limit, minute=0, second=0, microsecond=0
            )
    if future_time <= now_localized:
        future_time += timedelta(days=1)
    return future_time.strftime("%Y-%m-%d %H:%M:%S")


async def get_past_dates():
    past_user_ids = []
    async with aiosqlite.connect(DATABASE_NAME) as db:
        async with db.execute("PRAGMA journal_mode=WAL;") as cursor:
            await cursor.fetchone()

        now = datetime.now()

        query = f"SELECT {'id'}, {'remind_of_yourself'} FROM {TABLE_NAME}"

        async with db.execute(query) as cursor:
            results = await cursor.fetchall()
        for row in results:
            user_id = row[0]
            date_str = row[1]
            if date_str == "0":
                continue
            date_from_db = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            if date_from_db < now:
                past_user_ids.append(user_id)

    return past_user_ids


async def main():
    print(await User.get_ids_from_table())


if __name__ == "__main__":
    asyncio.run(main())
