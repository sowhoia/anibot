#!/usr/bin/env bash
# Запуск всех компонентов AniBot

set -euo pipefail

cd "$(dirname "$0")/.."

echo "==================================================================="
echo "  Запуск AniBot - все компоненты"
echo "==================================================================="

# Проверка доступности Telegram API
echo -e "\n[1/4] Проверка Telegram API..."
poetry run python scripts/check_telegram.py
if [ $? -eq 0 ]; then
    echo "✅ Telegram API доступен"
else
    echo "⚠️  Telegram API недоступен - настройте прокси в .env"
    echo "Продолжаем без основного бота..."
fi

# Запуск компонентов в фоне
echo -e "\n[2/4] Запуск основного бота..."
PYTHONPATH=. poetry run python -m app.main &
BOT_PID=$!
echo "✅ Бот запущен (PID: $BOT_PID)"

echo -e "\n[3/4] Запуск upload worker..."
PYTHONPATH=. poetry run python -m app.workers.upload_worker &
UPLOAD_PID=$!
echo "✅ Upload worker запущен (PID: $UPLOAD_PID)"

echo -e "\n[4/4] Запуск delta sync worker..."
PYTHONPATH=. poetry run python -m app.workers.delta_sync &
SYNC_PID=$!
echo "✅ Delta sync worker запущен (PID: $SYNC_PID)"

echo -e "\n==================================================================="
echo "  ВСЕ КОМПОНЕНТЫ ЗАПУЩЕНЫ!"
echo "==================================================================="
echo ""
echo "PIDs:"
echo "  Бот: $BOT_PID"
echo "  Upload worker: $UPLOAD_PID"
echo "  Delta sync: $SYNC_PID"
echo ""
echo "Логи в реальном времени:"
echo "  journalctl -f --user-unit=anibot-*"
echo ""
echo "Остановка всех:"
echo "  kill $BOT_PID $UPLOAD_PID $SYNC_PID"
echo ""
echo "Или используйте Ctrl+C"
echo "==================================================================="

# Ожидаем Ctrl+C
trap "echo 'Stopping...'; kill $BOT_PID $UPLOAD_PID $SYNC_PID 2>/dev/null; exit" SIGINT SIGTERM

# Ждем завершения всех процессов
wait

