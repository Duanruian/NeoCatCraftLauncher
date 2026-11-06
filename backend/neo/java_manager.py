from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import threading
import time
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx

from .config import Config
from .events import EventBus, make_event
from .tasks import TaskManager

USER_AGENT = "NeoCatCraftLauncher/0.2 (+https://github.com/neocatcraft)"

JAVA_MAJOR_BY_MC: list[tuple[str, int]] = [
    ("1.21", 21),
    ("1.20.5", 21),
    ("1.20", 17),
    ("1.19", 17),
    ("1.18", 17),
    ("1.17", 16),
    ("1.16", 8),
    ("1.15", 8),
    ("1.14", 8),
    ("1.13", 8),
    ("1.12", 8),
    ("1.11", 8),
    ("1.10", 8),
    ("1.9", 8),
    ("1.8", 8),
    ("1.7", 8),
]

JAVA_LABELS = {8: "Java 8", 11: "Java 11", 16: "Java 16", 17: "Java 17", 21: "Java 21", 22: "Java 22", 23: "Java 23", 25: "Java 25"}

AVAILABLE_MAJORS = [8, 11, 16, 17, 21, 25]

DOWNLOAD_PROGRESS_END = 85
VERIFY_PROGRESS_END = 90
EXTRACT_PROGRESS_END = 99
DOWNLOAD_CHUNK_SIZE = 256 * 1024


class JavaError(RuntimeError):
    pass


