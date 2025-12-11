from typing import Iterable

from loguru import logger
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.db import repo
from app.services.normalizer import NormalizedAnimeBundle, normalize_kodik_item


class IngestService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def ingest_items(self, raw_items: Iterable[dict]) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                for raw in raw_items:
                    try:
                        bundle = normalize_kodik_item(raw)
                        await self._persist_bundle(session, bundle)
                    except Exception as exc:  # noqa: BLE001
                        raw_id = raw.get("id") if isinstance(raw, dict) else None
                        logger.warning("Skip item %s due to error: %s", raw_id, exc)

    async def _persist_bundle(self, session: AsyncSession, bundle: NormalizedAnimeBundle) -> None:
        await repo.upsert_translation(session, bundle.translation)
        await repo.upsert_anime(session, bundle.anime)
        await repo.upsert_anime_translation(session, bundle.anime_translation)
        await repo.upsert_episodes(session, [e.__dict__ for e in bundle.episodes])
        logger.debug(
            "Upserted anime=%s translation=%s episodes=%s",
            bundle.anime["id"],
            bundle.translation["id"],
            len(bundle.episodes),
        )

