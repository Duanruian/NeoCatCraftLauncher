from __future__ import annotations

import json
import shutil
import tempfile
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
import minecraft_launcher_lib as mll

from .config import Config
from .events import EventBus, make_event
from .instances import InstanceError, InstanceManager
from .java_manager import JavaManager
from .mods.downloader import USER_AGENT, download_file
from .mods.platform import CURSEFORGE_API, CurseForgeClient, ModrinthClient, ModPlatformError
from .tasks import TaskManager

CURSEFORGE_MODPACK_CLASS = 4471

MRPACK_INDEX = "modrinth.index.json"
CURSEFORGE_MANIFEST = "manifest.json"


class ModpackError(RuntimeError):
    pass


def _loader_from_manifest_id(raw: str) -> tuple[str, str]:
    text = (raw or "").strip()
    if not text:
        return "vanilla", ""
    lowered = text.lower()
    for name in ("neoforge", "fabric", "quilt", "forge"):
        prefix = f"{name}-"
        if lowered.startswith(prefix):
            return name, text[len(prefix):]
    if "-" in text:
        head, _, tail = text.partition("-")
        return head.strip().lower(), tail.strip()
    return "vanilla", ""


def _loader_from_mrpack(dependencies: dict[str, Any]) -> tuple[str, str]:
    mapping = {
        "fabric-loader": "fabric",
        "quilt-loader": "quilt",
        "forge": "forge",
        "neoforge": "neoforge",
    }
    for key, loader in mapping.items():
        value = dependencies.get(key)
        if value:
            return loader, str(value)
    return "vanilla", ""


def _read_zip_json(archive: Path, name: str) -> dict[str, Any] | None:
    try:
        with zipfile.ZipFile(archive) as bundle:
            if name not in bundle.namelist():
                return None
            return json.loads(bundle.read(name).decode("utf-8"))
    except Exception:
        return None


def _safe_member(name: str, root: Path) -> Path | None:
    target = (root / name).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


def _extract_overrides(archive: Path, prefix: str, target_dir: Path) -> int:
    written = 0
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            if not entry.filename.startswith(prefix) or entry.is_dir():
                continue
            relative = entry.filename[len(prefix):]
            if not relative:
                continue
            destination = _safe_member(relative, target_dir)
            if destination is None:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(entry) as source, destination.open("wb") as handle:
                shutil.copyfileobj(source, handle)
            written += 1
    return written


