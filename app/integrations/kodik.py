import asyncio
from typing import Any, Iterable, List, Optional
from anime_parsers_ru import KodikParserAsync, KodikList

from app.config import settings


class KodikClient:
    """
    Обертка вокруг anime-parsers-ru для работы с Kodik.
    Реализует полную и дельта-выгрузку.
    """

    def __init__(self) -> None:
        self.parser = KodikParserAsync(token=settings.kodik_token or None)
        self.list_api = KodikList()
        self._min_interval = 1 / settings.kodik_rps_limit if settings.kodik_rps_limit else 0
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def _throttle(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            now = asyncio.get_running_loop().time()
            elapsed = now - self._last_call
            wait_for = self._min_interval - elapsed
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last_call = asyncio.get_running_loop().time()

    async def fetch_full_list(self, limit_per_page: int = 50, pages_to_parse: Optional[int] = None) -> List[Any]:
        """
        Получает список аниме через Kodik API с материалами и (если есть) эпизодами.
        """
        start_from = None
        results: list[Any] = []
        pages = 0
        while True:
            await self._throttle()
            batch, next_from = await self.parser.get_list(
                limit_per_page=limit_per_page,
                pages_to_parse=1,
                include_material_data=True,
                only_anime=True,
                start_from=start_from,
            )
            results.extend(batch)
            pages += 1
            if not next_from:
                break
            if pages_to_parse is not None and pages >= pages_to_parse:
                break
            start_from = next_from
        return results

    async def fetch_delta(self, updated_at_from: str, limit_per_page: int = 50, pages_to_parse: Optional[int] = None) -> List[Any]:
        """
        Псевдо-дельта: фильтруем по updated_at на клиенте (API Search не поддерживает updated_at).
        """
        items = await self.fetch_full_list(limit_per_page=limit_per_page, pages_to_parse=pages_to_parse)
        filtered = []
        for el in items:
            ts = el.get("updated_at") if isinstance(el, dict) else getattr(el, "updated_at", None)
            if ts and ts >= updated_at_from:
                filtered.append(el)
        return filtered

    async def get_episode_m3u8(
        self,
        external_ids: dict[str, Any],
        translation_id: int,
        episode_num: int,
        quality: int = 720,
    ) -> str:
        """
        Возвращает m3u8 для конкретной серии/озвучки по внешнему ID (shikimori/kinopoisk/imdb).
        """
        id_val, id_type = self._choose_external_id(external_ids)
        await self._throttle()
        return await self.parser.get_m3u8_playlist_link(
            id=str(id_val),
            id_type=id_type,
            translation_id=str(translation_id),
            seria_num=episode_num,
            quality=quality,
        )

    @staticmethod
    def _choose_external_id(external_ids: dict[str, Any]) -> tuple[str, str]:
        for key in ("shikimori", "kinopoisk", "imdb"):
            val = external_ids.get(key)
            if val:
                return str(val), key
        raise ValueError("Нет доступных внешних ID (shikimori/kinopoisk/imdb)")

