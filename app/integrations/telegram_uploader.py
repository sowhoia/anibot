"""
Сервис загрузки видео в Telegram.

Особенности:
- Упорядоченная загрузка серий (сохраняет порядок message_id)
- Автоматическое удаление временных файлов
- Отслеживание прогресса загрузки
- Graceful shutdown
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from loguru import logger
from pyrogram import Client
from pyrogram.types import Message

from app.config import settings
from app.db.repo import AnimeRepository
from app.db.session import get_session


class UploadStatus(str, Enum):
    """Статус задачи загрузки."""

    PENDING = "pending"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class EpisodeUploadTask:
    """Задача на загрузку эпизода."""

    episode_id: str
    anime_id: str
    translation_id: int
    number: int
    file_path: str
    caption: str
    buttons_factory: Callable[[], list] | None = None
    quality: int | None = None
    checksum: str | None = None
    size_bytes: int | None = None

    # Мета-информация о выполнении
    status: UploadStatus = field(default=UploadStatus.PENDING)
    error: str | None = field(default=None)
    telegram_message_id: int | None = field(default=None)

    @property
    def queue_key(self) -> tuple[str, int]:
        """Ключ очереди (anime_id, translation_id)."""
        return (self.anime_id, self.translation_id)


@dataclass
class UploadResult:
    """Результат загрузки."""

    task: EpisodeUploadTask
    message: Message | None = None
    error: Exception | None = None

    @property
    def success(self) -> bool:
        """Была ли загрузка успешной."""
        return self.message is not None and self.error is None


class OrderedUploadQueue:
    """
    Очередь загрузки с гарантией порядка.

    Гарантирует, что серии одного аниме с одной озвучкой
    загружаются строго последовательно, сохраняя порядок message_id.

    Примеры:
        >>> queue = OrderedUploadQueue(client)
        >>> await queue.enqueue(task)
        >>> await queue.shutdown()
    """

    def __init__(
        self,
        client: Client,
        chat_id: str | int | None = None,
        delete_after_upload: bool = True,
    ) -> None:
        """
        Args:
            client: Pyrogram клиент
            chat_id: ID чата для загрузки (по умолчанию из settings)
            delete_after_upload: Удалять файл после загрузки
        """
        self._client = client
        self._chat_id = chat_id or settings.upload_chat_id
        self._chat_validated = False
        
        # Валидация chat_id
        if not self._chat_id:
            raise ValueError("UPLOAD_CHAT_ID не настроен в .env")
        
        # Для "me" используем строку (Pyrogram понимает это как Saved Messages)
        if self._chat_id == "me":
            logger.info("Using 'me' as chat_id (Saved Messages)")
        else:
            logger.info("Using chat_id: {}", self._chat_id)
        
        self._delete_after_upload = delete_after_upload
        self._session_factory = get_session()

        # Очереди для каждой пары (anime_id, translation_id)
        self._queues: dict[tuple[str, int], asyncio.Queue[EpisodeUploadTask]] = {}
        self._workers: dict[tuple[str, int], asyncio.Task] = {}
        self._shutdown_event = asyncio.Event()
        self._active_uploads: dict[str, EpisodeUploadTask] = {}

    async def enqueue(self, task: EpisodeUploadTask) -> None:
        """
        Добавляет задачу в очередь.

        Args:
            task: Задача на загрузку
        """
        key = task.queue_key

        if key not in self._queues:
            self._queues[key] = asyncio.Queue()
            self._workers[key] = asyncio.create_task(
                self._worker(key),
                name=f"upload-worker-{key[0][:8]}-{key[1]}",
            )

        await self._queues[key].put(task)
        logger.debug(
            "Enqueued upload: {} (queue size: {})",
            task.episode_id,
            self._queues[key].qsize(),
        )

    async def _worker(self, key: tuple[str, int]) -> None:
        """
        Worker для обработки очереди.

        Args:
            key: Ключ очереди (anime_id, translation_id)
        """
        queue = self._queues[key]
        logger.info("Upload worker started for {}", key)

        while not self._shutdown_event.is_set():
            try:
                # Ожидаем задачу с таймаутом для проверки shutdown
                try:
                    task = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                self._active_uploads[task.episode_id] = task

                try:
                    result = await self._process_task(task)
                    if result.success:
                        logger.info(
                            "Video upload completed: {} -> msg_id={} (streamable)",
                            task.episode_id,
                            result.message.id,
                        )
                    else:
                        logger.error(
                            "Upload failed: {} - {}",
                            task.episode_id,
                            result.error,
                        )
                except Exception as exc:
                    logger.exception("Upload worker error: {}", exc)
                finally:
                    self._active_uploads.pop(task.episode_id, None)
                    queue.task_done()

            except asyncio.CancelledError:
                break

        logger.info("Upload worker stopped for {}", key)

    async def _validate_chat_access(self) -> None:
        """Проверяет и получает доступ к чату перед загрузкой."""
        if self._chat_validated or self._chat_id == "me":
            return
        
        try:
            # Получаем информацию о чате, чтобы Pyrogram "познакомился" с ним
            chat = await self._client.get_chat(self._chat_id)
            logger.info(
                "Chat validated: {} (type: {})",
                chat.title if hasattr(chat, 'title') else chat.id,
                chat.type
            )
            self._chat_validated = True
        except Exception as e:
            logger.warning(
                "Could not validate chat {}: {}. Will use 'me' as fallback.",
                self._chat_id,
                e
            )
            # Используем "me" как fallback
            self._chat_id = "me"
            self._chat_validated = True

    async def _process_task(self, task: EpisodeUploadTask) -> UploadResult:
        """
        Обрабатывает задачу загрузки.

        Args:
            task: Задача на загрузку

        Returns:
            Результат загрузки
        """
        task.status = UploadStatus.UPLOADING

        try:
            # Валидируем доступ к чату при первой загрузке
            await self._validate_chat_access()
            
            # Проверяем существование файла
            if not Path(task.file_path).exists():
                raise FileNotFoundError(f"File not found: {task.file_path}")

            # Подготавливаем кнопки
            buttons = task.buttons_factory() if task.buttons_factory else None

            # Загружаем файл как видео
            logger.info(
                "Uploading video {} (anime={}, tr={}, ep={}) to chat_id={}",
                task.episode_id,
                task.anime_id,
                task.translation_id,
                task.number,
                self._chat_id,
            )

            # Загружаем файл как видео (для просмотра в Telegram)
            msg = await self._client.send_video(
                chat_id=self._chat_id,
                video=task.file_path,
                caption=task.caption,
                reply_markup=buttons,
                supports_streaming=True,  # Включаем стриминг для просмотра без скачивания
            )

            # Сохраняем в БД
            async with self._session_factory() as session:
                async with session.begin():
                    repository = AnimeRepository(session)
                    await repository.mark_media(
                        episode_id=task.episode_id,
                        chat_id=str(msg.chat.id),
                        message_id=msg.id,
                        file_unique_id=getattr(msg.video, "file_unique_id", None),
                        quality=task.quality,
                        source_url=None,
                        checksum=task.checksum,
                        size_bytes=task.size_bytes or getattr(msg.video, "file_size", None),
                    )

            task.status = UploadStatus.COMPLETED
            task.telegram_message_id = msg.id

            return UploadResult(task=task, message=msg)

        except Exception as exc:
            task.status = UploadStatus.FAILED
            task.error = str(exc)
            return UploadResult(task=task, error=exc)

        finally:
            # Удаляем временный файл
            if self._delete_after_upload:
                await self._cleanup_file(task.file_path)

    async def _cleanup_file(self, file_path: str) -> None:
        """Безопасно удаляет файл."""
        try:
            if Path(file_path).exists():
                os.remove(file_path)
                logger.debug("Deleted temp file: {}", file_path)
        except OSError as exc:
            logger.warning("Failed to delete temp file {}: {}", file_path, exc)

    async def shutdown(self, timeout: float = 30.0) -> None:
        """
        Graceful shutdown очереди.

        Args:
            timeout: Максимальное время ожидания завершения
        """
        logger.info("Shutting down upload queue...")
        self._shutdown_event.set()

        # Ждем завершения всех workers
        if self._workers:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._workers.values(), return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("Upload workers did not stop in time, cancelling...")
                for worker in self._workers.values():
                    worker.cancel()

        self._workers.clear()
        self._queues.clear()
        logger.info("Upload queue shutdown complete")

    @property
    def active_uploads_count(self) -> int:
        """Количество активных загрузок."""
        return len(self._active_uploads)

    @property
    def pending_count(self) -> int:
        """Общее количество задач в очередях."""
        return sum(q.qsize() for q in self._queues.values())

    def get_status(self) -> dict[str, Any]:
        """Возвращает статус очереди."""
        return {
            "active_uploads": self.active_uploads_count,
            "pending": self.pending_count,
            "queues": len(self._queues),
            "workers": len(self._workers),
            "shutdown_requested": self._shutdown_event.is_set(),
        }


def build_pyrogram_client(
    session_name: str = "anibot-user",
    workdir: str = ".",
) -> Client:
    """
    Создает Pyrogram клиент для User API.

    Args:
        session_name: Имя сессии
        workdir: Рабочая директория

    Returns:
        Настроенный Pyrogram клиент
    """
    return Client(
        name=session_name,
        api_id=settings.user_api_api_id,
        api_hash=settings.user_api_api_hash,
        session_string=settings.user_api_session_string,
        workdir=workdir,
    )


# Singleton клиент
_client: Client | None = None
_queue: OrderedUploadQueue | None = None


async def get_upload_client() -> Client:
    """Возвращает singleton Pyrogram клиент."""
    global _client
    if _client is None:
        _client = build_pyrogram_client()
        await _client.start()
        
        # Проверяем, что клиент авторизован
        try:
            me = await _client.get_me()
            logger.info("Pyrogram client authorized as: {} (@{})", me.first_name, me.username)
        except Exception as e:
            logger.error("Failed to get user info from Pyrogram: {}", e)
            logger.error("Убедитесь, что USER_API_SESSION_STRING настроен в .env")
            raise
    
    return _client


async def get_upload_queue() -> OrderedUploadQueue:
    """Возвращает singleton очередь загрузки."""
    global _queue
    if _queue is None:
        client = await get_upload_client()
        _queue = OrderedUploadQueue(client)
    return _queue


async def shutdown_uploader() -> None:
    """Graceful shutdown загрузчика."""
    global _client, _queue

    if _queue:
        await _queue.shutdown()
        _queue = None

    if _client:
        await _client.stop()
        _client = None
