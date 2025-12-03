"""
Миграция 009: Очистка устаревших placeholder-значений в имени.

Заменяет устаревшее значение "Not_of_registration" на пустую строку в поле name
таблицы conversations. Это значение использовалось в старых версиях кода как
placeholder для пользователей без имени, но теперь используется пустая строка.

Изменения:
- Замена "Not_of_registration" -> "" (пустая строка) в поле name
- Также заменяются другие устаревшие placeholder'ы типа "Unknown Chat"
"""

import aiosqlite

from database import DATABASE_NAME

# Уникальный идентификатор миграции
MIGRATION_ID = "migration_009_cleanup_legacy_names"


async def upgrade():
    """Применяет миграцию."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Получаем список устаревших значений для замены
        legacy_placeholders = [
            "Not_of_registration",
            "Unknown Chat",
            "Unknown chat",
        ]

        total_updated = 0

        for placeholder in legacy_placeholders:
            # Заменяем устаревшие placeholder'ы на пустую строку
            cursor = await db.execute(
                "UPDATE conversations SET name = '' WHERE name = ?",
                (placeholder,)
            )
            updated_count = cursor.rowcount
            total_updated += updated_count

            if updated_count > 0:
                print(f"   Обновлено {updated_count} записей с именем '{placeholder}'")

        await db.commit()

        if total_updated > 0:
            return f"Очищено {total_updated} устаревших значений имени"
        return "Устаревшие значения не найдены"


async def downgrade():
    """
    Откатывает миграцию.

    Примечание: откат не восстанавливает исходные значения,
    так как неизвестно какое именно значение было у каждой записи.
    """
    return "Откат не поддерживается для этой миграции (данные не могут быть восстановлены)"

