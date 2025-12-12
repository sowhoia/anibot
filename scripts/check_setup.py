#!/usr/bin/env python3
"""Проверка настройки AniBot перед запуском."""
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.config import settings


def check_setup():
    """Проверяет настройку всех компонентов."""
    errors = []
    warnings = []
    
    print("🔍 Проверка настройки AniBot...\n")
    
    # 1. Проверка токена бота
    print("1. Telegram Bot Token...")
    if not settings.bot_token or settings.bot_token == "your_bot_token_here":
        errors.append("❌ BOT_TOKEN не настроен в .env")
    else:
        print("   ✅ BOT_TOKEN настроен")
    
    # 2. Проверка User API
    print("\n2. Telegram User API...")
    if not settings.user_api_api_id or settings.user_api_api_id == 123456:
        errors.append("❌ USER_API_API_ID не настроен в .env")
    else:
        print("   ✅ USER_API_API_ID настроен")
    
    if not settings.user_api_api_hash or settings.user_api_api_hash == "your_api_hash":
        errors.append("❌ USER_API_API_HASH не настроен в .env")
    else:
        print("   ✅ USER_API_API_HASH настроен")
    
    if not settings.user_api_session_string or settings.user_api_session_string == "your_pyrogram_session_string":
        warnings.append("⚠️  USER_API_SESSION_STRING не настроен - будет создан при первом запуске")
    else:
        print("   ✅ USER_API_SESSION_STRING настроен")
    
    # 3. Проверка UPLOAD_CHAT_ID
    print("\n3. Upload Chat ID...")
    if not settings.upload_chat_id:
        errors.append("❌ UPLOAD_CHAT_ID не настроен в .env")
    elif settings.upload_chat_id == "me":
        print("   ✅ UPLOAD_CHAT_ID='me' (Saved Messages)")
    else:
        print(f"   ✅ UPLOAD_CHAT_ID={settings.upload_chat_id}")
    
    # 4. Проверка прокси
    print("\n4. Telegram Proxy...")
    if settings.telegram_proxy_url:
        print(f"   ✅ TELEGRAM_PROXY_URL настроен: {settings.telegram_proxy_url.split('@')[0]}@***")
    else:
        warnings.append("⚠️  TELEGRAM_PROXY_URL не настроен (может быть проблема, если Telegram заблокирован)")
    
    # 5. Проверка зависимостей
    print("\n5. Зависимости...")
    try:
        import aiohttp_socks
        print("   ✅ aiohttp-socks установлен")
    except ImportError:
        errors.append("❌ aiohttp-socks не установлен. Запустите: poetry install")
    
    try:
        from pyrogram import Client
        print("   ✅ pyrogram установлен")
    except ImportError:
        errors.append("❌ pyrogram не установлен. Запустите: poetry install")
    
    # Итоги
    print("\n" + "="*80)
    if errors:
        print("❌ ОШИБКИ:")
        for error in errors:
            print(f"   {error}")
        print("\nИсправьте ошибки перед запуском!")
        return False
    
    if warnings:
        print("⚠️  ПРЕДУПРЕЖДЕНИЯ:")
        for warning in warnings:
            print(f"   {warning}")
    
    print("✅ Все проверки пройдены! Можно запускать бота.")
    print("="*80)
    return True


if __name__ == "__main__":
    success = check_setup()
    sys.exit(0 if success else 1)

