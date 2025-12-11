import asyncio

from loguru import logger

from app.common.async_utils import chunked, run_with_limited_concurrency
from app.common.logging import setup_logging
from app.config import settings
from app.integrations.kodik import KodikClient
from app.services.ingest import IngestService
from app.db.session import get_session


async def ingest_full(concurrency: int = 3) -> None:
    setup_logging(level=settings.log_level, log_path=settings.log_file)
    client = KodikClient()
    ingest = IngestService(get_session())

    raw_items = await client.fetch_full_list()
    batches = chunked(raw_items, size=100)
    await run_with_limited_concurrency(
        batches=batches,
        concurrency=concurrency,
        worker=ingest.ingest_items,
    )
    logger.info("Full ingest completed. Total items: %s", len(raw_items))


if __name__ == "__main__":
    asyncio.run(ingest_full())

