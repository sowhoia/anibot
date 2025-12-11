import asyncio
from loguru import logger

from app.common.logging import setup_logging
from app.config import settings
from app.integrations.telegram_uploader import (
    OrderedUploadQueue,
    EpisodeUploadTask,
    build_pyrogram_client,
)
from app.db.session import get_session
from app.db import repo
from app.services.downloader import Downloader, DownloadError


async def run_upload_worker() -> None:
    """
    Важно: очереди разделены по (anime_id, translation_id), и worker отправляет
    строго последовательно. Это исключает перепутанные message_id при одновременных загрузках.
    """
    setup_logging(level=settings.log_level, log_path=settings.log_file)
    client = build_pyrogram_client()
    queue = OrderedUploadQueue(client)
    session_factory = get_session()
    downloader = Downloader()

    await client.start()
    logger.info("Upload worker started")

    async def poll_tasks():
        while True:
            async with session_factory() as session:
                eps = await repo.get_episodes_without_media(session, limit=10)
            for ep in eps:
                external_ids = (ep.anime.external_ids if ep.anime else {}) or {}
                try:
                    file_path = await downloader.download_episode(
                        external_ids=external_ids,
                        translation_id=ep.translation_id,
                        episode_num=ep.number,
                    )
                except DownloadError as exc:
                    logger.error("Download failed for %s: %s", ep.id, exc)
                    continue

                task = EpisodeUploadTask(
                    episode_id=ep.id,
                    anime_id=ep.anime_id,
                    translation_id=ep.translation_id,
                    number=ep.number,
                    file_path=str(file_path),
                    caption=f"{ep.anime_id} — серия {ep.number}",
                    buttons_factory=lambda: [],
                )
                await queue.enqueue(task)
                # очистка файла после постановки в очередь выполнится в воркере
            await asyncio.sleep(settings.upload_poll_interval)

    await poll_tasks()


if __name__ == "__main__":
    asyncio.run(run_upload_worker())

