from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ..tasks import TaskManager

USER_AGENT = "NeoCatCraftLauncher/0.1.0 (mod manager; +https://modrinth.com)"
CHUNK_SIZE = 64 * 1024
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_KNOWN_EXTENSIONS = (".jar", ".jar.disabled", ".zip", ".mrpack")


@dataclass
class DownloadResult:
    path: str
    size: int
    skipped: bool
    attempts: int
    renamed_from: str | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size": self.size,
            "skipped": self.skipped,
            "attempts": self.attempts,
            "renamed_from": self.renamed_from,
        }


def sanitize_filename(filename: str) -> str:
    name = _ILLEGAL.sub("_", (filename or "").strip()).strip(" .")
    if not name:
        name = "download.jar"
    if not name.lower().endswith(_KNOWN_EXTENSIONS):
        name += ".jar"
    return name[:180]


def resolve_target(directory: Path, filename: str) -> tuple[Path, bool]:
    directory.mkdir(parents=True, exist_ok=True)
    clean = sanitize_filename(filename)
    target = directory / clean
    if not target.exists():
        return target, False
    stem = target.stem
    suffix = target.suffix
    if clean.lower().endswith(".jar.disabled"):
        stem = clean[: -len(".jar.disabled")]
        suffix = ".jar.disabled"
    index = 1
    while True:
        candidate = directory / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate, True
        index += 1


def _existing_same_file(target: Path, expected_size: int | None) -> bool:
    if not target.exists() or not expected_size:
        return False
    try:
        return target.stat().st_size == expected_size
    except OSError:
        return False


def download_file(
    url: str,
    directory: Path,
    filename: str,
    *,
    expected_size: int | None = None,
    sha1: str | None = None,
    retries: int = 3,
    timeout: int = 60,
    tasks: TaskManager | None = None,
    task_id: str | None = None,
    label: str = "",
) -> DownloadResult:
    directory.mkdir(parents=True, exist_ok=True)
    base_target = directory / sanitize_filename(filename)

    if _existing_same_file(base_target, expected_size):
        if tasks and task_id:
            tasks.progress(task_id, progress=expected_size, total=expected_size, message="已存在相同文件，跳过")
        return DownloadResult(path=str(base_target), size=expected_size or 0, skipped=True, attempts=0)

    target, renamed = resolve_target(directory, filename)
    partial = target.with_name(target.name + ".part")
    attempts = 0
    last_error: Exception | None = None

    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}

    while attempts < max(1, retries):
        attempts += 1
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
                with client.stream("GET", url) as response:
                    response.raise_for_status()
                    total = expected_size or int(response.headers.get("Content-Length") or 0)
                    if tasks and task_id and total:
                        tasks.progress(task_id, progress=0, total=total, message=label or "开始下载")
                    digest = hashlib.sha1()
                    written = 0
                    with partial.open("wb") as handle:
                        for chunk in response.iter_bytes(CHUNK_SIZE):
                            if not chunk:
                                continue
                            handle.write(chunk)
                            digest.update(chunk)
                            written += len(chunk)
                            if tasks and task_id:
                                tasks.progress(task_id, progress=written, message=label or "下载中")
                    if sha1 and digest.hexdigest().lower() != sha1.lower():
                        raise ValueError("文件校验失败（SHA1 不匹配）")
                    if expected_size and written != expected_size:
                        raise ValueError(f"文件大小不匹配（期望 {expected_size}，实际 {written}）")
            partial.replace(target)
            return DownloadResult(
                path=str(target),
                size=written,
                skipped=False,
                attempts=attempts,
                renamed_from=target.name if renamed else None,
            )
        except Exception as error:
            last_error = error
            try:
                partial.unlink(missing_ok=True)
            except OSError:
                pass
            if attempts < max(1, retries):
                if tasks and task_id:
                    tasks.progress(task_id, message=f"下载失败，第 {attempts} 次重试…")
                time.sleep(min(1.5 * attempts, 6))
    raise RuntimeError(f"下载失败（已尝试 {attempts} 次）：{last_error}")
