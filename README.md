# 🎬 AniBot

Минималистичный Telegram-бот для просмотра аниме через Kodik API.

## ✨ Возможности

- 🔍 **Поиск аниме** по названию (русский, romaji, английский)
- 📺 **Просмотр информации** об аниме (жанры, описание, рейтинг)
- 🎥 **Прямая загрузка** видео в Telegram (4GB для Premium)
- 🌐 **Множество озвучек** (Субтитры, AniLibria, AniDub и др.)
- 📊 **Автоматическая синхронизация** с Kodik API
- 💾 **Кэширование** загруженных эпизодов
- 🚀 **Быстрый поиск** через PostgreSQL FTS

## 🏗️ Архитектура

```
┌─────────────┐
│  Telegram   │◄────────────────┐
│   Users     │                 │
└─────────────┘                 │
       │                        │
       ▼                        │
┌─────────────┐          ┌─────────────┐
│  Bot API    │          │  User API   │
│  (aiogram)  │          │ (Pyrogram)  │
└─────────────┘          └─────────────┘
       │                        ▲
       │                        │
       ▼                        │
┌─────────────────────────────────────┐
│         PostgreSQL Database         │
│  ┌───────┐ ┌─────────┐ ┌─────────┐ │
│  │ anime │ │ episode │ │ trans   │ │
│  └───────┘ └─────────┘ └─────────┘ │
└─────────────────────────────────────┘
       ▲                        │
       │                        │
┌──────┴────────┐      ┌────────┴────────┐
│  Delta Sync   │      │ Upload Worker   │
│    Worker     │      │                 │
└───────────────┘      └─────────────────┘
       ▲                        │
       │                        ▼
       │                 ┌─────────────┐
       └─────────────────┤  Kodik API  │
                         └─────────────┘
```

### Компоненты:

1. **Bot API (app.main)** - основной бот для команд и интерфейса
2. **Upload Worker** - скачивание и загрузка видео в Telegram
3. **Delta Sync Worker** - синхронизация изменений с Kodik
4. **Database** - PostgreSQL с FTS индексами
5. **Cache** - Redis для кэширования запросов

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
# Установка PostgreSQL и Redis
sudo apt update
sudo apt install postgresql redis-server ffmpeg

# Установка Poetry
curl -sSL https://install.python-poetry.org | python3 -

# Установка зависимостей проекта
poetry install
```

### 2. Настройка базы данных

```bash
# Создание БД
sudo -u postgres createdb anibot
sudo -u postgres psql anibot -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"

# Применение миграций
PYTHONPATH=. poetry run alembic upgrade head

# Начальный импорт данных (займет ~30-60 минут)
PYTHONPATH=. poetry run python -m app.workers.ingest_full
```

### 3. Настройка .env

```bash
cp env.example .env
nano .env
```

**Минимальная конфигурация:**

```env
# Токен бота от @BotFather
BOT_TOKEN="ваш_токен"

# API credentials от https://my.telegram.org/apps
USER_API_API_ID=12345678
USER_API_API_HASH="ваш_api_hash"

# Куда загружать видео
UPLOAD_CHAT_ID="me"  # или ID канала

# Прокси (если Telegram заблокирован)
TELEGRAM_PROXY_URL="socks5://127.0.0.1:1080"
```

📖 **Подробная инструкция:** [SETUP.md](./SETUP.md)

### 4. Запуск

```bash
# Все компоненты сразу
./scripts/start_all.sh

# Или по отдельности:
PYTHONPATH=. poetry run python -m app.main              # Бот
PYTHONPATH=. poetry run python -m app.workers.upload_worker  # Загрузчик
PYTHONPATH=. poetry run python -m app.workers.delta_sync     # Синхронизация
```

## 📊 Статистика

После импорта данных:

```bash
sudo -u postgres psql anibot -c "
SELECT 
  (SELECT COUNT(*) FROM anime) as аниме,
  (SELECT COUNT(*) FROM episode) as эпизодов,
  (SELECT COUNT(*) FROM translation) as озвучек;
"
```

Пример вывода:
```
 аниме  | эпизодов | озвучек
--------+----------+---------
  15023 |   382808 |     156
```

## 🛠️ Разработка

### Структура проекта

```
AniBot/
├── app/
│   ├── bot/           # Telegram bot (aiogram)
│   │   ├── handlers/  # Обработчики команд
│   │   └── routers.py # Роутинг
│   ├── db/            # Database layer
│   │   ├── models.py  # SQLAlchemy модели
│   │   └── repo.py    # Репозитории
│   ├── integrations/  # Внешние API
│   │   ├── kodik.py   # Kodik API клиент
│   │   └── telegram_uploader.py  # Pyrogram загрузчик
│   ├── services/      # Бизнес-логика
│   │   ├── downloader.py  # Скачивание видео
│   │   └── ingest.py      # Импорт данных
│   └── workers/       # Background workers
│       ├── ingest_full.py  # Полный импорт
│       ├── upload_worker.py # Загрузка видео
│       └── delta_sync.py    # Синхронизация
├── migrations/        # Alembic миграции
└── scripts/           # Вспомогательные скрипты
```

### Полезные команды

```bash
# Проверка линтером
poetry run ruff check app/

# Форматирование
poetry run ruff format app/

# Проверка типов
poetry run mypy app/

# Тесты
poetry run pytest

# Новая миграция
PYTHONPATH=. poetry run alembic revision --autogenerate -m "описание"

# Проверка Telegram API
poetry run python scripts/check_telegram.py
```

## 🐛 Troubleshooting

### Telegram API недоступен
```
TelegramNetworkError: Request timeout error
```
**Решение:** Настройте прокси в `.env` → `TELEGRAM_PROXY_URL`

### PEER_ID_INVALID при загрузке
```
[400 PEER_ID_INVALID]
```
**Решение:** Проверьте `UPLOAD_CHAT_ID`, добавьте бота в канал как админа

### Translation_id = 0
```
Episode X has invalid translation_id=0
```
**Решение:** Пересоздайте БД и импортируйте данные заново

### Ошибки миграций
```
sqlalchemy.exc.ProgrammingError
```
**Решение:** 
```bash
sudo -u postgres psql -c "DROP DATABASE anibot; CREATE DATABASE anibot;"
PYTHONPATH=. poetry run alembic upgrade head
```

## 📝 TODO

- [ ] Добавить web интерфейс для статистики
- [ ] Поддержка встроенных плееров (inline)
- [ ] Рекомендации на основе истории
- [ ] Экспорт списков аниме
- [ ] API для сторонних клиентов
- [ ] Docker compose для развертывания

## 📄 Лицензия

MIT

## 🤝 Контрибьюция

Pull requests приветствуются! Для крупных изменений сначала откройте issue.

## ⚠️ Disclaimer

Этот бот использует Kodik API для получения ссылок на видео. Убедитесь, что вы соблюдаете условия использования Kodik и имеете необходимые права на контент.

---

**Сделано с ❤️ для анимешников**
