# Тестирование

## Обзор

Проект включает набор тестов для критичных компонентов, обеспечивающих корректную работу основных функций бота.

## Запуск тестов

### Все тесты

```bash
pytest
```

### С покрытием кода

```bash
pytest --cov=. --cov-report=html
```

После выполнения отчет будет доступен в `htmlcov/index.html`.

### Конкретный тест

```bash
# Один файл
pytest tests/test_message_buffer.py -v

# Конкретный тест
pytest tests/test_message_buffer.py::test_buffer_accumulation -v
```

### С подробным выводом

```bash
pytest -v -s
```

- `-v` — verbose mode (подробный вывод)
- `-s` — показывать print-ы и логи

## Покрытие тестами

### Текущие тесты

#### `test_message_buffer.py`
Тестирует буферизацию сообщений:
- Добавление сообщений в буфер
- Получение накопленных сообщений
- Обработка состояния буфера
- Завершение обработки

#### `test_forget_command.py`
Тестирует команду `/forget`:
- Сброс истории диалога
- Очистка контекста пользователя
- Корректная работа в БД

#### `test_telegram_error_parsing.py`
Тестирует парсинг ошибок Telegram API:
- Извлечение entity offset из ошибок
- Обработка различных форматов ошибок
- Корректная обработка некорректных данных

#### `test_markdown_fix.py`
Тестирует исправление Markdown:
- Экранирование специальных символов
- Корректная обработка форматирования
- Совместимость с Telegram API

#### `test_dispatch_all.py`
Тестирует массовую рассылку:
- Отправка сообщений всем пользователям
- Обработка ошибок при отправке
- Подсчет успешных/неудачных отправок

## Структура тестов

```
tests/
├── __init__.py
├── README.md
├── test_message_buffer.py      # Буферизация сообщений
├── test_forget_command.py       # Команда /forget
├── test_telegram_error_parsing.py  # Парсинг ошибок Telegram
├── test_markdown_fix.py         # Исправление Markdown
└── test_dispatch_all.py         # Массовая рассылка
```

## Написание новых тестов

### Базовая структура

```python
import pytest
from unittest.mock import AsyncMock, Mock, patch

@pytest.mark.asyncio
async def test_my_function():
    """Описание того, что тестируется."""
    # Arrange (подготовка)
    mock_data = {"key": "value"}
    
    # Act (выполнение)
    result = await my_function(mock_data)
    
    # Assert (проверка)
    assert result is not None
    assert result["key"] == "expected_value"
```

### Использование фикстур

```python
import pytest

@pytest.fixture
async def mock_database():
    """Фикстура для тестовой БД."""
    db = await create_test_database()
    yield db
    await db.close()

@pytest.mark.asyncio
async def test_with_fixture(mock_database):
    """Тест с использованием фикстуры."""
    result = await mock_database.query("SELECT * FROM users")
    assert len(result) == 0
```

### Мокирование aiogram

```python
from unittest.mock import AsyncMock, Mock
from aiogram.types import Message, User, Chat

@pytest.mark.asyncio
async def test_handler():
    """Тест обработчика сообщений."""
    # Создаем mock объекты
    mock_message = Mock(spec=Message)
    mock_message.from_user = Mock(spec=User)
    mock_message.from_user.id = 12345
    mock_message.chat = Mock(spec=Chat)
    mock_message.chat.id = 12345
    mock_message.text = "test message"
    mock_message.answer = AsyncMock()
    
    # Вызываем хандлер
    await my_handler(mock_message)
    
    # Проверяем вызов
    mock_message.answer.assert_called_once()
```

### Мокирование LLM API

```python
from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
@patch('services.llm_client.LLMClient.get_completion')
async def test_llm_interaction(mock_get_completion):
    """Тест взаимодействия с LLM."""
    # Настраиваем mock
    mock_get_completion.return_value = "Mocked response"
    
    # Вызываем функцию
    result = await process_user_message(123, "test message")
    
    # Проверяем
    assert result == "Mocked response"
    mock_get_completion.assert_called_once()
```

## Continuous Integration

Тесты автоматически запускаются при каждом push через GitHub Actions:

```yaml
- name: Run tests
  run: |
    pytest --cov=. --cov-report=xml
```

См. `.github/workflows/deploy.yml` для полной конфигурации.

## Best Practices

### 1. Именование тестов

```python
# Хорошо
def test_buffer_accumulates_multiple_messages():
    pass

# Плохо
def test1():
    pass
```

### 2. Один тест — одна проверка

```python
# Хорошо
def test_user_creation():
    user = create_user("test")
    assert user.name == "test"

def test_user_has_id():
    user = create_user("test")
    assert user.id is not None

# Плохо (слишком много проверок)
def test_user():
    user = create_user("test")
    assert user.name == "test"
    assert user.id is not None
    assert user.created_at is not None
    assert user.is_active is True
```

### 3. Используйте осмысленные assert сообщения

```python
# Хорошо
assert len(users) == 5, f"Expected 5 users, got {len(users)}"

# Плохо
assert len(users) == 5
```

### 4. Очистка после тестов

```python
@pytest.fixture
async def temp_file():
    """Создает временный файл."""
    file_path = "/tmp/test_file.txt"
    with open(file_path, "w") as f:
        f.write("test")
    
    yield file_path
    
    # Очистка
    if os.path.exists(file_path):
        os.remove(file_path)
```

## Отладка тестов

### Запуск с отладчиком

```bash
pytest --pdb
```

При ошибке откроется интерактивный отладчик.

### Запуск последнего упавшего теста

```bash
pytest --lf
```

### Просмотр логов

```bash
pytest -v -s --log-cli-level=DEBUG
```

## Метрики покрытия

Для просмотра покрытия по модулям:

```bash
pytest --cov=core --cov=handlers --cov=services --cov-report=term-missing
```

Вывод покажет:
- Процент покрытия по каждому файлу
- Строки, не покрытые тестами

## Необходимые зависимости

```txt
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
```

Установка:

```bash
pip install -r requirements/requirements-dev.txt
```

## Будущие улучшения

### Планируется добавить тесты для:

- [ ] Обработки фото и видео
- [ ] Групповых чатов
- [ ] Системы подписок
- [ ] Реферальной системы
- [ ] Миграций БД
- [ ] Статистики

### Планируется добавить:

- [ ] Integration тесты (с реальной БД)
- [ ] E2E тесты (с тестовым ботом)
- [ ] Performance тесты
- [ ] Load тесты

## Дополнительные ресурсы

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
- [Testing aiogram bots](https://docs.aiogram.dev/en/latest/dispatcher/testing.html)

