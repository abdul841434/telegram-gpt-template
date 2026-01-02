#!/bin/bash

# Скрипт для подготовки GitHub Secrets для CI/CD с Yandex Cloud

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "================================================"
echo "🔑 ПОДГОТОВКА GITHUB SECRETS ДЛЯ CI/CD"
echo "================================================"
echo ""

# Проверяем наличие yc CLI
if ! command -v yc &> /dev/null; then
    echo -e "${RED}❌ Yandex Cloud CLI (yc) не установлен!${NC}"
    echo "Установите его: https://cloud.yandex.ru/docs/cli/quickstart"
    exit 1
fi

# Проверяем наличие jq
if ! command -v jq &> /dev/null; then
    echo -e "${RED}❌ Утилита jq не установлена!${NC}"
    echo "Установите её:"
    echo "  macOS: brew install jq"
    echo "  Ubuntu: sudo apt-get install jq"
    echo "  CentOS: sudo yum install jq"
    exit 1
fi

# Функция для получения значения с подсказкой
get_value_or_ask() {
    local var_name=$1
    local prompt=$2
    local value=${!var_name}
    
    if [ -z "$value" ]; then
        read -p "$prompt: " value
    fi
    echo "$value"
}

echo "📝 Собираем информацию о Yandex Cloud..."
echo ""

# 1. Cloud ID и Folder ID
CLOUD_ID=$(yc config list | grep cloud-id | awk '{print $2}')
FOLDER_ID=$(yc config list | grep folder-id | awk '{print $2}')

if [ -z "$CLOUD_ID" ] || [ -z "$FOLDER_ID" ]; then
    echo -e "${RED}❌ Yandex Cloud не настроен!${NC}"
    echo "Выполните: yc init"
    exit 1
fi

# 2. Выбор Container Registry
echo "📦 Доступные Container Registry:"
yc container registry list
echo ""
read -p "Введите Registry ID (crp...) или оставьте пустым для создания нового: " REGISTRY_ID

if [ -z "$REGISTRY_ID" ]; then
    read -p "Введите имя нового Registry [telegram-gpt-registry]: " REGISTRY_NAME
    REGISTRY_NAME=${REGISTRY_NAME:-telegram-gpt-registry}
    
    echo "Создаем Container Registry..."
    REGISTRY_ID=$(yc container registry create --name "$REGISTRY_NAME" --format json | jq -r .id)
    echo -e "${GREEN}✅ Container Registry создан: $REGISTRY_NAME ($REGISTRY_ID)${NC}"
fi

# 3. Выбор Service Account
echo ""
echo "👤 Доступные Service Accounts:"
yc iam service-account list
echo ""
read -p "Введите ID Service Account (aje...) или оставьте пустым для создания нового: " SA_ID

if [ -z "$SA_ID" ]; then
    read -p "Введите имя нового Service Account [github-actions-sa]: " SA_NAME
    SA_NAME=${SA_NAME:-github-actions-sa}
    
    echo "Создаем Service Account..."
    SA_ID=$(yc iam service-account create --name "$SA_NAME" --format json | jq -r .id)
    
    echo "Назначаем права на Registry..."
    yc container registry add-access-binding \
      --id "$REGISTRY_ID" \
      --service-account-id "$SA_ID" \
      --role container-registry.images.pusher
    
    yc container registry add-access-binding \
      --id "$REGISTRY_ID" \
      --service-account-id "$SA_ID" \
      --role container-registry.images.puller
    
    echo -e "${GREEN}✅ Service Account создан: $SA_ID${NC}"