def _platform_params() -> dict[str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        os_name = "windows"
    elif system == "darwin":
        os_name = "macos"
    else:
        os_name = "linux"
    if machine in ("x86_64", "amd64", "x64"):
        arch = "x64"
    elif machine in ("aarch64", "arm64"):
        arch = "aarch64"
    else:
        arch = "x86"
    return {"os": os_name, "arch": arch}


def java_major_for_minecraft(mc_version: str) -> int:
    value = (mc_version or "").strip().lower()
    for prefix, major in JAVA_MAJOR_BY_MC:
        if value.startswith(prefix):
            return major
    return 21


def _read_release(java_home: Path) -> dict[str, str]:
    release = java_home / "release"
    data: dict[str, str] = {}
    if not release.is_file():
        return data
    try:
        for line in release.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            data[key.strip()] = value.strip().strip('"')
    except Exception:
        return {}
    return data


def _java_home_of(binary: Path) -> Path:
    current = binary.resolve()
    if current.name.lower() in ("java.exe", "javaw.exe", "java"):
        return current.parent.parent
    return current


def _binary_of(java_home: Path) -> str:
    if os.name == "nt":
        candidate = java_home / "bin" / "java.exe"
        if candidate.is_file():
            return str(candidate)
        candidate = java_home / "bin" / "javaw.exe"
        if candidate.is_file():
            return str(candidate)
    candidate = java_home / "bin" / "java"
    return str(candidate) if candidate.is_file() else ""


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


class JavaManager:
    def __init__(self, config: Config, tasks: TaskManager, bus: EventBus) -> None:
        self.config = config
        self.tasks = tasks
        self.bus = bus
        self._system_cache: tuple[float, list[dict[str, Any]]] | None = None
        self._lock = threading.Lock()

    # ---------- 枚举 ----------

    def managed(self) -> list[dict[str, Any]]:
        root = self.config.javas_directory
        items: list[dict[str, Any]] = []
        if not root.is_dir():
            return items
        try:
            children = sorted(root.iterdir())
        except OSError as error:
            self.bus.log(f"无法读取 Java 运行时目录: {error}", source="java", level="error")
            return items
        for child in children:
            try:
                if not child.is_dir():
                    continue
                home = child
                nested = [entry for entry in child.iterdir() if entry.is_dir() and (entry / "bin").is_dir()]
                for entry in nested:
                    if (entry / "bin").is_dir():
                        home = entry
                        break
                binary = _binary_of(home)
                if not binary:
                    continue
                release = _read_release(home)
                version = release.get("JAVA_VERSION") or release.get("JAVA_RUNTIME_VERSION") or ""
                items.append(
                    {
                        "path": binary,
                        "home": str(home),
                        "name": release.get("IMPLEMENTOR") or "Zulu",
                        "version": version,
                        "major": _major_of(version),
                        "managed": True,
                        "vendor": "Azul Zulu",
                        "source": "managed",
                        "label": f"{JAVA_LABELS.get(_major_of(version), 'Java')} · Zulu",
                    }
                )
            except OSError as error:
                self.bus.log(f"跳过无法访问的 Java 运行时 {child}: {error}", source="java", level="error")
                continue
        return items

    def system(self, force: bool = False) -> list[dict[str, Any]]:
        now = time.time()
        if not force and self._system_cache and now - self._system_cache[0] < 300:
            return self._system_cache[1]
        found: list[dict[str, Any]] = []
        try:
            import minecraft_launcher_lib as mll

            for info in mll.java_utils.find_system_java_versions_information():
                binary = info.get("java_path") or info.get("javaw_path")
                if not binary:
                    continue
                version = str(info.get("version") or "")
                found.append(
                    {
                        "path": binary,
                        "home": str(_java_home_of(Path(binary))),
                        "name": info.get("name") or "系统 Java",
                        "version": version,
                        "major": _major_of(version),
                        "managed": False,
                        "vendor": info.get("name") or "System",
                        "source": "system",
                        "label": f"{info.get('name') or 'Java'} {version}".strip(),
                    }
                )
        except Exception:
            pass
        runtime_root = self.config.minecraft_directory / "runtime"
        seen = {str(Path(item["path"]).resolve()).lower() for item in found if item.get("path")}
        if runtime_root.is_dir():
            patterns = ("**/bin/java.exe", "**/bin/java") if os.name == "nt" else ("**/bin/java",)
            for pattern in patterns:
                try:
                    candidates = runtime_root.glob(pattern)
                    for binary in candidates:
                        if not _is_file(binary):
                            continue
                        key = str(binary.resolve()).lower()
                        if key in seen:
                            continue
                        seen.add(key)
                        home = _java_home_of(binary)
                        release = _read_release(home)
                        version = release.get("JAVA_VERSION") or release.get("JAVA_RUNTIME_VERSION") or ""
                        major = _major_of(version)
                        found.append(
                            {
                                "path": str(binary),
                                "home": str(home),
                                "name": "Minecraft 内置 Java",
                                "version": version,
                                "major": major,
                                "managed": False,
                                "vendor": release.get("IMPLEMENTOR") or "Minecraft Runtime",
                                "source": "minecraft-runtime",
                                "label": f"Minecraft Runtime · Java {major}",
                            }
                        )
                except OSError:
                    continue
        self._system_cache = (now, found)
        return found

    def all_java(self, force: bool = False) -> list[dict[str, Any]]:
        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        configured = (self.config.get("java_path") or "").strip()
        if configured and _is_file(Path(configured)):
            version = _version_from_binary(Path(configured))
            merged.append(
                {
                    "path": configured,
                    "home": str(_java_home_of(Path(configured))),
                    "name": "手动指定",
                    "version": version,
                    "major": _major_of(version),
                    "managed": False,
                    "vendor": "自定义",
                    "source": "custom",
                    "label": f"自定义 Java {version}".strip(),
                }
            )
            seen.add(str(Path(configured).resolve()).lower())
        for item in self.managed() + self.system(force):
            key = str(Path(item["path"]).resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        merged.sort(key=lambda item: (not item.get("managed"), -int(item.get("major") or 0)))
        return merged

    # ---------- 解析 ----------

    def resolve(self, instance: dict[str, Any] | None = None) -> dict[str, Any] | None:
        instance_java = ((instance or {}).get("java_path") or "").strip()
        if instance_java and _is_file(Path(instance_java)):
            version = _version_from_binary(Path(instance_java))
            return {
                "path": instance_java,
                "major": _major_of(version),
                "version": version,
                "label": f"实例指定 Java {version}".strip(),
                "source": "instance",
            }

        candidates = self.all_java()
        mc_version = str((instance or {}).get("mc_version") or "")
        if not mc_version:
            configured = (self.config.get("java_path") or "").strip()
            if configured and _is_file(Path(configured)):
                return {
                    "path": configured,
                    "major": _major_of(_version_from_binary(Path(configured))),
                    "label": "全局默认 Java",
                    "source": "global",
                }
            return candidates[0] if candidates else None

        required = java_major_for_minecraft(mc_version)
        exact = [item for item in candidates if int(item.get("major") or 0) == required]
        if exact:
            preferred = next((item for item in exact if item.get("managed")), exact[0])
            return {**preferred, "required": required}
        higher = sorted(
            [item for item in candidates if int(item.get("major") or 0) >= required],
            key=lambda item: int(item.get("major") or 0),
        )
        if higher:
            return {**higher[0], "required": required, "mismatch": True}
        configured = (self.config.get("java_path") or "").strip()
        if configured and _is_file(Path(configured)):
            return {
                "path": configured,
                "major": _major_of(_version_from_binary(Path(configured))),
                "label": "全局默认 Java",
                "source": "global",
                "required": required,
            }
        return None

    def for_minecraft(self, mc_version: str) -> dict[str, Any] | None:
        return self.resolve({"mc_version": mc_version})

    def resolve_for_install(self, mc_version: str) -> str:
        required = java_major_for_minecraft(mc_version)
        resolved = self.resolve({"mc_version": mc_version})
        if resolved and resolved.get("path") and not resolved.get("mismatch"):
            return str(resolved["path"])
        if not bool(self.config.get("auto_download_java", True)):
            raise JavaError(
                f"加载器安装需要 Java {required}，请先安装匹配的 Java 运行时"
            )

        active_install = next(
            (
                item
                for item in self.tasks.list()
                if item.get("kind") == "java"
                and item.get("state") == "running"
                and f"Java {required}" in str(item.get("title") or "")
            ),
            None,
        )
        task = active_install or self.install(required)
        deadline = time.time() + 15 * 60
        while time.time() < deadline:
            task_id = task.get("id") if isinstance(task, dict) else task.id
            current = self.tasks.get(task_id)
            if current is not None and current.state == "done":
                break
            if current is not None and current.state == "error":
                raise JavaError(current.error or f"Java {required} 安装失败")
            time.sleep(0.25)
        else:
            raise JavaError(f"等待 Java {required} 安装完成超时")

        resolved = self.resolve({"mc_version": mc_version})
        if resolved and resolved.get("path") and not resolved.get("mismatch"):
            return str(resolved["path"])
        raise JavaError(f"无法准备加载器安装所需的 Java {required}")

    # ---------- 安装 ----------

    def resolve_package(self, major: int) -> dict[str, Any]:
        api = (self.config.get("zulu_api") or "").strip() or "https://api.azul.com/metadata/v1/zulu"
        params: dict[str, Any] = {
            "java_version": major,
            "archive_type": "zip",
            "java_package_type": "jdk",
            "javafx_bundled": "false",
            "latest": "true",
            "release_status": "ga",
            "page_size": 20,
            **_platform_params(),
        }
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        attempts = [
            {**params, "availability_types": "CA"},
            params,
        ]
        last_error: Exception | None = None
        for query in attempts:
            try:
                with httpx.Client(timeout=25, follow_redirects=True, headers=headers) as client:
                    response = client.get(f"{api.rstrip('/')}/packages/", params=query)
                if response.status_code == 406:
                    continue
                if response.status_code != 200:
                    last_error = JavaError(f"Azul 接口返回 HTTP {response.status_code}")
                    continue
                payload = response.json()
                if not isinstance(payload, list):
                    last_error = JavaError("Azul 接口返回了意外的数据格式")
                    continue
                for item in payload:
                    url = item.get("download_url") or ""
                    if url.lower().endswith(".zip"):
                        return {
                            "url": url,
                            "name": item.get("name") or f"zulu-{major}.zip",
                            "size": item.get("size") or 0,
                            "sha256": (item.get("sha256_hash") or "").lower(),
                            "major": major,
                            "version": item.get("openjdk_version") or ".".join(str(v) for v in (item.get("java_version") or [])),
                        }
                last_error = JavaError(f"没有找到 Java {major} 的 Zulu 安装包")
            except Exception as error:
                last_error = error
        raise JavaError(f"获取 Zulu Java {major} 失败: {last_error}")

    def install(self, major: int) -> dict[str, Any]:
        major = int(major)
        if major <= 0:
            raise JavaError("无效的 Java 版本")
        task = self.tasks.create("java", f"安装 Zulu Java {major}")
        self.bus.log(f"开始从 Azul 下载 Zulu Java {major}", source="java")

        def worker() -> None:
            temp_dir: Path | None = None
            try:
                package = self.resolve_package(major)
                self.tasks.progress(task.id, message=f"解析安装包 {package['name']}")
                root = self.config.javas_directory
                target = root / f"zulu-{major}"
                if target.exists():
                    target = root / f"zulu-{major}-{int(time.time())}"
                with _temporary_directory(root) as temp_dir:
                    archive = temp_dir / package["name"]
                    self._download(package, archive, task.id)
                    self.tasks.update(
                        task.id,
                        force=True,
                        progress=VERIFY_PROGRESS_END,
                        total=100,
                        message="安装包校验完成，正在解压",
                    )
                    extract_dir = temp_dir / "extract"
                    self._extract_zip(archive, extract_dir, task.id)
                    entries = [entry for entry in extract_dir.iterdir() if entry.is_dir()]
                    source = next((entry for entry in entries if _binary_of(entry)), None)
                    if source is None:
                        source = entries[0] if len(entries) == 1 else extract_dir
                    if not _binary_of(source):
                        raise JavaError("解压后未找到 java 可执行文件")
                    self.tasks.progress(task.id, progress=EXTRACT_PROGRESS_END, message="正在安装 Java 文件")
                    if target.exists():
                        shutil.rmtree(target, ignore_errors=True)
                    shutil.move(str(source), str(target))
                binary = _binary_of(target)
                if not binary:
                    raise JavaError("解压后未找到 java 可执行文件")
                release = _read_release(target)
                version = release.get("JAVA_VERSION") or package.get("version") or str(major)
                self._system_cache = None
                self.tasks.finish(
                    task.id,
                    {"path": binary, "version": version, "major": major},
                    f"Zulu Java {major} 安装完成",
                )
                self.bus.publish(make_event("java.changed"))
                self.bus.log(f"Zulu Java {major} 已安装到 {target}", source="java")
            except Exception as error:
                self.tasks.fail(task.id, str(error))
                self.bus.log(f"Zulu Java {major} 安装失败: {error}", source="java", level="error")

        threading.Thread(target=worker, daemon=True).start()
        return task.snapshot()

    def ensure(self, mc_version: str, instance: dict[str, Any] | None = None) -> dict[str, Any] | None:
        resolved = self.resolve(instance)
        if resolved and not resolved.get("mismatch"):
            return resolved
        if not bool(self.config.get("auto_download_java", True)):
            return resolved
        required = java_major_for_minecraft(mc_version)
        if any(int(item.get("major") or 0) == required for item in self.managed()):
            return self.resolve(instance)
        self.install(required)
        return resolved

    # ---------- 内部 ----------

    def _download(self, package: dict[str, Any], target: Path, task_id: str) -> int:
        expected_size = max(0, int(package.get("size") or 0))
        expected_sha256 = str(package.get("sha256") or "").strip().lower()
        self.tasks.progress(
            task_id,
            progress=0,
            total=100,
            message=f"下载 {package['name']}",
        )
        headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
        last_error: Exception | None = None
        retries = int(self.config.get("download_retries", 3) or 3)
        timeout = int(self.config.get("download_timeout", 60) or 60)
        for attempt in range(1, max(1, retries) + 1):
            part = target.with_suffix(target.suffix + ".part")
            try:
                with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
                    with client.stream("GET", package["url"]) as response:
                        response.raise_for_status()
                        content_length = _content_length(response)
                        declared_sizes = {
                            size for size in (expected_size, content_length) if size > 0
                        }
                        if len(declared_sizes) > 1:
                            raise JavaError(
                                f"安装包大小信息不一致（接口 {expected_size}，服务器 {content_length}）"
                            )
                        total = next(iter(declared_sizes), 0)
                        written = 0
                        digest = hashlib.sha256()
                        with part.open("wb") as handle:
                            for chunk in response.iter_raw(DOWNLOAD_CHUNK_SIZE):
                                if not chunk:
                                    continue
                                handle.write(chunk)
                                digest.update(chunk)
                                written += len(chunk)
                                progress = (
                                    min(
                                        DOWNLOAD_PROGRESS_END,
                                        int(written * DOWNLOAD_PROGRESS_END / total),
                                    )
                                    if total
                                    else 0
                                )
                                self.tasks.progress(
                                    task_id,
                                    progress=progress,
                                    total=100,
                                    message=_download_message(package["name"], written, total),
                                )
                                # Servers can report the full Content-Length while keeping the
                                # connection open. Stop after the declared file is complete
                                # instead of waiting indefinitely for another chunk.
                                if total and written >= total:
                                    break
                if total and written != total:
                    raise JavaError(f"安装包下载不完整（期望 {total} 字节，实际 {written} 字节）")
                if expected_sha256:
                    self.tasks.update(
                        task_id,
                        force=True,
                        progress=DOWNLOAD_PROGRESS_END,
                        total=100,
                        message="下载完成，正在校验 SHA-256",
                    )
                    if digest.hexdigest() != expected_sha256:
                        raise JavaError("Zulu 安装包校验失败（SHA-256 不匹配）")
                part.replace(target)
                return written
            except Exception as error:
                last_error = error
                try:
                    part.unlink(missing_ok=True)
                except Exception:
                    pass
                if attempt < retries:
                    self.tasks.progress(
                        task_id,
                        progress=0,
                        total=100,
                        message=f"下载中断，正在进行第 {attempt + 1} 次尝试",
                    )
                    time.sleep(min(1.5 * attempt, 6))
        raise JavaError(f"下载失败: {last_error}")

    def _extract_zip(self, archive: Path, extract_dir: Path, task_id: str) -> None:
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            total_bytes = sum(info.file_size for info in members)
            extracted_bytes = 0
            last_report = 0.0
            for index, info in enumerate(members, start=1):
                bundle.extract(info, path=extract_dir)
                if not info.is_dir():
                    extracted_bytes += info.file_size
                now = time.monotonic()
                if index == len(members) or now - last_report >= 0.1:
                    progress = (
                        VERIFY_PROGRESS_END
                        + int(
                            (EXTRACT_PROGRESS_END - VERIFY_PROGRESS_END)
                            * extracted_bytes
                            / total_bytes
                        )
                        if total_bytes
                        else VERIFY_PROGRESS_END
                    )
                    self.tasks.progress(
                        task_id,
                        progress=min(EXTRACT_PROGRESS_END, progress),
                        total=100,
                        message=f"正在解压安装包（{index}/{len(members)}）",
                    )
                    last_report = now


def _content_length(response: httpx.Response) -> int:
    try:
        return max(0, int(response.headers.get("Content-Length") or 0))
    except (TypeError, ValueError):
        return 0


@contextmanager
def _temporary_directory(parent: Path) -> Iterator[Path]:
    parent.mkdir(parents=True, exist_ok=True)
    directory: Path | None = None
    for _ in range(100):
        candidate = parent / f"neo-java-{uuid.uuid4().hex}"
        try:
            # Path.mkdir inherits the parent directory's Windows ACL. The bundled
            # Python's tempfile.mkdtemp can create inaccessible 0700 directories.
            candidate.mkdir()
            directory = candidate
            break
        except FileExistsError:
            continue
    if directory is None:
        raise JavaError("无法创建 Java 安装临时目录")
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _format_bytes(value: int) -> str:
    size = max(0, int(value or 0))
    if size < 1024:
        return f"{size} B"
    if size < 1024**2:
        return f"{size / 1024:.1f} KB"
    if size < 1024**3:
        return f"{size / 1024**2:.1f} MB"
    return f"{size / 1024**3:.2f} GB"


def _download_message(name: str, written: int, total: int) -> str:
    if total:
        return f"下载 {name} · {_format_bytes(written)} / {_format_bytes(total)}"
    return f"下载 {name} · {_format_bytes(written)}"


def _major_of(version: str) -> int:
    text = (version or "").strip()
    if not text:
        return 0
    match = re.match(r"^(\d+)", text)
    if not match:
        return 0
    major = int(match.group(1))
    if major == 1:
        parts = text.split(".")
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1])
        return 1
    return major


def _version_from_binary(binary: Path) -> str:
    home = _java_home_of(binary)
    release = _read_release(home)
    if release.get("JAVA_VERSION"):
        return release["JAVA_VERSION"]
    version = release.get("JAVA_RUNTIME_VERSION") or ""
    if version:
        return version
    try:
        import subprocess

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        output = subprocess.run(
            [str(binary), "-version"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=creationflags,
        )
        text = (output.stderr or "") + (output.stdout or "")
        match = re.search(r'version "([^"]+)"', text)
        if match:
            return match.group(1)
    except Exception:
        pass
    return ""


JavaProgressCallback = Callable[[int, int], None]
