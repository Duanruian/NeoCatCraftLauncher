from __future__ import annotations

import base64
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .config import Config
from .events import EventBus, make_event
from .mods.downloader import download_file
from .mods.platform import (
    CurseForgeClient,
    ModPlatformError,
    ModrinthClient,
)
from .tasks import TaskManager

CONTENT_KINDS: dict[str, dict[str, Any]] = {
    "resourcepack": {
        "label": "资源包",
        "modrinth_type": "resourcepack",
        "curseforge_class": 12,
        "directory": "resourcepacks",
        "extensions": {".zip"},
    },
    "shader": {
        "label": "光影包",
        "modrinth_type": "shader",
        "curseforge_class": 6552,
        "directory": "shaderpacks",
        "extensions": {".zip"},
    },
    "datapack": {
        "label": "数据包",
        "modrinth_type": "datapack",
        "curseforge_class": 6945,
        "directory": "datapacks",
        "extensions": {".zip"},
    },
}

ICON_LIMIT_BYTES = 128 * 1024


def _safe_child(root: Path, name: str) -> Path | None:
    if not name or name in {".", ".."}:
        return None
    try:
        candidate = (root / name).resolve()
        candidate.relative_to(root.resolve())
    except Exception:
        return None
    return candidate


def _archive_icon(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path) as archive:
            candidates = [
                entry
                for entry in archive.infolist()
                if not entry.is_dir()
                and entry.filename.lower() in {"pack.png", "thumbnail.png", "icon.png"}
                and entry.file_size <= ICON_LIMIT_BYTES
            ]
            if not candidates:
                return None
            data = archive.read(candidates[0])
            return "data:image/png;base64," + base64.b64encode(data).decode("ascii")
    except Exception:
        return None


