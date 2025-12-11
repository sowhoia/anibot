import asyncio
import shutil
from pathlib import Path
from typing import Optional

from loguru import logger

from app.config import settings
from app.integrations.kodik import KodikClient


class DownloadError(Exception):
    pass


class Downloader:
    def __init__(self, temp_dir: Path | None = None):
        self.temp_dir = temp_dir or settings.temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.kodik = KodikClient()

    async def download_episode(
        self,
        external_ids: dict,
        translation_id: int,
        episode_num: int,
        quality: int = 720,
    ) -> Path:
        """
        Скачивает серию в mp4 через ffmpeg (copy), возвращает путь к файлу.
        Требует установленный ffmpeg в системе.
        """
        m3u8_url = await self.kodik.get_episode_m3u8(
            external_ids=external_ids,
            translation_id=translation_id,
            episode_num=episode_num,
            quality=quality,
        )
        if not shutil.which("ffmpeg"):
            raise DownloadError("ffmpeg не найден в PATH")

        source_id = external_ids.get("shikimori") or external_ids.get("kinopoisk") or external_ids.get("imdb") or "unknown"
        out_path = self.temp_dir / f"{source_id}-{translation_id}-{episode_num}.mp4"
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            m3u8_url,
            "-c",
            "copy",
            "-bsf:a",
            "aac_adtstoasc",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
        logger.info(
            "ffmpeg download start source_id=%s tr=%s num=%s",
            source_id,
            translation_id,
            episode_num,
        )
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=settings.download_timeout_seconds,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            await self.cleanup_file(out_path)
            raise DownloadError(f"ffmpeg timed out after {settings.download_timeout_seconds}s")

        if proc.returncode != 0:
            await self.cleanup_file(out_path)
            raise DownloadError(f"ffmpeg failed: {stderr.decode()}")
        if not out_path.exists():
            raise DownloadError("ffmpeg completed but file not found")
        return out_path

    async def cleanup_file(self, path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:  # noqa: PERF203
            logger.warning("Cannot remove temp file %s: %s", path, exc)

