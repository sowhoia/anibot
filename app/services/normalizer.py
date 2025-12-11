from dataclasses import dataclass, field
from typing import Any, List, Optional

from anime_parsers_ru.api_kodik import Response


@dataclass
class NormalizedEpisode:
    id: str
    anime_id: str
    translation_id: int
    number: int
    season: int
    title: Optional[str]
    duration: Optional[int] = None
    preview_image: Optional[str] = None


@dataclass
class NormalizedAnimeBundle:
    anime: dict
    translation: dict
    anime_translation: dict
    episodes: List[NormalizedEpisode] = field(default_factory=list)


def normalize_kodik_item(item: Any) -> NormalizedAnimeBundle:
    """
    Поддерживает объекты Response.Element (KodikList/Search) и dict (parser.get_list).
    """
    if isinstance(item, Response.Element):
        return _normalize_element(item)
    if isinstance(item, dict):
        return _normalize_dict(item)
    raise TypeError(f"Unsupported item type: {type(item)}")


def _collect_alt_titles(mat: dict) -> list:
    alt = []
    for key in ("title_orig", "other_title", "other_titles", "other_titles_en", "other_titles_jp"):
        val = mat.get(key)
        if isinstance(val, list):
            alt.extend(val)
        elif val:
            alt.append(val)
    return list({t for t in alt if t})


def _get_rating(item: dict, key: str) -> float | None:
    try:
        val = item.get(key)
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _to_dict(obj: Any) -> dict:
    if not obj:
        return {}
    if isinstance(obj, dict):
        return obj
    return getattr(obj, "__dict__", {}) or {}


def _normalize_dict(raw: dict) -> NormalizedAnimeBundle:
    anime_id = raw.get("id") or raw.get("kodik_id") or raw.get("link")
    translation_info = raw.get("translation") or {}
    translation_id = int(translation_info.get("id")) if translation_info.get("id") else 0
    mat = raw.get("material_data") or {}
    additional = raw.get("additional_data") or {}

    anime = {
        "id": anime_id,
        "title": raw.get("title"),
        "title_orig": raw.get("title_orig"),
        "alt_titles": _collect_alt_titles(mat),
        "year": raw.get("year"),
        "poster_url": mat.get("poster_url") or mat.get("anime_poster_url"),
        "description": mat.get("description") or mat.get("anime_description"),
        "genres": mat.get("genres") or mat.get("anime_genres"),
        "rating_shiki": mat.get("shikimori_rating"),
        "rating_kinopoisk": mat.get("kinopoisk_rating"),
        "rating_imdb": mat.get("imdb_rating"),
        "episodes_total": additional.get("episodes_count") or raw.get("last_episode") or additional.get("last_episode"),
        "external_ids": {
            "shikimori": raw.get("shikimori_id"),
            "kinopoisk": raw.get("kinopoisk_id"),
            "imdb": raw.get("imdb_id"),
        },
        "blocked_countries": additional.get("blocked_countries"),
    }

    anime_translation = {
        "anime_id": anime_id,
        "translation_id": translation_id,
        "episodes_available": additional.get("episodes_count") or raw.get("last_episode"),
        "last_episode": raw.get("last_episode"),
    }

    translation = {
        "id": translation_id,
        "title": translation_info.get("title"),
        "type": translation_info.get("type"),
    }

    # Для get_list сезоны редко приходят; используем episodes_count/last_episode
    fallback_total = additional.get("episodes_count") or raw.get("last_episode")
    episodes: list[NormalizedEpisode] = []
    if fallback_total:
        for ep_num in range(1, int(fallback_total) + 1):
            episodes.append(
                NormalizedEpisode(
                    id=f"{anime_id}:{translation_id}:{ep_num}",
                    anime_id=anime_id,
                    translation_id=translation_id,
                    number=ep_num,
                    season=1,
                    title=None,
                )
            )

    return NormalizedAnimeBundle(
        anime=anime,
        translation=translation,
        anime_translation=anime_translation,
        episodes=episodes,
    )


def _normalize_element(item: Response.Element) -> NormalizedAnimeBundle:
    anime_id = item.id
    translation_info = _to_dict(item.translation)
    translation_id = int(translation_info.get("id")) if translation_info.get("id") else 0

    material = getattr(item, "_material_data", None)
    mat = material.__dict__ if material else {}
    additional = getattr(item, "raw_data", {}).get("additional_data", {})

    anime = {
        "id": anime_id,
        "title": item.title,
        "title_orig": item.title_orig,
        "alt_titles": _collect_alt_titles(mat),
        "year": item.year,
        "poster_url": mat.get("poster_url") or mat.get("anime_poster_url"),
        "description": mat.get("description") or mat.get("anime_description"),
        "genres": mat.get("genres") or mat.get("anime_genres"),
        "rating_shiki": mat.get("shikimori_rating"),
        "rating_kinopoisk": mat.get("kinopoisk_rating"),
        "rating_imdb": mat.get("imdb_rating"),
        "episodes_total": additional.get("episodes_count") or item.last_episode,
        "external_ids": {
            "shikimori": item.shikimori_id,
            "kinopoisk": item.kinopoisk_id,
            "imdb": item.imdb_id,
        },
        "blocked_countries": additional.get("blocked_countries"),
    }

    anime_translation = {
        "anime_id": anime_id,
        "translation_id": translation_id,
        "episodes_available": additional.get("episodes_count") or item.last_episode,
        "last_episode": item.last_episode,
    }

    translation = {
        "id": translation_id,
        "title": translation_info.get("title"),
        "type": translation_info.get("type"),
    }

    episodes = _normalize_episodes(item, anime_id=anime_id, translation_id=translation_id)

    return NormalizedAnimeBundle(
        anime=anime,
        translation=translation,
        anime_translation=anime_translation,
        episodes=episodes,
    )


def _normalize_episodes(item: Response.Element, anime_id: str, translation_id: int) -> list[NormalizedEpisode]:
    episodes: list[NormalizedEpisode] = []
    seasons = item.raw_data.get("seasons") or {}
    for season_str, episodes_dict in seasons.items():
        try:
            season_num = int(season_str)
        except (TypeError, ValueError):
            season_num = 1
        inner_eps = episodes_dict.get("episodes") if isinstance(episodes_dict, dict) else None
        mapping = inner_eps if isinstance(inner_eps, dict) else episodes_dict if isinstance(episodes_dict, dict) else {}
        for ep_num_str, ep_data in mapping.items():
            try:
                ep_num = int(ep_num_str)
            except (TypeError, ValueError):
                continue
            ep_title = None
            duration = None
            preview = None
            if isinstance(ep_data, dict):
                ep_title = ep_data.get("title") or ep_data.get("name")
                duration = ep_data.get("duration")
                preview = ep_data.get("preview")
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

    # Фоллбек, если нет структуры seasons: генерируем по last_episode
    fallback_total = getattr(item, "episodes_count", None) or getattr(item, "last_episode", None)
    if not episodes and fallback_total:
        for ep_num in range(1, int(fallback_total) + 1):
            episodes.append(
                NormalizedEpisode(
                    id=f"{anime_id}:{translation_id}:{ep_num}",
                    anime_id=anime_id,
                    translation_id=translation_id,
                    number=ep_num,
                    season=1,
                    title=None,
                )
            )
    return episodes

