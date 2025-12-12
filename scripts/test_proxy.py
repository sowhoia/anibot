#!/usr/bin/env python3
"""Тест подключения через прокси к Telegram API."""
import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.config import settings


async def test_proxy():
    """Тестирует подключение через прокси."""
    proxy_url = getattr(settings, 'telegram_proxy_url', None)
    
    if not proxy_url:
        print("❌ TELEGRAM_PROXY_URL не настроен в .env")
        print("\nДобавьте в .env:")
        print('TELEGRAM_PROXY_URL="socks5://QfyZTrMy:BiapBEFW@130.49.32.224:64749"')
        return False
    
    print(f"🔍 Тестирую прокси: {proxy_url.split('@')[0]}@***")
    
    try:
        from aiohttp_socks import ProxyConnector
        import httpx
        
        # Тест через httpx (для проверки доступности)
        async with httpx.AsyncClient(
            proxies=proxy_url,
            timeout=10.0
        ) as client:
            response = await client.get("https://api.telegram.org")
            print(f"✅ Прокси работает! Telegram API доступен (статус: {response.status_code})")
            
        # Тест через ProxyConnector (как в коде)
        connector = ProxyConnector.from_url(proxy_url)
        print("✅ ProxyConnector создан успешно")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при подключении через прокси: {e}")
        print("\n" + "="*80)
        print("ВОЗМОЖНЫЕ ПРИЧИНЫ:")
        print("="*80)
        print("\n1. Неверный формат URL:")
        print("   ❌ socks5://host:port:user:pass")
        print("   ✅ socks5://user:pass@host:port")
        print("\n2. Неверные учетные данные")
        print("\n3. Прокси-сервер недоступен")
        print("\n4. Прокси блокирует Telegram")
        print("\n" + "="*80)
        return False


if __name__ == "__main__":
    result = asyncio.run(test_proxy())
    sys.exit(0 if result else 1)

