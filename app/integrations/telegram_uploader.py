import asyncio
from dataclasses import dataclass
from typing import Callable, Dict, Tuple

from loguru import logger
from pyrogram import Client

from app.config import settings
from app.db import repo
from app.db.session import get_session


@dataclass
class EpisodeUploadTask:
    episode_id: str
    anime_id: str
    translation_id: int
    number: int
    file_path: str
    caption: str
    buttons_factory: Callable[[], list]


class OrderedUploadQueue:
    """
    Гарантирует отправку серий строго по порядку внутри ключа (anime_id, translation_id).
    Это исключает ситуацию, когда message_id серий путаются из-за гонок при параллельных отправках.
    """

    def __init__(self, client: Client) -> None:
        self.client = client
        self.queues: Dict[Tuple[str, int], asyncio.Queue[EpisodeUploadTask]] = {}
        self.workers: Dict[Tuple[str, int], asyncio.Task] = {}
        self.session_factory = get_session()

    async def enqueue(self, task: EpisodeUploadTask) -> None:
        key = (task.anime_id, task.translation_id)
        if key not in self.queues:
            self.queues[key] = asyncio.Queue()
            self.workers[key] = asyncio.create_task(self._worker(key))
        await self.queues[key].put(task)

    async def _worker(self, key: Tuple[str, int]) -> None:
        queue = self.queues[key]
        while True:
            task = await queue.get()
            try:
                await self._process(task)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Upload failed for %s: %s", task.episode_id, exc)
            finally:
                queue.task_done()

    async def _process(self, task: EpisodeUploadTask) -> None:
        logger.info(
            "Uploading episode %s (anime=%s, tr=%s, num=%s)",
            task.episode_id,
            task.anime_id,
            task.translation_id,
            task.number,
        )
        # Реальная отправка файла в канал user API
        # Здесь предполагается, что file_path — локальный путь после скачивания из Kodik.
        buttons = task.buttons_factory() if task.buttons_factory else None
        try:
            msg = await self.client.send_document(
                chat_id="me",  # заменить на id закрытого канала
                document=task.file_path,
                caption=task.caption,
                reply_markup=buttons,
            )
            async with self.session_factory() as session:
                async with session.begin():
                    await repo.mark_media(
                        session=session,
                        episode_id=task.episode_id,
                        chat_id=str(msg.chat.id),
                        message_id=msg.id,
                        file_unique_id=getattr(msg.document, "file_unique_id", None),
                        quality=None,
                        source_url=None,
                        checksum=None,
                        size_bytes=getattr(msg.document, "file_size", None),
                    )
        finally:
            # Удаляем временный файл независимо от успеха отправки
            try:
                import os

                os.remove(task.file_path)
            except FileNotFoundError:
                pass
            except OSError as exc:  # noqa: PERF203
                logger.warning("Cannot delete temp file %s: %s", task.file_path, exc)


def build_pyrogram_client() -> Client:
    return Client(
        "anibot-user",
        api_id=settings.user_api_api_id,
        api_hash=settings.user_api_api_hash,
        session_string=settings.user_api_session_string,
        workdir=".",
    )

