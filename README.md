# 🏠 Krisha.kz Telegram Bot

Бот для поиска квартир в Алматы на [Krisha.kz](https://krisha.kz) с автоматическими уведомлениями о новых объявлениях.

## Возможности

- 🔍 **Поиск по фильтрам**: комнаты, цена, площадь
- 🆕 **Автоуведомления**: бот проверяет новые объявления каждые 5 минут
- 📸 **Фото и описание**: полная информация о квартире
- 🗺 **Районы Алматы**: поиск только по городу Алматы
- 💾 **База данных**: SQLite для хранения истории

## Установка

### 1. Получи токен бота

1. Напиши [@BotFather](https://t.me/BotFather) в Telegram
2. Создай нового бота командой `/newbot`
3. Скопируй токен (выглядит как `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Узнай свой Telegram ID

Напиши [@userinfobot](https://t.me/userinfobot) и скопируй ID.

### 3. Установи зависимости

```bash
pip install -r requirements.txt
```

### 4. Настрой переменные окружения

Скопируй `.env.example` в `.env` и заполни:

```bash
cp .env.example .env
```

Отредактируй `.env`:
```env
BOT_TOKEN=your_bot_token_here
ADMIN_ID=your_telegram_id
CHECK_INTERVAL=300
```

### 5. Запусти бота

```bash
python bot.py
```

## Команды

| Команда | Описание |
|---------|----------|
| `/start` | Главное меню |
| `/filters` | Настроить фильтры |
| `/search` | Найти квартиры сейчас |
| `/myfilters` | Показать мои фильтры |
| `/stop` | Остановить уведомления |
| `/help` | Помощь |

## Фильтры поиска

- 🛏 **Комнаты**: 1, 2, 3, 4+ или любое
- 💰 **Цена**: от/до в тенге
- 📐 **Площадь**: от/до в м²

## Запуск на сервере (24/7)

Для постоянной работы рекомендуется:

### VPS (PythonAnywhere, DigitalOcean, Hetzner)

```bash
# Установка
pip install -r requirements.txt

# Запуск через systemd или screen/tmux
screen -S krisha_bot
python bot.py
# Ctrl+A, D для выхода из screen
```

### Docker (опционально)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

## ⚠️ Важно

- Сайт Krisha.kz использует защиту от ботов. При частых запросах возможна блокировка IP.
- Рекомендуется интервал проверки **не менее 300 секунд (5 минут)**.
- Бот создан для личного использования. Коммерческое использование может нарушать правила сайта.
- Для стабильной работы рассмотри использование [официального API](https://auto-parser.ru/parser_krisha_kz) (платно).

## Структура проекта

```
krisha_telegram_bot/
├── bot.py           # Основной файл бота
├── parser.py        # Парсер Krisha.kz
├── database.py      # Работа с SQLite
├── config.py        # Конфигурация
├── requirements.txt # Зависимости
├── .env.example     # Пример переменных
└── bot_data.db      # База данных (создается автоматически)
```

## Лицензия

MIT License — для личного использования.
