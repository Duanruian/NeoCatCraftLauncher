from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid as uuid_lib
from pathlib import Path
from typing import Any

from .config import Config

INSTANCE_FIELDS: tuple[str, ...] = (
    "name",
    "mc_version",
    "loader",
    "loader_version",
    "loader_installer",
    "version_id",
    "isolation",
    "directory",
    "memory_mb",
    "min_memory_mb",
    "java_path",
    "jvm_args",
    "resolution",
    "icon",
    "background",
    "group",
    "favorite",
    "notes",
)

_SAFE_ID = re.compile(r"[^a-z0-9._-]+")
_SAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


class InstanceError(ValueError):
    pass


def _slugify(text: str) -> str:
    slug = _SAFE_ID.sub("-", (text or "").strip().lower()).strip("-.")
    return slug or "instance"


def _sanitize_name(text: str) -> str:
    cleaned = _SAFE_NAME.sub("-", (text or "").strip()).strip(" .")
    return cleaned[:48] or "新实例"


def _default_icon(loader: str) -> str:
    mapping = {"fabric": "fabric", "forge": "forge", "neoforge": "neoforge", "quilt": "quilt"}
    return mapping.get((loader or "").lower(), "grass")


class InstanceManager:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.file = config.dir / "instances.json"
        self._lock = threading.RLock()
        self._items: list[dict[str, Any]] = []
        self._load()

    # ---------- 持久化 ----------

    def _load(self) -> None:
        if not self.file.is_file():
            return
        try:
            payload = json.loads(self.file.read_text(encoding="utf-8"))
        except Exception:
            return
        items = payload.get("instances") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            return
        for raw in items:
            if not isinstance(raw, dict):
                continue
            try:
                self._items.append(self._normalize(raw))
            except Exception:
                continue

    def _save(self) -> None:
        payload = {"instances": self._items, "version": 1}
        self.file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        instance_id = _slugify(str(raw.get("id") or uuid_lib.uuid4().hex[:10]))
        if any(item["id"] == instance_id for item in self._items):
            instance_id = f"{instance_id}-{uuid_lib.uuid4().hex[:4]}"
        loader = (raw.get("loader") or "vanilla").strip().lower()
        mc_version = str(raw.get("mc_version") or "").strip()
        record: dict[str, Any] = {
            "id": instance_id,
            "name": _sanitize_name(str(raw.get("name") or mc_version or "新实例")),
            "mc_version": mc_version,
            "loader": loader,
            "loader_version": str(raw.get("loader_version") or ""),
            "loader_installer": str(raw.get("loader_installer") or ""),
            "version_id": str(raw.get("version_id") or mc_version),
            "isolation": bool(raw.get("isolation", True)),
            "directory": str(raw.get("directory") or ""),
            "memory_mb": raw.get("memory_mb"),
            "min_memory_mb": raw.get("min_memory_mb"),
            "java_path": str(raw.get("java_path") or ""),
            "jvm_args": raw.get("jvm_args"),
            "resolution": raw.get("resolution"),
            "icon": str(raw.get("icon") or _default_icon(loader)),
            "background": str(raw.get("background") or ""),
            "group": str(raw.get("group") or ""),
            "favorite": bool(raw.get("favorite", False)),
            "notes": str(raw.get("notes") or ""),
            "created_at": float(raw.get("created_at") or time.time()),
            "last_played": float(raw.get("last_played") or 0),
            "playtime": int(raw.get("playtime") or 0),
        }
        return record

    # ---------- 查询 ----------

    def raw_list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._items]

    def get(self, instance_id: str) -> dict[str, Any] | None:
        with self._lock:
            for item in self._items:
                if item["id"] == instance_id:
                    return dict(item)
        return None

    def require(self, instance_id: str) -> dict[str, Any]:
        instance = self.get(instance_id)
        if instance is None:
            raise InstanceError(f"实例不存在: {instance_id}")
        return instance

    def resolve(self, instance_id: str | None) -> dict[str, Any] | None:
        if instance_id:
            return self.get(instance_id)
        active = (self.config.get("active_instance") or "").strip()
        if active:
            return self.get(active)
        items = self.raw_list()
        return items[0] if items else None

    def directory_of(self, instance: dict[str, Any]) -> Path:
        custom = (instance.get("directory") or "").strip()
        if custom:
            path = Path(custom)
        elif instance.get("isolation", True):
            path = self.config.instances_directory / instance["id"]
        else:
            path = self.config.minecraft_directory
        path.mkdir(parents=True, exist_ok=True)
        return path

    def mods_directory_of(self, instance: dict[str, Any] | None) -> Path:
        if instance is None:
            return self.config.mods_directory
        path = self.directory_of(instance) / "mods"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def version_installed(self, instance: dict[str, Any]) -> bool:
        version_id = instance.get("version_id") or instance.get("mc_version")
        if not version_id:
            return False
        loader = str(instance.get("loader") or "vanilla").lower()
        if loader not in {"", "vanilla"} and version_id == instance.get("mc_version"):
            return False
        json_file = self.config.minecraft_directory / "versions" / version_id / f"{version_id}.json"
        return json_file.is_file()

    def snapshot(self, instance: dict[str, Any]) -> dict[str, Any]:
        payload = dict(instance)
        directory = self.directory_of(instance)
        payload["directory"] = str(directory)
        payload["mods_directory"] = str(directory / "mods")
        payload["installed"] = self.version_installed(instance)
        payload["display_loader"] = (
            "原版"
            if instance.get("loader") in ("", "vanilla")
            else f"{str(instance.get('loader')).title()} {instance.get('loader_version') or ''}".strip()
        )
        return payload

    def list(self) -> list[dict[str, Any]]:
        items = [self.snapshot(item) for item in self.raw_list()]
        items.sort(key=lambda item: (not item.get("favorite"), -float(item.get("last_played") or 0), item.get("name", "")))
        return items

    # ---------- 写入 ----------

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        mc_version = str(payload.get("mc_version") or "").strip()
        if not mc_version:
            raise InstanceError("缺少 Minecraft 版本")
        loader = str(payload.get("loader") or "vanilla").strip().lower()
        name = _sanitize_name(str(payload.get("name") or f"{mc_version} {loader}".strip()))
        with self._lock:
            base_id = _slugify(payload.get("id") or name)
            instance_id = base_id
            counter = 1
            existing = {item["id"] for item in self._items}
            while instance_id in existing:
                counter += 1
                instance_id = f"{base_id}-{counter}"
            record = self._normalize(
                {
                    **payload,
                    "id": instance_id,
                    "name": name,
                    "mc_version": mc_version,
                    "loader": loader,
                }
            )
            record["id"] = instance_id
            self._items.append(record)
            self._save()
        directory = self.directory_of(record)
        for folder in ("mods", "saves", "resourcepacks", "shaderpacks", "config", "logs"):
            (directory / folder).mkdir(parents=True, exist_ok=True)
        if not (self.config.get("active_instance") or "").strip():
            self.config.set("active_instance", instance_id)
        return self.snapshot(record)

    def update(self, instance_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            for index, item in enumerate(self._items):
                if item["id"] != instance_id:
                    continue
                updated = dict(item)
                for key in INSTANCE_FIELDS:
                    if key in patch:
                        updated[key] = patch[key]
                if "name" in patch:
                    updated["name"] = _sanitize_name(str(patch["name"]))
                if "loader" in patch:
                    updated["loader"] = str(patch["loader"] or "vanilla").lower()
                if updated.get("isolation") and updated.get("directory"):
                    updated["directory"] = ""
                self._items[index] = self._normalize({**updated, "id": instance_id})
                self._items[index]["id"] = instance_id
                self._save()
                return self.snapshot(self._items[index])
        raise InstanceError(f"实例不存在: {instance_id}")

    def delete(self, instance_id: str, delete_files: bool = False) -> dict[str, Any]:
        with self._lock:
            target = None
            for item in self._items:
                if item["id"] == instance_id:
                    target = item
                    break
            if target is None:
                raise InstanceError(f"实例不存在: {instance_id}")
            self._items = [item for item in self._items if item["id"] != instance_id]
            self._save()
        if (self.config.get("active_instance") or "") == instance_id:
            remaining = self.raw_list()
            self.config.set("active_instance", remaining[0]["id"] if remaining else "")
        removed = False
        if delete_files and target.get("isolation", True):
            directory = self.directory_of(target)
            try:
                if directory.is_dir() and directory != self.config.minecraft_directory:
                    shutil.rmtree(directory, ignore_errors=True)
                    removed = True
            except Exception:
                removed = False
        return {"deleted": instance_id, "files_removed": removed}

    def duplicate(self, instance_id: str, name: str | None = None) -> dict[str, Any]:
        source = self.require(instance_id)
        payload = {key: source.get(key) for key in INSTANCE_FIELDS if key != "directory"}
        payload["name"] = name or f"{source['name']} 副本"
        payload["isolation"] = True
        payload["favorite"] = False
        created = self.create(payload)
        if source.get("isolation", True):
            try:
                shutil.copytree(
                    self.directory_of(source),
                    Path(created["directory"]),
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("logs", "crash-reports"),
                )
            except Exception:
                pass
        return created

    def touch_played(self, instance_id: str) -> None:
        with self._lock:
            for item in self._items:
                if item["id"] == instance_id:
                    item["last_played"] = time.time()
                    self._save()
                    return
