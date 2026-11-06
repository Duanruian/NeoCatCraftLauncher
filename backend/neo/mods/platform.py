from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from ..config import Config
from ..events import EventBus, make_event
from ..tasks import TaskManager
from .downloader import USER_AGENT, download_file
from .scanner import scan_mods

MODRINTH_API = "https://api.modrinth.com/v2"
CURSEFORGE_API = "https://api.curseforge.com/v1"
CURSEFORGE_GAME_ID = 432
CURSEFORGE_MOD_CLASS = 6
CURSEFORGE_LOADER_TYPES = {"forge": 1, "fabric": 4, "quilt": 5, "neoforge": 6}
CURSEFORGE_RELATION_REQUIRED = 3
MODRINTH_LOADERS = {"forge", "fabric", "quilt", "neoforge"}
MODRINTH_PROJECT_PATHS = {
    "mod": "mod",
    "modpack": "modpack",
    "shader": "shader",
    "resourcepack": "resourcepack",
    "datapack": "datapack",
}
_MC_VERSION = re.compile(r"^\d+\.\d+(\.\d+)?([-.][0-9A-Za-z]+)*$")


class ModPlatformError(RuntimeError):
    pass


def _http(timeout: int = 20) -> httpx.Client:
    return httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def _dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def _trim(text: Any, limit: int = 400) -> str:
    cleaned = " ".join(str(text or "").split())
    return cleaned[:limit]


def _sha1_from_hashes(value: Any) -> str | None:
    if isinstance(value, dict):
        direct = value.get("sha1") or value.get("1")
        if direct:
            return str(direct)
        for entry in value.values():
            if isinstance(entry, dict):
                resolved = _sha1_from_hashes(entry)
                if resolved:
                    return resolved
        return None
    if isinstance(value, list):
        for entry in value:
            if not isinstance(entry, dict):
                continue
            if entry.get("algo") in (1, "1", "sha1") and entry.get("value"):
                return str(entry["value"])
        for entry in value:
            if isinstance(entry, dict) and entry.get("value"):
                return str(entry["value"])
    return None


