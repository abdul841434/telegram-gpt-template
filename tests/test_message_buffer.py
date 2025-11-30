"""
Тесты для буферизации сообщений.
"""

import asyncio

import pytest

from services.message_buffer import MessageBuffer


@pytest.mark.asyncio
async def test_single_message():
    """Тест обработки одного сообщения."""
    buffer = MessageBuffer()
    
    # Первое сообщение должно начать обработку
    should_process = await buffer.add_message(123, "привет")
    assert should_process is True
    
    # Получаем сообщения
    messages = await buffer.get_buffered_messages(123)
    assert messages == ["привет"]
    
    # Завершаем обработку
    has_more = await buffer.finish_processing(123)
    assert has_more is False


@pytest.mark.asyncio
async def test_multiple_messages_buffering():
    """Тест накопления нескольких сообщений в буфере."""
    buffer = MessageBuffer()
    
    # Первое сообщение - начинаем обработку
    should_process = await buffer.add_message(123, "привет")
    assert should_process is True
    
    # Второе и третье сообщения - должны попасть в буфер
    should_process = await buffer.add_message(123, "как дела")
    assert should_process is False
    
    should_process = await buffer.add_message(123, "я сплю")
    assert should_process is False
    
    # Получаем ВСЕ накопленные сообщения (включая первое)
    messages = await buffer.get_buffered_messages(123)
    assert messages == ["привет", "как дела", "я сплю"]
    
    # После get_buffered_messages буфер должен быть пуст
    has_buffered = await buffer.has_buffered_messages(123)
    assert has_buffered is False
    
    # Завершаем обработку - новых сообщений нет
    has_more = await buffer.finish_processing(123)
    assert has_more is False


@pytest.mark.asyncio
async def test_multiple_users():
    """Тест обработки сообщений от разных пользователей."""
    buffer = MessageBuffer()
    
    # Два пользователя отправляют сообщения
    should_process_1 = await buffer.add_message(111, "user1 msg1")
    should_process_2 = await buffer.add_message(222, "user2 msg1")
    
    assert should_process_1 is True
    assert should_process_2 is True
    
    # Оба отправляют еще по сообщению
    await buffer.add_message(111, "user1 msg2")
    await buffer.add_message(222, "user2 msg2")
    
    # Получаем ВСЕ сообщения первого пользователя
    messages_1 = await buffer.get_buffered_messages(111)
    assert messages_1 == ["user1 msg1", "user1 msg2"]
    
    # Получаем ВСЕ сообщения второго пользователя
    messages_2 = await buffer.get_buffered_messages(222)
    assert messages_2 == ["user2 msg1", "user2 msg2"]
    
    # После get_buffered_messages буферы должны быть пусты
    assert await buffer.has_buffered_messages(111) is False
    assert await buffer.has_buffered_messages(222) is False


@pytest.mark.asyncio
async def test_task_tracking():
    """Тест отслеживания текущей задачи обработки."""
    buffer = MessageBuffer()
    
    await buffer.add_message(123, "test")
    
    # Создаем фейковую задачу
    async def dummy_task():
        await asyncio.sleep(0.1)
        return "result"
    
    task = asyncio.create_task(dummy_task())
    await buffer.set_current_task(123, task)
    
    # Проверяем, что задача сохранена
    assert buffer.user_states[123]["current_task"] is task
    
    # Ждем завершения задачи
    await task
    
    # Завершаем обработку
    messages = await buffer.get_buffered_messages(123)
    await buffer.finish_processing(123)
    
    # Задача должна быть очищена
    assert buffer.user_states[123]["current_task"] is None


@pytest.mark.asyncio
async def test_concurrent_messages():
    """Тест обработки быстрых последовательных сообщений."""
    buffer = MessageBuffer()
    
    # Первое сообщение
    should_process = await buffer.add_message(123, "msg1")
    assert should_process is True
    
    # Симулируем быстрые сообщения
    tasks = []
    for i in range(2, 6):
        task = buffer.add_message(123, f"msg{i}")
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)
    
    # Все последующие сообщения должны попасть в буфер
    assert all(result is False for result in results)
    
    # Получаем все сообщения
    messages = await buffer.get_buffered_messages(123)
    assert len(messages) == 5
    assert messages == ["msg1", "msg2", "msg3", "msg4", "msg5"]


@pytest.mark.asyncio
async def test_empty_buffer_after_finish():
    """Тест очистки буфера после завершения обработки."""
    buffer = MessageBuffer()
    
    await buffer.add_message(123, "test")
    messages = await buffer.get_buffered_messages(123)
    
    # Буфер должен быть пуст после get_buffered_messages
    has_buffered = await buffer.has_buffered_messages(123)
    assert has_buffered is False
    
    # Завершаем обработку
    has_more = await buffer.finish_processing(123)
    assert has_more is False
    
    # processing флаг должен быть сброшен
    assert buffer.user_states[123]["processing"] is False


if __name__ == "__main__":
    # Для быстрого запуска тестов
    pytest.main([__file__, "-v"])