class ContentService:
    def __init__(
        self,
        config: Config,
        tasks: TaskManager,
        bus: EventBus,
        instances: Any = None,
    ) -> None:
        self.config = config
        self.tasks = tasks
        self.bus = bus
        self.instances = instances
        self._lock = threading.Lock()

    def _clients(self) -> tuple[ModrinthClient, CurseForgeClient]:
        return (
            ModrinthClient(timeout=20),
            CurseForgeClient(self.config.get("curseforge_api_key") or "", timeout=20),
        )

    @staticmethod
    def _kind(kind: str) -> dict[str, Any]:
        normalized = (kind or "").strip().lower()
        if normalized not in CONTENT_KINDS:
            raise ModPlatformError(f"不支持的内容类型: {kind}")
        return CONTENT_KINDS[normalized]

    def _instance_root(self, instance_id: str | None) -> Path:
        if self.instances is not None and instance_id:
            instance = self.instances.get(instance_id)
            if instance is None:
                raise ModPlatformError("实例不存在")
            return self.instances.directory_of(instance)
        return self.config.minecraft_directory

    def directory(self, kind: str, instance_id: str | None, world: str | None = None) -> Path:
        definition = self._kind(kind)
        root = self._instance_root(instance_id)
        if kind == "datapack" and world:
            saves = root / "saves"
            save_dir = _safe_child(saves, world)
            if save_dir is None or not save_dir.is_dir():
                raise ModPlatformError("所选存档不存在")
            target = save_dir / "datapacks"
        else:
            target = root / str(definition["directory"])
        target.mkdir(parents=True, exist_ok=True)
        return target

    def search(
        self,
        kind: str,
        platform: str,
        query: str,
        minecraft_version: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        definition = self._kind(kind)
        normalized_platform = (platform or "all").lower()
        if normalized_platform == "all":
            return self._aggregate_search(
                definition,
                query,
                minecraft_version,
                limit,
                offset,
            )
        return self._search_platform(
            normalized_platform,
            definition,
            query,
            minecraft_version,
            limit,
            offset,
        )

    def _search_platform(
        self,
        platform: str,
        definition: dict[str, Any],
        query: str,
        minecraft_version: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        modrinth, curseforge = self._clients()
        if platform == "curseforge":
            payload = curseforge.search(
                query,
                minecraft_version,
                None,
                limit,
                offset,
                class_id=int(definition["curseforge_class"]),
            )
        elif platform == "modrinth":
            payload = modrinth.search(
                query,
                minecraft_version,
                None,
                limit,
                offset,
                project_type=str(definition["modrinth_type"]),
            )
        else:
            raise ModPlatformError(f"未知平台: {platform}")
        for hit in payload.get("hits") or []:
            hit["kind"] = definition["modrinth_type"]
        return payload

    def _aggregate_search(
        self,
        definition: dict[str, Any],
        query: str,
        minecraft_version: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        hits: list[dict[str, Any]] = []
        warnings: list[str] = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(
                    self._search_platform,
                    platform,
                    definition,
                    query,
                    minecraft_version,
                    limit,
                    offset,
                ): platform
                for platform in ("modrinth", "curseforge")
            }
            for future in as_completed(futures):
                platform = futures[future]
                try:
                    payload = future.result()
                    hits.extend(payload.get("hits") or [])
                except Exception as error:
                    warnings.append(f"{platform}: {error}")
        hits.sort(
            key=lambda item: (
                -int(item.get("downloads") or 0),
                str(item.get("title") or "").lower(),
            )
        )
        return {
            "platform": "all",
            "kind": definition["modrinth_type"],
            "total": len(hits),
            "hits": hits[: max(1, min(limit, 50))],
            "offset": max(0, offset),
            "warnings": warnings,
        }

    def versions(
        self,
        kind: str,
        platform: str,
        project_id: str,
        minecraft_version: str | None = None,
    ) -> dict[str, Any]:
        self._kind(kind)
        modrinth, curseforge = self._clients()
        if platform == "curseforge":
            items = curseforge.files(project_id, minecraft_version, None)
        else:
            items = modrinth.versions(project_id, minecraft_version, None)
        return {"platform": platform, "project_id": project_id, "kind": kind, "versions": items}

    def install(
        self,
        kind: str,
        platform: str,
        project_id: str,
        version_id: str | None = None,
        minecraft_version: str | None = None,
        instance_id: str | None = None,
        world: str | None = None,
    ) -> dict[str, Any]:
        definition = self._kind(kind)
        target_dir = self.directory(kind, instance_id, world)
        task = self.tasks.create("download", f"下载{definition['label']} #{project_id}")

        def worker() -> None:
            try:
                modrinth, curseforge = self._clients()
                if platform == "curseforge":
                    if version_id:
                        version = curseforge.file(project_id, version_id)
                    else:
                        versions = curseforge.files(project_id, minecraft_version, None)
                        if not versions:
                            raise ModPlatformError("没有匹配当前游戏版本的 CurseForge 文件")
                        version = versions[0]
                else:
                    if version_id:
                        version = modrinth.version(version_id)
                    else:
                        versions = modrinth.versions(project_id, minecraft_version, None)
                        if not versions:
                            raise ModPlatformError("没有匹配当前游戏版本的 Modrinth 文件")
                        version = versions[0]

                files = [item for item in version.get("files") or [] if item.get("url")]
                primary = next((item for item in files if item.get("primary")), files[0] if files else None)
                if primary is None:
                    raise ModPlatformError("该版本没有可下载文件")
                result = download_file(
                    primary["url"],
                    target_dir,
                    primary.get("filename") or f"{project_id}.zip",
                    expected_size=primary.get("size"),
                    sha1=primary.get("sha1"),
                    retries=int(self.config.get("download_retries", 3) or 3),
                    timeout=int(self.config.get("download_timeout", 60) or 60),
                    tasks=self.tasks,
                    task_id=task.id,
                    label=f"下载{definition['label']}",
                )
                self.tasks.finish(
                    task.id,
                    {"path": result.path, "kind": kind},
                    f"{definition['label']}已保存到 {Path(result.path).name}",
                )
                self.bus.publish(
                    make_event("content.changed", content_kind=kind, instance_id=instance_id)
                )
                self.bus.log(f"{definition['label']}已保存到 {result.path}", source="content")
            except Exception as error:
                self.tasks.fail(task.id, str(error))
                self.bus.log(f"{definition['label']}下载失败: {error}", source="content", level="error")

        threading.Thread(target=worker, daemon=True).start()
        return task.snapshot()

    def scan(self, kind: str, instance_id: str | None, world: str | None = None) -> dict[str, Any]:
        definition = self._kind(kind)
        directory = self.directory(kind, instance_id, world)
        extensions = definition["extensions"]
        items: list[dict[str, Any]] = []
        for path in sorted(directory.iterdir(), key=lambda item: item.name.lower()):
            if not path.is_file():
                continue
            actual = path.name[: -len(".disabled")] if path.name.lower().endswith(".disabled") else path.name
            if Path(actual).suffix.lower() not in extensions:
                continue
            stat = path.stat()
            items.append(
                {
                    "file_name": path.name,
                    "name": Path(actual).stem,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "enabled": not path.name.lower().endswith(".disabled"),
                    "icon": _archive_icon(path),
                    "kind": kind,
                }
            )
        items.sort(key=lambda item: (-float(item["modified"]), item["name"].lower()))
        return {
            "kind": kind,
            "label": definition["label"],
            "directory": str(directory),
            "count": len(items),
            "items": items,
            "world": world or "",
        }

    def toggle(self, kind: str, file_name: str, instance_id: str | None, world: str | None = None) -> dict[str, Any]:
        directory = self.directory(kind, instance_id, world)
        source = _safe_child(directory, file_name)
        if source is None or not source.is_file():
            raise ModPlatformError("文件不存在")
        if source.name.lower().endswith(".disabled"):
            target = source.with_name(source.name[: -len(".disabled")])
        else:
            target = source.with_name(source.name + ".disabled")
        if target.exists():
            raise ModPlatformError(f"{target.name} 已存在，无法切换")
        source.replace(target)
        self.bus.publish(
            make_event("content.changed", content_kind=kind, instance_id=instance_id)
        )
        return {"file": target.name, "enabled": not target.name.lower().endswith(".disabled")}

    def delete(self, kind: str, file_name: str, instance_id: str | None, world: str | None = None) -> dict[str, Any]:
        directory = self.directory(kind, instance_id, world)
        target = _safe_child(directory, file_name)
        if target is None or not target.is_file():
            raise ModPlatformError("文件不存在")
        target.unlink()
        self.bus.publish(
            make_event("content.changed", content_kind=kind, instance_id=instance_id)
        )
        return {"deleted": target.name}


__all__ = ["CONTENT_KINDS", "ContentService"]