class ModrinthClient:
    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout

    def search(
        self,
        query: str,
        minecraft_version: str | None,
        loader: str | None,
        limit: int = 20,
        offset: int = 0,
        project_type: str = "mod",
    ) -> dict[str, Any]:
        facets: list[list[str]] = [[f"project_type:{project_type}"]]
        if loader in MODRINTH_LOADERS:
            facets.append([f"categories:{loader}"])
        if minecraft_version:
            facets.append([f"versions:{minecraft_version}"])
        params = {
            "query": query or "",
            "limit": max(1, min(limit, 50)),
            "offset": max(0, offset),
            "index": "relevance" if query else "downloads",
            "facets": _dumps(facets),
        }
        with _http(self.timeout) as client:
            response = client.get(f"{MODRINTH_API}/search", params=params)
            if response.status_code != 200:
                raise ModPlatformError(f"Modrinth 搜索失败（HTTP {response.status_code}）")
            payload = response.json()
        hits = [self._normalize_hit(hit, project_type) for hit in payload.get("hits", [])]
        return {"platform": "modrinth", "total": payload.get("total_hits", len(hits)), "hits": hits, "offset": params["offset"]}

    @staticmethod
    def _normalize_hit(hit: dict[str, Any], project_type: str = "mod") -> dict[str, Any]:
        project_path = MODRINTH_PROJECT_PATHS.get(project_type, project_type)
        return {
            "platform": "modrinth",
            "id": hit.get("project_id"),
            "slug": hit.get("slug"),
            "title": hit.get("title") or hit.get("slug"),
            "description": _trim(hit.get("description")),
            "author": hit.get("author"),
            "downloads": hit.get("downloads") or 0,
            "follows": hit.get("follows") or 0,
            "icon": hit.get("icon_url"),
            "categories": hit.get("display_categories") or hit.get("categories") or [],
            "url": f"https://modrinth.com/{project_path}/{hit.get('slug')}" if hit.get("slug") else None,
            "project_type": project_type,
            "game_versions": (hit.get("versions") or [])[-8:],
            "date_modified": hit.get("date_modified"),
        }

    def versions(self, project_id: str, minecraft_version: str | None = None, loader: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if minecraft_version:
            params["game_versions"] = _dumps([minecraft_version])
        if loader in MODRINTH_LOADERS:
            params["loaders"] = _dumps([loader])
        with _http(self.timeout) as client:
            response = client.get(f"{MODRINTH_API}/project/{project_id}/version", params=params)
            if response.status_code != 200:
                raise ModPlatformError(f"Modrinth 版本列表获取失败（HTTP {response.status_code}）")
            payload = response.json()
        return [self.normalize_version(item, project_id) for item in payload]

    def version(self, version_id: str) -> dict[str, Any]:
        with _http(self.timeout) as client:
            response = client.get(f"{MODRINTH_API}/version/{version_id}")
            if response.status_code != 200:
                raise ModPlatformError(f"Modrinth 版本详情获取失败（HTTP {response.status_code}）")
            payload = response.json()
        return self.normalize_version(payload, payload.get("project_id"))

    def projects(self, ids: list[str]) -> dict[str, str]:
        if not ids:
            return {}
        with _http(self.timeout) as client:
            response = client.get(f"{MODRINTH_API}/projects", params={"ids": _dumps(ids)})
            if response.status_code != 200:
                return {}
            payload = response.json()
        return {item.get("id"): item.get("title") or item.get("slug") for item in payload if isinstance(item, dict)}

    @staticmethod
    def normalize_version(payload: dict[str, Any], project_id: str | None) -> dict[str, Any]:
        files = []
        for item in payload.get("files") or []:
            files.append(
                {
                    "url": item.get("url"),
                    "filename": item.get("filename"),
                    "size": item.get("size"),
                    "primary": bool(item.get("primary")),
                    "sha1": _sha1_from_hashes(item.get("hashes")),
                }
            )
        dependencies = []
        for item in payload.get("dependencies") or []:
            dependencies.append(
                {
                    "project_id": item.get("project_id"),
                    "version_id": item.get("version_id"),
                    "dependency_type": item.get("dependency_type") or "optional",
                }
            )
        return {
            "platform": "modrinth",
            "project_id": project_id or payload.get("project_id"),
            "version_id": payload.get("id"),
            "name": payload.get("name"),
            "version_number": payload.get("version_number"),
            "channel": payload.get("version_type") or "release",
            "game_versions": payload.get("game_versions") or [],
            "loaders": payload.get("loaders") or [],
            "date": payload.get("date_published"),
            "downloads": payload.get("downloads") or 0,
            "files": files,
            "dependencies": dependencies,
        }


class CurseForgeClient:
    def __init__(self, api_key: str, timeout: int = 20) -> None:
        self.api_key = (api_key or "").strip()
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ModPlatformError("CurseForge 需要 API Key，请先在设置中填写 curseforge_api_key")
        return {"User-Agent": USER_AGENT, "x-api-key": self.api_key, "Accept": "application/json"}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        with _http(self.timeout) as client:
            response = client.get(f"{CURSEFORGE_API}{path}", params=params, headers=self._headers())
            if response.status_code == 403:
                raise ModPlatformError("CurseForge 拒绝了请求，请检查 API Key 是否有效")
            if response.status_code != 200:
                raise ModPlatformError(f"CurseForge 请求失败（HTTP {response.status_code}）")
            return response.json().get("data")

    def search(
        self,
        query: str,
        minecraft_version: str | None,
        loader: str | None,
        limit: int = 20,
        offset: int = 0,
        class_id: int = CURSEFORGE_MOD_CLASS,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "gameId": CURSEFORGE_GAME_ID,
            "classId": class_id,
            "searchFilter": query or "",
            "sortField": 2 if query else 6,
            "sortOrder": "desc",
            "index": max(0, offset),
            "pageSize": max(1, min(limit, 50)),
        }
        if minecraft_version:
            params["gameVersion"] = minecraft_version
        if loader in CURSEFORGE_LOADER_TYPES:
            params["modLoaderType"] = CURSEFORGE_LOADER_TYPES[loader]
        data = self._get("/mods/search", params) or []
        hits = [self._normalize_hit(item) for item in data]
        return {"platform": "curseforge", "total": len(hits), "hits": hits, "offset": params["index"]}

    @staticmethod
    def _normalize_hit(item: dict[str, Any]) -> dict[str, Any]:
        authors = item.get("authors") or []
        logo = item.get("logo") or {}
        return {
            "platform": "curseforge",
            "id": str(item.get("id")),
            "slug": item.get("slug"),
            "title": item.get("name"),
            "description": _trim(item.get("summary")),
            "author": authors[0].get("name") if authors else None,
            "downloads": item.get("downloadCount") or 0,
            "follows": 0,
            "icon": logo.get("thumbnailUrl") or logo.get("url"),
            "categories": [category.get("name") for category in item.get("categories") or []],
            "url": (item.get("links") or {}).get("websiteUrl"),
            "game_versions": sorted({entry.get("gameVersion") for entry in item.get("latestFilesIndexes") or [] if entry.get("gameVersion")})[-8:],
            "date_modified": item.get("dateModified"),
        }

    def files(self, mod_id: str, minecraft_version: str | None = None, loader: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"pageSize": 50}
        if minecraft_version:
            params["gameVersion"] = minecraft_version
        if loader in CURSEFORGE_LOADER_TYPES:
            params["modLoaderType"] = CURSEFORGE_LOADER_TYPES[loader]
        data = self._get(f"/mods/{mod_id}/files", params) or []
        return [self.normalize_file(item, mod_id) for item in data]

    def file(self, mod_id: str, file_id: str) -> dict[str, Any]:
        data = self._get(f"/mods/{mod_id}/files/{file_id}")
        if not data:
            raise ModPlatformError("CurseForge 未找到指定文件")
        return self.normalize_file(data, mod_id)

    def mod(self, mod_id: str) -> dict[str, Any]:
        return self._get(f"/mods/{mod_id}") or {}

    @staticmethod
    def fallback_url(file_id: str, filename: str) -> str:
        numeric = int(file_id)
        return f"https://mediafilez.forgecdn.net/files/{numeric // 1000}/{numeric % 1000:03d}/{quote(filename)}"

    @classmethod
    def normalize_file(cls, item: dict[str, Any], mod_id: str | None) -> dict[str, Any]:
        filename = item.get("fileName")
        url = item.get("downloadUrl")
        if not url and filename and item.get("id") is not None:
            url = cls.fallback_url(str(item.get("id")), filename)
        dependencies = []
        for entry in item.get("dependencies") or []:
            dependencies.append(
                {
                    "project_id": str(entry.get("modId")),
                    "version_id": None,
                    "dependency_type": "required" if entry.get("relationType") == CURSEFORGE_RELATION_REQUIRED else "optional",
                }
            )
        raw_tags = [str(value) for value in item.get("gameVersions") or [] if value]
        game_versions = [value for value in raw_tags if _MC_VERSION.match(value)]
        loaders = [value.lower() for value in raw_tags if value.lower() in MODRINTH_LOADERS]
        return {
            "platform": "curseforge",
            "project_id": str(mod_id or item.get("modId")),
            "version_id": str(item.get("id")),
            "name": item.get("displayName") or filename,
            "version_number": item.get("displayName") or filename,
            "channel": {1: "release", 2: "beta", 3: "alpha"}.get(item.get("releaseType"), "release"),
            "game_versions": game_versions[:12],
            "loaders": loaders,
            "date": item.get("fileDate"),
            "downloads": item.get("downloadCount") or 0,
            "files": [
                {
                    "url": url,
                    "filename": filename,
                    "size": item.get("fileLength"),
                    "primary": True,
                    "sha1": _sha1_from_hashes(item.get("hashes")),
                }
            ],
            "dependencies": dependencies,
            "unavailable": bool(item.get("isAvailable") is False),
        }


class ModService:
    def __init__(self, config: Config, tasks: TaskManager, bus: EventBus, instances: Any = None) -> None:
        self.config = config
        self.tasks = tasks
        self.bus = bus
        self.instances = instances
        self._title_cache: dict[str, str] = {}
        self._lock = threading.Lock()

    # ---------- 目录 ----------

    def mods_directory(self, instance_id: str | None = None) -> Path:
        if self.instances is not None and instance_id:
            instance = self.instances.get(instance_id)
            if instance:
                return self.instances.mods_directory_of(instance)
        return self.config.mods_directory

    # ---------- 平台 ----------

    def platform_status(self) -> list[dict[str, Any]]:
        return [
            {"id": "modrinth", "name": "Modrinth", "available": True, "requires_key": False},
            {
                "id": "curseforge",
                "name": "CurseForge",
                "available": bool((self.config.get("curseforge_api_key") or "").strip()),
                "requires_key": True,
            },
        ]

    def _clients(self) -> tuple[ModrinthClient, CurseForgeClient]:
        timeout = int(self.config.get("download_timeout", 60) or 60)
        return ModrinthClient(timeout=20), CurseForgeClient(self.config.get("curseforge_api_key") or "", timeout=20)

    # ---------- 搜索 ----------

    def search(
        self,
        platform: str,
        query: str,
        minecraft_version: str | None = None,
        loader: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        modrinth, curseforge = self._clients()
        if platform == "all":
            return self._aggregate_search(query, minecraft_version, loader, limit, offset)
        if platform == "curseforge":
            return curseforge.search(query, minecraft_version, loader, limit, offset)
        return modrinth.search(query, minecraft_version, loader, limit, offset)

    def _aggregate_search(
        self,
        query: str,
        minecraft_version: str | None,
        loader: str | None,
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
                    query,
                    minecraft_version,
                    loader,
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
            "total": len(hits),
            "hits": hits[: max(1, min(limit, 50))],
            "offset": max(0, offset),
            "warnings": warnings,
        }

    def _search_platform(
        self,
        platform: str,
        query: str,
        minecraft_version: str | None,
        loader: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        modrinth, curseforge = self._clients()
        if platform == "curseforge":
            return curseforge.search(query, minecraft_version, loader, limit, offset)
        return modrinth.search(query, minecraft_version, loader, limit, offset)

    def versions(self, platform: str, project_id: str, minecraft_version: str | None = None, loader: str | None = None) -> dict[str, Any]:
        modrinth, curseforge = self._clients()
        if platform == "curseforge":
            items = curseforge.files(project_id, minecraft_version, loader)
        else:
            items = modrinth.versions(project_id, minecraft_version, loader)
        return {"platform": platform, "project_id": project_id, "versions": items}

    def inspect_dependencies(
        self,
        platform: str,
        project_id: str,
        version_id: str | None = None,
        minecraft_version: str | None = None,
        loader: str | None = None,
        instance_id: str | None = None,
    ) -> dict[str, Any]:
        version = self._resolve_version(
            platform,
            project_id,
            version_id,
            minecraft_version,
            loader,
        )
        installed = self._installed_mod_ids(self.mods_directory(instance_id))
        return {
            "platform": platform,
            "project_id": project_id,
            "version_id": version.get("version_id"),
            "version_number": version.get("version_number"),
            "dependencies": self._dependency_details(version, installed),
        }

    # ---------- 安装 ----------

    def install(
        self,
        platform: str,
        project_id: str,
        version_id: str | None = None,
        minecraft_version: str | None = None,
        loader: str | None = None,
        with_dependencies: bool = False,
        enabled: bool = True,
        instance_id: str | None = None,
        dependency_project_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        task = self.tasks.create("download", f"准备下载模组 #{project_id}")

        def worker() -> None:
            try:
                version = self._resolve_version(
                    platform,
                    project_id,
                    version_id,
                    minecraft_version,
                    loader,
                )
                title = self._project_title(platform, project_id)
                target_dir = self.mods_directory(instance_id)
                self.tasks.update(
                    task.id,
                    title=f"下载 {title} {version.get('version_number') or ''}".strip(),
                    message="已获取下载信息，开始下载",
                    force=True,
                )
                result = self._install_version(
                    version,
                    title,
                    with_dependencies,
                    enabled,
                    depth=0,
                    visited=set(),
                    target_dir=target_dir,
                    existing_task=task,
                    finish_task=False,
                )
                selected_dependencies = {
                    str(project_id)
                    for project_id in (dependency_project_ids or [])
                    if str(project_id).strip()
                }
                children = list(result.get("children") or [])
                installed = self._installed_mod_ids(target_dir) | {
                    str(version.get("project_id") or "").lower()
                }
                for dependency in version.get("dependencies") or []:
                    dependency_project = str(dependency.get("project_id") or "")
                    if (
                        not dependency_project
                        or dependency_project not in selected_dependencies
                        or dependency_project.lower() in installed
                    ):
                        continue
                    try:
                        child_version = self._resolve_dependency(platform, dependency, version)
                        if child_version is None:
                            raise ModPlatformError("没有找到兼容的前置版本")
                        child_title = self._project_title(
                            child_version.get("platform") or platform,
                            dependency_project,
                        )
                        child = self._install_version(
                            child_version,
                            child_title,
                            False,
                            enabled,
                            depth=1,
                            visited=set(),
                            target_dir=target_dir,
                        )
                        children.append(child)
                        installed.add(dependency_project.lower())
                    except Exception as error:
                        children.append(
                            {
                                "file": None,
                                "error": str(error),
                                "project_id": dependency_project,
                                "skipped": True,
                                "dependencies": [],
                                "children": [],
                            }
                        )
                result["children"] = children
                self.tasks.finish(
                    task.id,
                    {"project_id": project_id, "version": version, **result},
                    f"已下载 {title}",
                )
            except Exception as error:
                self.tasks.fail(task.id, str(error))
                self.bus.log(f"模组 #{project_id} 下载失败: {error}", source="mods", level="error")

        threading.Thread(target=worker, daemon=True).start()
        return task.snapshot()

    def _resolve_version(
        self,
        platform: str,
        project_id: str,
        version_id: str | None,
        minecraft_version: str | None,
        loader: str | None,
    ) -> dict[str, Any]:
        modrinth, curseforge = self._clients()
        if platform == "curseforge":
            if version_id:
                return curseforge.file(project_id, version_id)
            files = curseforge.files(project_id, minecraft_version, loader)
            if not files:
                raise ModPlatformError("没有匹配当前版本与加载器的 CurseForge 文件")
            return files[0]
        if version_id:
            return modrinth.version(version_id)
        versions = modrinth.versions(project_id, minecraft_version, loader)
        if not versions:
            raise ModPlatformError("没有匹配当前版本与加载器的 Modrinth 版本")
        return versions[0]

    def _project_title(self, platform: str, project_id: str) -> str:
        if platform == "curseforge":
            key = f"cf:{project_id}"
            with self._lock:
                if key in self._title_cache:
                    return self._title_cache[key]
            try:
                data = self._clients()[1].mod(project_id)
                title = data.get("name") or f"CurseForge #{project_id}"
            except Exception:
                title = f"CurseForge #{project_id}"
        else:
            key = f"mr:{project_id}"
            with self._lock:
                if key in self._title_cache:
                    return self._title_cache[key]
            try:
                title = self._clients()[0].projects([project_id]).get(project_id) or f"Modrinth #{project_id}"
            except Exception:
                title = f"Modrinth #{project_id}"
        with self._lock:
            self._title_cache[key] = title
        return title

    def _install_version(
        self,
        version: dict[str, Any],
        title: str,
        with_dependencies: bool,
        enabled: bool,
        depth: int,
        visited: set[str],
        target_dir: Path,
        existing_task: Any = None,
        finish_task: bool = True,
    ) -> dict[str, Any]:
        signature = f"{version.get('platform')}:{version.get('version_id')}"
        if signature in visited:
            return {"file": None, "skipped": True, "dependencies": [], "children": []}
        visited.add(signature)

        task = existing_task or self.tasks.create(
            "download",
            f"下载 {title} {version.get('version_number') or ''}".strip(),
        )
        self.bus.log(f"开始下载 {title}（{version.get('platform')}）", source="mods")

        installed_ids = self._installed_mod_ids(target_dir)
        dependencies = self._dependency_hints(version, installed_ids)
        children: list[dict[str, Any]] = []
        try:
            primary = self._primary_file(version)
            if not primary:
                raise ModPlatformError("该版本没有可下载文件")
            result = download_file(
                primary["url"],
                target_dir,
                primary["filename"],
                expected_size=primary.get("size"),
                sha1=primary.get("sha1"),
                retries=int(self.config.get("download_retries", 3) or 3),
                timeout=int(self.config.get("download_timeout", 60) or 60),
                tasks=self.tasks,
                task_id=task.id,
                label=f"下载 {title}",
            )
            final_path = Path(result.path)
            if not enabled and not final_path.name.lower().endswith(".disabled"):
                disabled = final_path.with_name(final_path.name + ".disabled")
                final_path.replace(disabled)
                final_path = disabled
            self.bus.publish(make_event("mods.downloaded", platform=version.get("platform"), project_id=version.get("project_id"), path=str(final_path)))

            if with_dependencies and depth < 2:
                for dependency in version.get("dependencies") or []:
                    if dependency.get("dependency_type") != "required":
                        continue
                    try:
                        child_version = self._resolve_dependency(version.get("platform"), dependency, version)
                        if child_version is None:
                            continue
                        child_title = self._project_title(version.get("platform"), dependency.get("project_id"))
                        children.append(
                            self._install_version(child_version, child_title, True, enabled, depth + 1, visited, target_dir)
                        )
                    except Exception as error:
                        children.append({"file": None, "error": str(error), "skipped": True, "dependencies": []})

            if finish_task:
                self.tasks.finish(
                    task.id,
                    {"file": str(final_path), "dependencies": dependencies, "children": children},
                    f"已下载到 {final_path.name}",
                )
            self.bus.log(f"{title} 已保存为 {final_path.name}", source="mods")
            self.bus.publish(make_event("mods.changed"))
            return {"file": str(final_path), "skipped": bool(result.skipped), "dependencies": dependencies, "children": children}
        except Exception as error:
            self.tasks.fail(task.id, str(error))
            self.bus.log(f"{title} 下载失败: {error}", source="mods", level="error")
            raise

    def _primary_file(self, version: dict[str, Any]) -> dict[str, Any] | None:
        files = [item for item in version.get("files") or [] if item.get("url")]
        for item in files:
            if item.get("primary"):
                return item
        return files[0] if files else None

    def _resolve_dependency(self, platform: str | None, dependency: dict[str, Any], parent: dict[str, Any]) -> dict[str, Any] | None:
        project_id = dependency.get("project_id")
        if not project_id:
            return None
        modrinth, curseforge = self._clients()
        if platform == "curseforge":
            files = curseforge.files(str(project_id), None, None)
            return files[0] if files else None
        if dependency.get("version_id"):
            return modrinth.version(dependency["version_id"])
        loaders = [value for value in parent.get("loaders") or [] if value in MODRINTH_LOADERS]
        game_versions = parent.get("game_versions") or []
        versions = modrinth.versions(str(project_id), game_versions[0] if game_versions else None, loaders[0] if loaders else None)
        return versions[0] if versions else None

    def _dependency_hints(self, version: dict[str, Any], installed_ids: set[str]) -> list[dict[str, Any]]:
        entries = [item for item in version.get("dependencies") or [] if item.get("dependency_type") == "required"]
        return self._dependency_details(version, installed_ids, entries=entries)

    def _dependency_details(
        self,
        version: dict[str, Any],
        installed_ids: set[str],
        entries: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        entries = entries if entries is not None else [
            item
            for item in version.get("dependencies") or []
            if item.get("dependency_type") in {"required", "optional"}
        ]
        if not entries:
            return []
        hints: list[dict[str, Any]] = []
        platform = version.get("platform") or "modrinth"
        titles: dict[str, str] = {}
        if platform == "modrinth":
            try:
                titles = self._clients()[0].projects([str(item.get("project_id")) for item in entries if item.get("project_id")])
            except Exception:
                titles = {}
        seen: set[str] = set()
        for item in entries:
            project_id = str(item.get("project_id") or "")
            if not project_id or project_id in seen:
                continue
            seen.add(project_id)
            title = titles.get(project_id) or f"{platform} #{project_id}"
            hints.append(
                {
                    "project_id": project_id,
                    "version_id": item.get("version_id"),
                    "name": title,
                    "dependency_type": item.get("dependency_type") or "optional",
                    "installed": project_id.lower() in installed_ids or title.lower().replace(" ", "-") in installed_ids,
                    "platform": platform,
                }
            )
        return hints

    def _installed_mod_ids(self, directory: Path | None = None) -> set[str]:
        try:
            report = scan_mods(directory or self.config.mods_directory)
        except Exception:
            return set()
        ids: set[str] = set()
        for mod in report.get("mods", []):
            if mod.get("mod_id"):
                ids.add(mod["mod_id"].lower())
        return ids

    # ---------- 本地管理 ----------

    def scan(self, instance_id: str | None = None) -> dict[str, Any]:
        return scan_mods(self.mods_directory(instance_id))

    def toggle(self, file_name: str, instance_id: str | None = None) -> dict[str, Any]:
        directory = self.mods_directory(instance_id)
        source = directory / file_name
        if not source.is_file():
            raise ModPlatformError("文件不存在")
        if source.name.lower().endswith(".disabled"):
            target = directory / source.name[: -len(".disabled")]
        else:
            target = directory / (source.name + ".disabled")
        if target.exists():
            raise ModPlatformError(f"{target.name} 已存在，无法切换")
        source.replace(target)
        self.bus.publish(make_event("mods.changed", instance_id=instance_id))
        return {"file": target.name, "enabled": not target.name.lower().endswith(".disabled")}

    def delete(self, file_name: str, instance_id: str | None = None) -> dict[str, Any]:
        directory = self.mods_directory(instance_id)
        candidate = directory / file_name
        if not candidate.is_file():
            raise ModPlatformError("文件不存在")
        resolved = candidate.resolve()
        if resolved.parent != directory.resolve():
            raise ModPlatformError("非法的文件路径")
        resolved.unlink()
        self.bus.publish(make_event("mods.changed", instance_id=instance_id))
        return {"deleted": resolved.name}
