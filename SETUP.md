# 🚀 Инструкция по запуску AniBot

## 1️⃣ Настройка .env файла

Скопируйте `env.example` в `.env` и заполните:

```bash
cp env.example .env
nano .env
```

### Обязательные параметры:

```env
# ===== TELEGRAM BOT =====
BOT_TOKEN="ваш_токен_от_@BotFather"

# ===== USER API (для загрузки видео) =====
# Получите на https://my.telegram.org/apps
USER_API_API_ID=12345678
USER_API_API_HASH="ваш_api_hash"

# Сессия Pyrogram - создается автоматически при первом запуске
# Оставьте пустым, программа попросит код из Telegram
USER_API_SESSION_STRING=""

# ===== КАНАЛ ДЛЯ ВИДЕО =====
# Вариант 1: ID канала (например: -1001234567890)
# Вариант 2: "me" для Избранного
UPLOAD_CHAT_ID="me"

# ===== ПРОКСИ (если Telegram заблокирован) =====
# Для SOCKS5:
TELEGRAM_PROXY_URL="socks5://127.0.0.1:1080"
# Для HTTP:
# TELEGRAM_PROXY_URL="http://user:pass@host:port"
```

### Получение токенов:

1. **BOT_TOKEN**: 
   - Напишите [@BotFather](https://t.me/BotFather)
   - Команда: `/newbot`
   - Следуйте инструкциям

2. **USER_API_API_ID и USER_API_API_HASH**:
   - Откройте https://my.telegram.org/apps
   - Войдите в аккаунт
   - Создайте приложение
   - Скопируйте `api_id` и `api_hash`

3. **USER_API_SESSION_STRING**:
   - При первом запуске worker попросит код из Telegram
   - После авторизации строка сохранится автоматически

4. **UPLOAD_CHAT_ID**:
   - Для Избранного: `"me"`
   - Для канала: 
     - Создайте канал
     - Добавьте бота как админа
     - Найдите ID канала (например, через [@userinfobot](https://t.me/userinfobot))
     - Формат: `-1001234567890`

## 2️⃣ Настройка прокси (если Telegram заблокирован)

### Проверка доступности Telegram:

```bash
poetry run python scripts/check_telegram.py
```

### Варианты решения:

#### ✅ Вариант 1: VPN (рекомендуется)
Подключитесь к VPN на уровне системы.

#### ✅ Вариант 2: SSH туннель
```bash
# На удаленном сервере с доступом к Telegram:
ssh -D 1080 -N user@your_server

# В .env:
TELEGRAM_PROXY_URL="socks5://127.0.0.1:1080"
```

#### ✅ Вариант 3: Shadowsocks
```bash
sudo apt install shadowsocks-libev
# Настройте конфиг в /etc/shadowsocks-libev/config.json
sudo systemctl start shadowsocks-libev

# В .env:
TELEGRAM_PROXY_URL="socks5://127.0.0.1:1080"
```

## 3️⃣ Запуск компонентов

### Вариант A: Все сразу (удобно для тестирования)

```bash
./scripts/start_all.sh
```

### Вариант B: По отдельности (для продакшена)

#### 1. Основной бот (команды в Telegram)
```bash
PYTHONPATH=. poetry run python -m app.main
```

#### 2. Upload worker (скачивание и загрузка видео)
```bash
PYTHONPATH=. poetry run python -m app.workers.upload_worker
```

#### 3. Delta sync worker (синхронизация с Kodik)
```bash
PYTHONPATH=. poetry run python -m app.workers.delta_sync
```

## 4️⃣ Проверка работы

### Проверка БД:
```bash
sudo -u postgres psql anibot -c "SELECT COUNT(*) FROM anime;"
sudo -u postgres psql anibot -c "SELECT COUNT(*) FROM episode;"
```

### Проверка логов:
```bash
# Upload worker
tail -f /tmp/anibot_upload.log

# Основной бот
# Логи в консоли
```

### Тест бота в Telegram:
1. Найдите вашего бота по username
2. Отправьте `/start`
3. Попробуйте поиск: `Hunter x Hunter`

## 5️⃣ Troubleshooting

### ❌ Telegram API недоступен
```
TelegramNetworkError: Request timeout error
```
**Решение:** Настройте прокси (см. раздел 2️⃣)

### ❌ PEER_ID_INVALID при загрузке
```
[400 PEER_ID_INVALID] - The peer id being used is invalid
```
**Решение:** 
- Проверьте `UPLOAD_CHAT_ID` в `.env`
- Для канала: добавьте бота как админа
- Для "me": убедитесь что `USER_API_SESSION_STRING` настроен

### ❌ Translation_id = 0
```
Episode X has invalid translation_id=0, skipping
```
**Решение:** Уже исправлено! Если видите эту ошибку, обновите код.

### ❌ Ошибка миграции БД
```
sqlalchemy.exc.ProgrammingError
```
**Решение:**
```bash
# Сброс миграций
sudo -u postgres psql -c "DROP DATABASE IF EXISTS anibot;"
sudo -u postgres psql -c "CREATE DATABASE anibot OWNER postgres;"

# Применить заново
PYTHONPATH=. poetry run alembic upgrade head

# Повторить импорт
PYTHONPATH=. poetry run python -m app.workers.ingest_full
```

## 6️⃣ Systemd службы (для автозапуска)

Создайте файлы служб:

```bash
# /etc/systemd/system/anibot-main.service
[Unit]
Description=AniBot Main Bot
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=sowhoia
WorkingDirectory=/home/sowhoia/Projects/AniBot
Environment="PYTHONPATH=/home/sowhoia/Projects/AniBot"
ExecStart=/home/sowhoia/.local/bin/poetry run python -m app.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Активация:
```bash
sudo systemctl daemon-reload
sudo systemctl enable anibot-main
sudo systemctl start anibot-main
sudo systemctl status anibot-main
```

## 7️⃣ Мониторинг

### Статистика БД:
```bash
sudo -u postgres psql anibot -c "
SELECT 
  (SELECT COUNT(*) FROM anime) as total_anime,
  (SELECT COUNT(*) FROM episode) as total_episodes,
  (SELECT COUNT(*) FROM episode WHERE telegram_file_id IS NOT NULL) as uploaded_episodes;
"
```

### Очередь загрузки:
```bash
sudo -u postgres psql anibot -c "
SELECT COUNT(*) 
FROM episode 
WHERE telegram_file_id IS NULL 
  AND translation_id != 0;
"
```

---

## 📞 Поддержка

При возникновении проблем:
1. Проверьте логи компонентов
2. Убедитесь что все сервисы запущены (PostgreSQL, Redis)
3. Проверьте `.env` файл
4. Проверьте доступность Telegram API

