FROM python:3.13-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости для сборки пакетов
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY main.py .
COPY config.py .
COPY bot_instance.py .
COPY filters.py .
COPY states.py .
COPY utils.py .
COPY database.py .
COPY handlers/ ./handlers/
COPY services/ ./services/
COPY config/ ./config/

# Создаем директорию для базы данных и логов
RUN mkdir -p /data

# Запускаем бота
CMD ["python", "-u", "main.py"]