else
    # Проверяем права существующего Service Account
    echo ""
    echo "🔍 Проверяем права Service Account на Registry..."
    
    BINDINGS=$(yc container registry list-access-bindings --id "$REGISTRY_ID" --format json)
    HAS_PUSHER=$(echo "$BINDINGS" | jq -r ".[] | select(.subject.id==\"$SA_ID\" and .role_id==\"container-registry.images.pusher\") | .role_id")
    HAS_PULLER=$(echo "$BINDINGS" | jq -r ".[] | select(.subject.id==\"$SA_ID\" and .role_id==\"container-registry.images.puller\") | .role_id")
    
    NEEDS_UPDATE=false
    
    if [ -z "$HAS_PUSHER" ]; then
        echo -e "${YELLOW}⚠️  Права pusher отсутствуют, добавляем...${NC}"
        yc container registry add-access-binding \
          --id "$REGISTRY_ID" \
          --service-account-id "$SA_ID" \
          --role container-registry.images.pusher
        NEEDS_UPDATE=true
    else
        echo -e "${GREEN}✅ Права pusher уже есть${NC}"
    fi
    
    if [ -z "$HAS_PULLER" ]; then
        echo -e "${YELLOW}⚠️  Права puller отсутствуют, добавляем...${NC}"
        yc container registry add-access-binding \
          --id "$REGISTRY_ID" \
          --service-account-id "$SA_ID" \
          --role container-registry.images.puller
        NEEDS_UPDATE=true
    else
        echo -e "${GREEN}✅ Права puller уже есть${NC}"
    fi
    
    if [ "$NEEDS_UPDATE" = false ]; then
        echo -e "${GREEN}✅ Все права уже настроены${NC}"
    fi
fi

# 4. Создаем ключ для Service Account
echo ""
echo "🔑 Создаем ключ для Service Account..."
KEY_FILE="/tmp/yc-sa-key-$$.json"
yc iam key create --service-account-id "$SA_ID" --output "$KEY_FILE" > /dev/null

# 5. IP адрес сервера
YC_INSTANCE_IP=$(get_value_or_ask "YC_INSTANCE_IP" "Введите IP адрес сервера")

# 6. Пользователь SSH
YC_INSTANCE_USER=$(get_value_or_ask "YC_INSTANCE_USER" "Введите SSH пользователя на сервере")

# 7. Находим SSH ключ
echo ""
echo "🔍 Ищем SSH ключи..."
SSH_KEY_PATH=""

# Собираем все доступные SSH ключи
SSH_KEYS=()

# Проверяем переменную окружения
if [ -n "$SSH_PRIVATE_KEY_PATH" ] && [ -f "$SSH_PRIVATE_KEY_PATH" ]; then
    SSH_KEYS+=("$SSH_PRIVATE_KEY_PATH")
fi

# Ищем ключи Yandex Cloud по паттерну с пользователем
shopt -s nullglob
for key in ~/.ssh/yc-*"$YC_INSTANCE_USER"; do
    if [ -f "$key" ] && [[ ! "$key" =~ \.pub$ ]] && [[ ! "$key" =~ -cert\.pub$ ]]; then
        SSH_KEYS+=("$key")
    fi
done

# Ищем ключи Yandex Cloud общие
for key in ~/.ssh/yc-*; do
    if [ -f "$key" ] && [[ ! "$key" =~ \.pub$ ]] && [[ ! "$key" =~ -cert\.pub$ ]]; then
        # Проверяем, что ключ еще не добавлен
        if [[ ! " ${SSH_KEYS[@]} " =~ " ${key} " ]]; then
            SSH_KEYS+=("$key")
        fi
    fi
done
shopt -u nullglob

# Проверяем стандартные ключи
if [ -f ~/.ssh/id_rsa ] && [[ ! " ${SSH_KEYS[@]} " =~ " $HOME/.ssh/id_rsa " ]]; then
    SSH_KEYS+=("$HOME/.ssh/id_rsa")
fi
if [ -f ~/.ssh/id_ed25519 ] && [[ ! " ${SSH_KEYS[@]} " =~ " $HOME/.ssh/id_ed25519 " ]]; then
    SSH_KEYS+=("$HOME/.ssh/id_ed25519")
fi

