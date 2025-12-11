from dataclasses import dataclass
from typing import List, Tuple

from sqlalchemy import func, select, literal
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.db import models


@dataclass
class SearchItem:
    id: str
    title: str
    year: int | None = None


class SearchService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None):
        from app.db.session import get_session

        self.session_factory = session_factory or get_session()

    async def search(self, query: str, page: int, limit: int) -> Tuple[List[SearchItem], int]:
        if not query:
            return [], 0
        async with self.session_factory() as session:
            q = self._build_query(query)
            total = (await session.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
            offset = (page - 1) * limit
            res = await session.execute(q.offset(offset).limit(limit))
            items = [
                SearchItem(
                    id=row.id,
                    title=row.title,
                    year=row.year,
                )
                for row in res.all()
            ]
        return items, total

    def _build_query(self, query: str):
        # Используем ILIKE + trigram similarity если доступна функция
        similarity = func.coalesce(func.similarity(models.Anime.title, query), literal(0))
        q = (
            select(models.Anime.id, models.Anime.title, models.Anime.year, similarity.label("sim"))
            .where(models.Anime.title.ilike(f"%{query}%") | models.Anime.title_orig.ilike(f"%{query}%"))
            .order_by(similarity.desc(), models.Anime.year.desc().nullslast())
        )
        return q

