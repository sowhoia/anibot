"""
Нормализация данных из Kodik API.

Преобразует различные форматы данных из Kodik в унифицированную структуру
для сохранения в базу данных.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeAlias

from anime_parsers_ru.api_kodik import Response

# Type aliases
RawData: TypeAlias = dict[str, Any] | Response.Element


@dataclass(slots=True)
class NormalizedEpisode:
    """Нормализованные данные эпизода."""

    id: str
    anime_id: str
    translation_id: int
    number: int
    season: int = 1
    title: str | None = None
    duration: int | None = None
    preview_image: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Преобразует в словарь для сохранения в БД."""
        return {
            "id": self.id,
            "anime_id": self.anime_id,
            "translation_id": self.translation_id,
            "number": self.number,
            "season": self.season,
            "title": self.title,
            "duration": self.duration,
            "preview_image": self.preview_image,
        }


@dataclass(slots=True)
class NormalizedAnimeBundle:
    """Пакет нормализованных данных для одного аниме."""

    anime: dict[str, Any]
    translation: dict[str, Any]
    anime_translation: dict[str, Any]
    episodes: list[NormalizedEpisode] = field(default_factory=list)


class KodikNormalizer:
    """
    Нормализатор данных из Kodik API.

    Поддерживает:
    - Response.Element (из KodikList/Search)
    - dict (из KodikParserAsync.get_list())
    """

    # Ключи для сбора альтернативных названий
    ALT_TITLE_KEYS: tuple[str, ...] = (
        "title_orig",
        "other_title",
        "other_titles",
        "other_titles_en",
        "other_titles_jp",
    )

    def normalize(self, item: RawData) -> NormalizedAnimeBundle:
        """
        Нормализует элемент из Kodik API.

        Args:
            item: Response.Element или dict из API

        Returns:
            NormalizedAnimeBundle с данными для БД

        Raises:
            TypeError: Если тип item не поддерживается
        """
        if isinstance(item, Response.Element):
            return self._normalize_element(item)
        if isinstance(item, dict):
            return self._normalize_dict(item)
        raise TypeError(f"Unsupported item type: {type(item)}")

    def _normalize_element(self, item: Response.Element) -> NormalizedAnimeBundle:
        """Нормализует Response.Element."""
        raw_data = getattr(item, "raw_data", {}) or {}
        material = getattr(item, "_material_data", None)
        material_data = material.__dict__ if material else {}
        additional = raw_data.get("additional_data", {})

        anime_id = item.id
        translation_info = self._to_dict(item.translation)
        translation_id = self._safe_int(translation_info.get("id"), 0)

        return NormalizedAnimeBundle(
            anime=self._build_anime_dict(
                anime_id=anime_id,
                title=item.title,
                title_orig=item.title_orig,
                year=item.year,
                material_data=material_data,
                additional=additional,
                external_ids={
                    "shikimori": item.shikimori_id,
                    "kinopoisk": item.kinopoisk_id,
                    "imdb": item.imdb_id,
                },
                last_episode=item.last_episode,
            ),
            translation=self._build_translation_dict(translation_id, translation_info),
            anime_translation=self._build_anime_translation_dict(
                anime_id=anime_id,
                translation_id=translation_id,
                episodes_count=additional.get("episodes_count") or item.last_episode,
                last_episode=item.last_episode,
            ),
            episodes=self._extract_episodes(
                raw_data=raw_data,
                anime_id=anime_id,
                translation_id=translation_id,
                fallback_total=getattr(item, "episodes_count", None) or item.last_episode,
            ),
        )

    def _normalize_dict(self, raw: dict[str, Any]) -> NormalizedAnimeBundle:
        """Нормализует словарь из API."""
        anime_id = raw.get("id") or raw.get("kodik_id") or raw.get("link")
        translation_info = raw.get("translation") or {}
        translation_id = self._safe_int(translation_info.get("id"), 0)
        material_data = raw.get("material_data") or {}
        additional = raw.get("additional_data") or {}

        fallback_total = additional.get("episodes_count") or raw.get("last_episode")

        return NormalizedAnimeBundle(
            anime=self._build_anime_dict(
                anime_id=anime_id,
                title=raw.get("title"),
                title_orig=raw.get("title_orig"),
                year=raw.get("year"),
                material_data=material_data,
                additional=additional,
                external_ids={
                    "shikimori": raw.get("shikimori_id"),
                    "kinopoisk": raw.get("kinopoisk_id"),
                    "imdb": raw.get("imdb_id"),
                },
                last_episode=raw.get("last_episode"),
            ),
            translation=self._build_translation_dict(translation_id, translation_info),
            anime_translation=self._build_anime_translation_dict(
                anime_id=anime_id,
                translation_id=translation_id,
                episodes_count=fallback_total,
                last_episode=raw.get("last_episode"),
            ),
            episodes=self._generate_episodes_from_count(
                anime_id=anime_id,
                translation_id=translation_id,
                total=fallback_total,
            ),
        )

    # Маппинг статусов из Kodik в наши
    STATUS_MAP: dict[str, str] = {
        "ongoing": "ongoing",
        "released": "released",
        "announced": "announced",
        "finished": "released",
        "airing": "ongoing",
    }

    def _build_anime_dict(
        self,
        anime_id: str,
        title: str | None,
        title_orig: str | None,
        year: int | None,
        material_data: dict[str, Any],
        additional: dict[str, Any],
        external_ids: dict[str, Any],
        last_episode: int | None,
    ) -> dict[str, Any]:
        """Собирает словарь данных аниме."""
        # Определяем статус
        raw_status = (
            material_data.get("anime_status")
            or material_data.get("status")
            or additional.get("status")
        )
        status = self.STATUS_MAP.get(str(raw_status).lower()) if raw_status else None

        return {
            "id": anime_id,
            "title": title,
            "title_orig": title_orig,
            "alt_titles": self._collect_alt_titles(material_data),
            "year": year,
            "poster_url": material_data.get("poster_url") or material_data.get("anime_poster_url"),
            "description": material_data.get("description") or material_data.get("anime_description"),
            "genres": material_data.get("genres") or material_data.get("anime_genres"),
            "rating_shiki": self._safe_float(material_data.get("shikimori_rating")),
            "rating_kinopoisk": self._safe_float(material_data.get("kinopoisk_rating")),
            "rating_imdb": self._safe_float(material_data.get("imdb_rating")),
            "episodes_total": additional.get("episodes_count") or last_episode,
            "external_ids": {k: v for k, v in external_ids.items() if v},
            "blocked_countries": additional.get("blocked_countries"),
            "status": status,
        }

    def _build_translation_dict(
        self,
        translation_id: int,
        translation_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Собирает словарь данных озвучки."""
        return {
            "id": translation_id,
            "title": translation_info.get("title"),
            "type": translation_info.get("type"),
        }

    def _build_anime_translation_dict(
        self,
        anime_id: str,
        translation_id: int,
        episodes_count: int | None,
        last_episode: int | None,
    ) -> dict[str, Any]:
        """Собирает словарь связи аниме-озвучка."""
        return {
            "anime_id": anime_id,
            "translation_id": translation_id,
            "episodes_available": episodes_count,
            "last_episode": last_episode,
        }

    def _extract_episodes(
        self,
        raw_data: dict[str, Any],
        anime_id: str,
        translation_id: int,
        fallback_total: int | None,
    ) -> list[NormalizedEpisode]:
        """Извлекает эпизоды из структуры seasons."""
        episodes: list[NormalizedEpisode] = []
        seasons = raw_data.get("seasons") or {}

        for season_str, season_data in seasons.items():
            season_num = self._safe_int(season_str, 1)
            episodes_dict = self._extract_episodes_dict(season_data)

            for ep_num_str, ep_data in episodes_dict.items():
                ep_num = self._safe_int(ep_num_str)
                if ep_num is None:
                    continue

                ep_title, duration, preview = self._parse_episode_data(ep_data)

                episodes.append(
                    NormalizedEpisode(
                        id=f"{anime_id}:{translation_id}:{ep_num}",
                        anime_id=anime_id,
                        translation_id=translation_id,
                        number=ep_num,
                        season=season_num,
                        title=ep_title,
                        duration=duration,
                        preview_image=preview,
                    )
                )

        # Фоллбек: генерируем из общего количества
        if not episodes and fallback_total:
            episodes = self._generate_episodes_from_count(
                anime_id=anime_id,
                translation_id=translation_id,
                total=fallback_total,
            )

        return episodes

    def _extract_episodes_dict(self, season_data: Any) -> dict[str, Any]:
        """Извлекает словарь эпизодов из данных сезона."""
        if not isinstance(season_data, dict):
            return {}

        # Может быть вложенная структура {"episodes": {...}}
        inner = season_data.get("episodes")
        if isinstance(inner, dict):
            return inner

        return season_data

    def _parse_episode_data(
        self,
        ep_data: Any,
    ) -> tuple[str | None, int | None, str | None]:
        """Парсит данные эпизода."""
        if not isinstance(ep_data, dict):
            return None, None, None

        return (
            ep_data.get("title") or ep_data.get("name"),
            self._safe_int(ep_data.get("duration")),
            ep_data.get("preview"),
        )

    def _generate_episodes_from_count(
        self,
        anime_id: str,
        translation_id: int,
        total: int | None,
    ) -> list[NormalizedEpisode]:
        """Генерирует список эпизодов по количеству."""
        if not total:
            return []

        return [
            NormalizedEpisode(
                id=f"{anime_id}:{translation_id}:{ep_num}",
                anime_id=anime_id,
                translation_id=translation_id,
                number=ep_num,
                season=1,
            )
            for ep_num in range(1, int(total) + 1)
        ]

    def _collect_alt_titles(self, material_data: dict[str, Any]) -> list[str]:
        """Собирает альтернативные названия."""
        titles: set[str] = set()

        for key in self.ALT_TITLE_KEYS:
            value = material_data.get(key)
            if isinstance(value, list):
                titles.update(t for t in value if t)
            elif value:
                titles.add(value)

        return list(titles)

    @staticmethod
    def _to_dict(obj: Any) -> dict[str, Any]:
        """Преобразует объект в словарь."""
        if not obj:
            return {}
        if isinstance(obj, dict):
            return obj
        return getattr(obj, "__dict__", {}) or {}

    @staticmethod
    def _safe_int(value: Any, default: int | None = None) -> int | None:
        """Безопасное преобразование в int."""
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        """Безопасное преобразование в float."""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


# Singleton нормализатор
_normalizer: KodikNormalizer | None = None


def get_normalizer() -> KodikNormalizer:
    """Возвращает singleton экземпляр нормализатора."""
    global _normalizer
    if _normalizer is None:
        _normalizer = KodikNormalizer()
    return _normalizer


def normalize_kodik_item(item: RawData) -> NormalizedAnimeBundle:
    """
    Удобная функция для нормализации элемента.

    Поддерживает Response.Element и dict.
    """
    return get_normalizer().normalize(item)