# Если ключей несколько - даем выбрать
if [ ${#SSH_KEYS[@]} -eq 0 ]; then
    echo -e "${YELLOW}⚠️  SSH ключи не найдены${NC}"
    read -p "Введите путь к SSH приватному ключу: " SSH_KEY_PATH
elif [ ${#SSH_KEYS[@]} -eq 1 ]; then
    SSH_KEY_PATH="${SSH_KEYS[0]}"
    echo -e "${GREEN}✅ Найден ключ: $SSH_KEY_PATH${NC}"
else
    echo -e "${YELLOW}📋 Найдено несколько SSH ключей:${NC}"
    for i in "${!SSH_KEYS[@]}"; do
        # Извлекаем только имя файла для более читаемого вывода
        KEY_NAME=$(basename "${SSH_KEYS[$i]}")
        echo "  $((i+1))) $KEY_NAME"
        echo "     Путь: ${SSH_KEYS[$i]}"
    done
    echo ""
    
    # Проверяем подключение для каждого ключа
    echo "🔍 Проверяем подключение к серверу $YC_INSTANCE_USER@$YC_INSTANCE_IP..."
    WORKING_KEYS=()
    for key in "${SSH_KEYS[@]}"; do
        KEY_NAME=$(basename "$key")
        if ssh -i "$key" -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes "$YC_INSTANCE_USER@$YC_INSTANCE_IP" "exit" 2>/dev/null; then
            echo -e "${GREEN}✅ $KEY_NAME - работает${NC}"
            WORKING_KEYS+=("$key")
        else
            echo -e "${RED}❌ $KEY_NAME - не подходит${NC}"
        fi
    done
    
    if [ ${#WORKING_KEYS[@]} -eq 0 ]; then
        echo ""
        echo -e "${RED}❌ Ни один из ключей не подошел!${NC}"
        echo "Возможные причины:"
        echo "  - Неверный IP адрес или имя пользователя"
        echo "  - Сервер недоступен"
        echo "  - Ключи не настроены на сервере"
        echo ""
        read -p "Введите путь к SSH приватному ключу вручную: " SSH_KEY_PATH
    elif [ ${#WORKING_KEYS[@]} -eq 1 ]; then
        SSH_KEY_PATH="${WORKING_KEYS[0]}"
        KEY_NAME=$(basename "$SSH_KEY_PATH")
        echo ""
        echo -e "${GREEN}✅ Автоматически выбран рабочий ключ: $KEY_NAME${NC}"
        echo "   Путь: $SSH_KEY_PATH"
    else
        echo ""
        echo -e "${YELLOW}📋 Найдено ${#WORKING_KEYS[@]} рабочих ключа:${NC}"
        for i in "${!WORKING_KEYS[@]}"; do
            KEY_NAME=$(basename "${WORKING_KEYS[$i]}")
            echo "  $((i+1))) $KEY_NAME"
            echo "     Путь: ${WORKING_KEYS[$i]}"
        done
        echo ""
        read -p "Выберите номер ключа (1-${#WORKING_KEYS[@]}): " KEY_NUM
        
        # Проверка корректности ввода
        if [[ ! "$KEY_NUM" =~ ^[0-9]+$ ]] || [ "$KEY_NUM" -lt 1 ] || [ "$KEY_NUM" -gt ${#WORKING_KEYS[@]} ]; then
            echo -e "${RED}❌ Некорректный выбор!${NC}"
            rm -f "$KEY_FILE"
            exit 1
        fi
        
        SSH_KEY_PATH="${WORKING_KEYS[$((KEY_NUM-1))]}"
        KEY_NAME=$(basename "$SSH_KEY_PATH")
        echo -e "${GREEN}✅ Выбран ключ: $KEY_NAME${NC}"
    fi
fi

if [ ! -f "$SSH_KEY_PATH" ]; then
    echo -e "${RED}❌ SSH ключ не найден: $SSH_KEY_PATH${NC}"
    rm -f "$KEY_FILE"
    exit 1
fi

# Финальная проверка подключения
echo ""
echo "🔍 Проверяем SSH подключение..."
if ssh -i "$SSH_KEY_PATH" -o ConnectTimeout=10 -o StrictHostKeyChecking=no "$YC_INSTANCE_USER@$YC_INSTANCE_IP" "echo '✅ SSH подключение работает'" 2>/dev/null; then
    echo -e "${GREEN}✅ SSH ключ подтвержден: $SSH_KEY_PATH${NC}"
else
    echo -e "${RED}❌ SSH подключение не работает с этим ключом!${NC}"
    echo "Проверьте:"
    echo "  - Правильность IP адреса: $YC_INSTANCE_IP"
    echo "  - Правильность пользователя: $YC_INSTANCE_USER"
    echo "  - Доступность сервера"
    rm -f "$KEY_FILE"
    exit 1
fi

# Вывод результатов
echo ""
echo "================================================"
echo "✅ GITHUB SECRETS ГОТОВЫ"
echo "================================================"
echo ""
echo -e "${YELLOW}📋 Скопируйте каждую переменную в GitHub:${NC}"
echo "Settings → Secrets and variables → Actions → New repository secret"
echo ""
echo "================================================"
echo ""

# Yandex Cloud конфигурация
echo "1️⃣  YC_CLOUD_ID"
echo "---"
echo "$CLOUD_ID"
echo ""

echo "2️⃣  YC_FOLDER_ID"
echo "---"
echo "$FOLDER_ID"
echo ""

echo "3️⃣  YC_REGISTRY_ID"
echo "---"
echo "$REGISTRY_ID"
echo ""

echo "4️⃣  YC_INSTANCE_IP"
echo "---"
echo "$YC_INSTANCE_IP"
echo ""

echo "5️⃣  YC_INSTANCE_USER"
echo "---"
echo "$YC_INSTANCE_USER"
echo ""

# Service Account JSON
echo "6️⃣  YC_SA_JSON_CREDENTIALS"
echo "---"
cat "$KEY_FILE"
echo ""

# SSH ключ
echo "7️⃣  SSH_PRIVATE_KEY"
echo "---"
cat "$SSH_KEY_PATH"
echo ""

# Удаляем временный файл
rm -f "$KEY_FILE"

echo "================================================"
echo "📝 ОБЯЗАТЕЛЬНЫЕ СЕКРЕТЫ TELEGRAM БОТА"
echo "================================================"
echo ""

echo "8️⃣  TG_TOKEN"
echo "---"
echo "Получите токен у @BotFather"
echo "Формат: 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
echo ""

echo "9️⃣  LLM_TOKEN"
echo "---"
echo "Получите токен на https://openrouter.ai/keys"
echo "Формат: sk-or-v1-..."
echo ""

echo "🔟 ADMIN_CHAT"
echo "---"
echo "Получите ваш chat ID у @userinfobot"
echo "Формат: 123456789"
echo ""

echo "================================================"
echo "⚙️  ОПЦИОНАЛЬНЫЕ СЕКРЕТЫ (есть дефолты)"
echo "================================================"
echo ""

echo "1️⃣1️⃣  MODEL (опционально, по умолчанию: google/gemini-2.0-flash-exp:free)"
echo "---"
echo "Примеры моделей:"
echo "  - google/gemini-2.0-flash-exp:free"
echo "  - anthropic/claude-3.5-sonnet"
echo "  - openai/gpt-4"
echo ""

echo "1️⃣2️⃣  MAX_CONTEXT (опционально, по умолчанию: 20)"
echo "---"
echo "Количество сообщений в контексте"
echo ""

echo "1️⃣3️⃣  MAX_STORAGE (опционально, по умолчанию: 100)"
echo "---"
echo "Количество сообщений для хранения в БД"
echo ""

echo "1️⃣4️⃣  FEEDBACK_FORM_URL (опционально)"
echo "---"
echo "Ссылка на Google форму для обратной связи"
echo ""

echo "1️⃣5️⃣  REQUIRED_CHANNELS (опционально)"
echo "---"
echo "Список обязательных каналов для подписки (через запятую)"
echo "Формат: @channel1,@channel2"
echo ""

echo "1️⃣6️⃣  FILE_LOG_LEVEL (опционально, по умолчанию: INFO)"
echo "---"
echo "Уровень логирования в файл: DEBUG, INFO, WARNING, ERROR"
echo ""

echo "1️⃣7️⃣  TELEGRAM_LOG_LEVEL (опционально, по умолчанию: DISABLED)"
echo "---"
echo "Уровень логирования в Telegram: DISABLED, INFO, WARNING, ERROR"
echo ""

echo "================================================"
echo "✅ ГОТОВО!"
echo "================================================"
echo ""
echo "📌 Следующие шаги:"
echo "1. Скопируйте все значения выше в GitHub Secrets"
echo "2. Запустите деплой: git push origin main"
echo "3. Проверьте статус в GitHub Actions"
echo ""