class ModpackService:
    def __init__(
        self,
        config: Config,
        tasks: TaskManager,
        bus: EventBus,
        instances: InstanceManager,
        java: JavaManager,
    ) -> None:
        self.config = config
        self.tasks = tasks
        self.bus = bus
        self.instances = instances
        self.java = java
        self._lock = threading.Lock()

    # ---------- 平台 ----------

    def _modrinth(self) -> ModrinthClient:
        return ModrinthClient(timeout=20)

    def _curseforge(self) -> CurseForgeClient:
        return CurseForgeClient(self.config.get("curseforge_api_key") or "", timeout=20)

    def search(
        self,
        platform: str,
        query: str,
        minecraft_version: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        if platform == "all":
            return self._aggregate_search(query, minecraft_version, limit, offset)
        if platform == "curseforge":
            return self._curseforge().search(
                query,
                minecraft_version,
                None,
                limit,
                offset,
                class_id=CURSEFORGE_MODPACK_CLASS,
            )
        return self._modrinth().search(query, minecraft_version, None, limit, offset, project_type="modpack")

    def _aggregate_search(
        self,
        query: str,
        minecraft_version: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        hits: list[dict[str, Any]] = []
        warnings: list[str] = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(self.search, platform, query, minecraft_version, limit, offset): platform
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
            "total": len(hits),
            "hits": hits[: max(1, min(limit, 50))],
            "offset": max(0, offset),
            "warnings": warnings,
        }

    def versions(self, platform: str, project_id: str, minecraft_version: str | None = None) -> dict[str, Any]:
        if platform == "curseforge":
            files = self._curseforge().files(project_id, minecraft_version)
            items = [
                {
                    "version_id": item["version_id"],
                    "name": item.get("name"),
                    "version_number": item.get("version_number"),
                    "channel": item.get("channel"),
                    "game_versions": item.get("game_versions") or [],
                    "loaders": item.get("loaders") or [],
                    "date": item.get("date"),
                    "filename": (item.get("files") or [{}])[0].get("filename"),
                    "size": (item.get("files") or [{}])[0].get("size"),
                }
                for item in files
            ]
            return {"platform": platform, "project_id": project_id, "versions": items}
        modrinth = self._modrinth()
        return {
            "platform": platform,
            "project_id": project_id,
            "versions": modrinth.versions(project_id, minecraft_version, None),
        }

    # ---------- 安装 ----------

    def install(
        self,
        platform: str,
        project_id: str,
        version_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        project_id = str(project_id or "").strip()
        if not project_id:
            raise ModpackError("缺少 project_id")
        task = self.tasks.create("modpack", f"安装整合包 #{project_id}")

        def worker() -> None:
            temp_dir: Path | None = None
            try:
                url, filename = self._resolve_download(platform, project_id, version_id)
                temp_dir = Path(tempfile.mkdtemp(prefix="neo-modpack-"))
                archive = temp_dir / filename
                self.tasks.progress(task.id, message=f"下载整合包 {filename}")
                downloaded = download_file(
                    url,
                    temp_dir,
                    filename,
                    retries=int(self.config.get("download_retries", 3) or 3),
                    timeout=int(self.config.get("download_timeout", 60) or 60),
                    tasks=self.tasks,
                    task_id=task.id,
                    label=f"下载整合包 {filename}",
                )
                # download_file may sanitize or de-duplicate the requested name.
                # Always install the file that was actually written to disk.
                archive = Path(downloaded.path)
                instance = self._install_archive(archive, task.id, fallback_name=name)
                self.tasks.finish(
                    task.id,
                    {"instance": instance["id"], "name": instance["name"]},
                    f"整合包已安装：{instance['name']}",
                )
                self.bus.publish(make_event("instances.changed"))
                self.bus.publish(make_event("versions.changed"))
                self.bus.log(f"整合包 {instance['name']} 已安装到 {instance['directory']}", source="modpack")
            except Exception as error:
                self.tasks.fail(task.id, str(error))
                self.bus.log(f"整合包安装失败: {error}", source="modpack", level="error")
            finally:
                if temp_dir is not None:
                    shutil.rmtree(temp_dir, ignore_errors=True)

        threading.Thread(target=worker, daemon=True).start()
        return task.snapshot()

    def import_file(self, path: str, name: str | None = None) -> dict[str, Any]:
        source = Path(path)
        if not source.is_file():
            raise ModpackError(f"文件不存在: {path}")
        task = self.tasks.create("modpack", f"导入整合包 {source.name}")

        def worker() -> None:
            try:
                instance = self._install_archive(source, task.id, fallback_name=name)
                self.tasks.finish(
                    task.id,
                    {"instance": instance["id"], "name": instance["name"]},
                    f"整合包已导入：{instance['name']}",
                )
                self.bus.publish(make_event("instances.changed"))
                self.bus.publish(make_event("versions.changed"))
            except Exception as error:
                self.tasks.fail(task.id, str(error))
                self.bus.log(f"导入整合包失败: {error}", source="modpack", level="error")

        threading.Thread(target=worker, daemon=True).start()
        return task.snapshot()

    # ---------- 内部 ----------

    def _resolve_download(self, platform: str, project_id: str, version_id: str | None) -> tuple[str, str]:
        if platform == "curseforge":
            client = self._curseforge()
            if version_id:
                item = client.file(project_id, version_id)
            else:
                files = client.files(project_id)
                if not files:
                    raise ModpackError("该整合包没有可用文件")
                item = files[0]
            primary = (item.get("files") or [None])[0]
            if not primary or not primary.get("url"):
                raise ModpackError("CurseForge 未提供该整合包的下载地址")
            return primary["url"], primary.get("filename") or f"{project_id}-{version_id}.zip"
        modrinth = self._modrinth()
        if version_id:
            version = modrinth.version(version_id)
        else:
            files = modrinth.versions(project_id, None, None)
            if not files:
                raise ModpackError("该整合包没有可用版本")
            version = files[0]
        primary = next((item for item in version.get("files") or [] if item.get("primary")), None)
        if primary is None:
            files = version.get("files") or []
            primary = files[0] if files else None
        if not primary or not primary.get("url"):
            raise ModpackError("Modrinth 未提供该整合包的下载地址")
        return primary["url"], primary.get("filename") or f"{project_id}.mrpack"

    def _install_archive(self, archive: Path, task_id: str, fallback_name: str | None = None) -> dict[str, Any]:
        if _read_zip_json(archive, MRPACK_INDEX) is not None:
            return self._install_mrpack(archive, task_id, fallback_name)
        if _read_zip_json(archive, CURSEFORGE_MANIFEST) is not None:
            return self._install_curseforge(archive, task_id, fallback_name)
        raise ModpackError("无法识别的整合包格式（仅支持 .mrpack 与 CurseForge 整合包）")

    def _install_mrpack(self, archive: Path, task_id: str, fallback_name: str | None) -> dict[str, Any]:
        index = _read_zip_json(archive, MRPACK_INDEX) or {}
        dependencies = index.get("dependencies") or {}
        mc_version = str(dependencies.get("minecraft") or "").strip()
        if not mc_version:
            raise ModpackError("整合包缺少 Minecraft 版本信息")
        loader, loader_version = _loader_from_mrpack(dependencies)
        title = str(index.get("name") or fallback_name or archive.stem)
        instance = self.instances.create(
            {
                "name": title,
                "mc_version": mc_version,
                "loader": loader,
                "loader_version": loader_version,
                "isolation": True,
                "notes": str(index.get("summary") or ""),
            }
        )
        directory = self.instances.directory_of(instance)
        self.tasks.progress(task_id, message=f"安装基础环境 Minecraft {mc_version}")
        version_id = self._install_base(mc_version, loader, loader_version, task_id)
        self.instances.update(instance["id"], {"version_id": version_id})
        self.tasks.progress(task_id, message="下载整合包模组文件")
        mll.mrpack.install_mrpack(
            str(archive),
            str(self.config.minecraft_directory),
            modpack_directory=str(directory),
            callback=self._callback(task_id),
            mrpack_install_options={"skipDependenciesInstall": True},
        )
        return self.instances.require(instance["id"])

    def _install_curseforge(self, archive: Path, task_id: str, fallback_name: str | None) -> dict[str, Any]:
        manifest = _read_zip_json(archive, CURSEFORGE_MANIFEST) or {}
        minecraft = manifest.get("minecraft") or {}
        mc_version = str(minecraft.get("version") or "").strip()
        if not mc_version:
            raise ModpackError("整合包缺少 Minecraft 版本信息")
        loaders = [
            item for item in minecraft.get("modLoaders") or []
            if isinstance(item, dict) and item.get("id")
        ]
        primary = next((item for item in loaders if item.get("primary")), None)
        if primary is None and loaders:
            primary = loaders[0]
        loader_raw = str((primary or {}).get("id") or "")
        loader, loader_version = _loader_from_manifest_id(loader_raw)
        title = str(manifest.get("name") or fallback_name or archive.stem)
        authors = manifest.get("author") or ""
        instance = self.instances.create(
            {
                "name": title,
                "mc_version": mc_version,
                "loader": loader,
                "loader_version": loader_version,
                "isolation": True,
                "notes": f"CurseForge 整合包 {manifest.get('version') or ''} · {authors}".strip(),
            }
        )
        directory = self.instances.directory_of(instance)
        self.tasks.progress(task_id, message=f"安装基础环境 Minecraft {mc_version}")
        version_id = self._install_base(mc_version, loader, loader_version, task_id)
        self.instances.update(instance["id"], {"version_id": version_id})

        overrides = str(manifest.get("overrides") or "overrides").rstrip("/") + "/"
        self.tasks.progress(task_id, message="释放整合包配置文件")
        _extract_overrides(archive, overrides, directory)

        entries = [item for item in manifest.get("files") or [] if item.get("required", True)]
        mods_dir = self.instances.mods_directory_of(instance)
        total = max(1, len(entries))
        self.tasks.progress(task_id, total=total, progress=0, message="下载整合包模组文件")
        failures: list[str] = []
        for position, entry in enumerate(entries):
            project_id = str(entry.get("projectID") or "").strip()
            file_id = str(entry.get("fileID") or "").strip()
            if not project_id or not file_id:
                failures.append("整合包清单中存在缺少 projectID/fileID 的文件")
                continue
            try:
                url, filename = self._curseforge_file(project_id, file_id)
                download_file(
                    url,
                    mods_dir,
                    filename,
                    retries=int(self.config.get("download_retries", 3) or 3),
                    timeout=int(self.config.get("download_timeout", 60) or 60),
                    tasks=self.tasks,
                    task_id=task_id,
                    label=f"下载 {filename}",
                )
            except Exception as error:
                detail = f"{project_id}/{file_id}: {error}"
                failures.append(detail)
                self.bus.log(f"CurseForge 文件下载失败 {detail}", source="modpack", level="error")
            self.tasks.progress(task_id, progress=position + 1, total=total)
        if failures:
            preview = "；".join(failures[:3])
            suffix = f"；另有 {len(failures) - 3} 个文件失败" if len(failures) > 3 else ""
            raise ModpackError(f"有 {len(failures)} 个必需文件下载失败：{preview}{suffix}")
        return self.instances.require(instance["id"])

    def _curseforge_file(self, project_id: str, file_id: str) -> tuple[str, str]:
        item = self._curseforge().file(project_id, file_id)
        primary = (item.get("files") or [{}])[0]
        url = primary.get("url")
        filename = primary.get("filename")
        if url:
            return url, filename or f"{project_id}-{file_id}.jar"
        api_key = (self.config.get("curseforge_api_key") or "").strip()
        if not api_key:
            raise ModpackError("CurseForge 需要 API Key 才能下载该文件")
        headers = {"User-Agent": USER_AGENT, "x-api-key": api_key, "Accept": "application/json"}
        with httpx.Client(timeout=30, follow_redirects=True, headers=headers) as client:
            response = client.get(f"{CURSEFORGE_API}/mods/{project_id}/files/{file_id}/download-url")
        if response.status_code != 200:
            raise ModpackError(f"CurseForge 下载地址获取失败（HTTP {response.status_code}）")
        resolved = (response.json() or {}).get("data")
        if not resolved:
            raise ModpackError("该文件不允许第三方下载")
        return resolved, filename or unquote(urlparse(resolved).path.rsplit("/", 1)[-1])

    def _install_base(self, mc_version: str, loader: str, loader_version: str, task_id: str) -> str:
        self.tasks.progress(task_id, message=f"安装 Minecraft {mc_version}")
        mll.install.install_minecraft_version(
            mc_version,
            str(self.config.minecraft_directory),
            callback=self._callback(task_id),
        )
        version_id = mc_version
        if loader and loader != "vanilla":
            self.tasks.progress(task_id, message=f"安装 {loader} {loader_version}".strip())
            module = mll.mod_loader.get_mod_loader(loader)
            version_id = module.install(
                mc_version,
                str(self.config.minecraft_directory),
                loader_version=loader_version or None,
                callback=self._callback(task_id),
                java=self.java.resolve_for_install(mc_version),
            )
        return version_id

    def _callback(self, task_id: str) -> dict[str, Any]:
        def set_status(status: str) -> None:
            self.tasks.progress(task_id, message=str(status))

        def set_progress(progress: int) -> None:
            self.tasks.progress(task_id, progress=int(progress))

        def set_max(maximum: int) -> None:
            self.tasks.progress(task_id, total=int(maximum))

        return {"setStatus": set_status, "setProgress": set_progress, "setMax": set_max}


__all__ = ["ModpackError", "ModpackService", "ModPlatformError", "InstanceError"]
