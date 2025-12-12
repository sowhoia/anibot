#!/usr/bin/env python3
"""Проверка доступности Telegram API."""
import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def check_telegram_api():
    """Проверяет доступность api.telegram.org."""
    import aiohttp
    from aiohttp_socks import ProxyConnector
    
    # Пробуем загрузить настройки
    proxy_url = None
    try:
        from app.config import settings
        proxy_url = getattr(settings, 'telegram_proxy_url', None)
    except Exception:
        pass
    
    # 1. Проверка напрямую
    print("Проверка доступности Telegram API напрямую...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.telegram.org", timeout=aiohttp.ClientTimeout(total=10)) as response:
                print(f"✅ Telegram API доступен напрямую (статус: {response.status})")
                return True
    except Exception as e:
        print(f"❌ Telegram API недоступен напрямую: {type(e).__name__}")
    
    # 2. Проверка через прокси
    if proxy_url:
        print(f"\nПроверка через прокси: {proxy_url.split('@')[0] if '@' in proxy_url else proxy_url}@***")
        try:
            connector = ProxyConnector.from_url(proxy_url)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get("https://api.telegram.org", timeout=aiohttp.ClientTimeout(total=15)) as response:
                    print(f"✅ Telegram API доступен через прокси (статус: {response.status})")
                    return True
        except Exception as e:
            print(f"❌ Telegram API недоступен через прокси: {type(e).__name__}: {e}")
    
    # Если ничего не сработало
    print("\n" + "="*80)
    print("РЕШЕНИЕ:")
    print("="*80)
    print("\n1. Используйте VPN")
    print("\n2. Настройте прокси в .env:")
    print("   TELEGRAM_PROXY_URL=\"socks5://user:pass@host:port\"")
    print("   # или")
    print("   TELEGRAM_PROXY_URL=\"http://user:pass@host:port\"")
    print("\n3. Установите прокси локально:")
    print("   - Shadowsocks: apt install shadowsocks-libev")
    print("   - V2Ray: https://www.v2ray.com/")
    print("   - SSH tunnel: ssh -D 1080 -N your_server")
    print("\n" + "="*80)
    return False


if __name__ == "__main__":
    result = asyncio.run(check_telegram_api())
    sys.exit(0 if result else 1)

