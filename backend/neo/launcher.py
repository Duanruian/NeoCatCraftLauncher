from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Any

import minecraft_launcher_lib as mll

from .auth import AuthService
from .config import APP_NAME, APP_VERSION, LEGACY_JVM_ARGS, SAFE_JVM_ARGS, Config
from .events import EventBus, make_event
from .instances import InstanceError, InstanceManager
from .java_manager import JavaError, JavaManager, java_major_for_minecraft
from .tasks import TaskManager

APRIL_FOOLS_VERSION_IDS = {
    "15w14a",
    "1.rv-pre1",
    "3d shareware v1.34",
    "20w14∞",
    "22w13oneblockatatime",
    "23w13a_or_b",
    "24w14potato",
    "25w14craftmine",
}

def classify_version(version_id: str, version_type: str, release_time: Any = None) -> str:
    kind = str(version_type or "").strip().lower()
    identifier = str(version_id or "").strip().lower()
    if kind in {"old_alpha", "old_beta", "alpha", "beta"}:
        return "ancient"
    if kind == "release":
        return "release"
    released_on_april_first = str(release_time or "")[5:10] == "04-01"
    if identifier in APRIL_FOOLS_VERSION_IDS or released_on_april_first:
        return "april_fools"
    return "snapshot"


def guess_loader(version_id: str) -> str:
    lowered = (version_id or "").lower()
    if lowered.startswith("fabric-loader-") or "-fabric-" in lowered:
        return "fabric"
    if lowered.startswith("quilt-loader-") or "-quilt-" in lowered:
        return "quilt"
    if lowered.startswith("neoforge-") or "-neoforge-" in lowered:
        return "neoforge"
    if "forge" in lowered:
        return "forge"
    return "vanilla"


def parse_loader_version(loader: str, version_id: str, mc_version: str) -> str:
    value = version_id or ""
    loader = (loader or "").lower()
    patterns = {
        "fabric": rf"^fabric-loader-(.+)-{re.escape(mc_version)}$",
        "quilt": rf"^quilt-loader-(.+)-{re.escape(mc_version)}$",
        "forge": rf"^{re.escape(mc_version)}-forge-(.+)$",
        "neoforge": r"^neoforge-(.+)$",
    }
    pattern = patterns.get(loader)
    if pattern:
        match = re.match(pattern, value)
        if match:
            return match.group(1)
    if loader and loader != "vanilla" and "-" in value:
        return value.rsplit("-", 1)[-1]
    return ""


def install_mod_loader(
    loader: str,
    minecraft_version: str,
    minecraft_directory: str,
    loader_version: str | None,
    callback: dict[str, Any],
    java_path: str,
) -> tuple[str, str]:
    module = mll.mod_loader.get_mod_loader(loader)
    selected_version = loader_version or module.get_latest_loader_version(minecraft_version)
    installed_version = module.install(
        minecraft_version,
        minecraft_directory,
        loader_version=selected_version,
        callback=callback,
        java=java_path,
    )
    if not installed_version:
        installed_version = module.get_installed_version(minecraft_version, selected_version)
    if not installed_version:
        raise RuntimeError(f"{module.get_name()} 安装后没有返回可启动的版本 ID")
    resolved_loader_version = (
        parse_loader_version(loader, str(installed_version), minecraft_version) or selected_version
    )
    return str(installed_version), str(resolved_loader_version)


def _jar_text(archive: zipfile.ZipFile, name: str) -> str:
    try:
        info = archive.getinfo(name)
    except KeyError:
        return ""
    if info.file_size > 4 * 1024 * 1024:
        return ""
    data = archive.read(name)
    return data.decode("utf-8", errors="replace")


def _detect_loader_type(*values: Any) -> str:
    text = " ".join(str(value or "") for value in values).lower()
    if "neoforge" in text or "neoforged" in text:
        return "neoforge"
    if "quilt" in text:
        return "quilt"
    if "fabric" in text:
        return "fabric"
    if "forge" in text:
        return "forge"
    return ""


def inspect_mod_loader_jar(installer_path: str | Path) -> dict[str, Any]:
    path = Path(installer_path).expanduser().resolve()
    if path.suffix.lower() != ".jar" or not path.is_file():
        raise ValueError("请选择有效的模组加载器 .jar 安装包")

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    loader = _detect_loader_type(path.name)
    minecraft_version = ""
    loader_version = ""
    profile: dict[str, Any] = {}
    manifest = ""
    profile_text = ""
    entry_names: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            entry_names = archive.namelist()
            profile_text = _jar_text(archive, "install_profile.json")
            manifest = _jar_text(archive, "META-INF/MANIFEST.MF")
            if profile_text:
                profile = json.loads(profile_text)
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise ValueError(f"无法读取安装包: {error}") from error

    install_data = profile.get("install") if isinstance(profile.get("install"), dict) else {}
    version_info = profile.get("versionInfo") if isinstance(profile.get("versionInfo"), dict) else {}
    minecraft_version = str(
        profile.get("minecraft")
        or install_data.get("minecraft")
        or version_info.get("inheritsFrom")
        or ""
    ).strip()
    raw_version = str(
        profile.get("version")
        or install_data.get("version")
        or version_info.get("id")
        or ""
    ).strip()
    loader = loader or _detect_loader_type(
        profile_text,
        manifest,
        "\n".join(entry_names),
        raw_version,
        profile.get("path"),
        install_data.get("path"),
    )

    if loader == "forge":
        path_spec = str(profile.get("path") or install_data.get("path") or "")
        match = re.search(r"forge:([^:]+)", path_spec)
        if match and not minecraft_version:
            spec_parts = match.group(1).split("-", 1)
            if len(spec_parts) == 2:
                minecraft_version, raw_version = spec_parts
        if minecraft_version and raw_version.startswith(f"{minecraft_version}-"):
            raw_version = raw_version[len(minecraft_version) + 1 :]
        match = re.search(r"-forge-([^/\\]+)$", raw_version, re.IGNORECASE)
        if match:
            raw_version = match.group(1)
    elif loader == "neoforge":
        path_spec = str(profile.get("path") or install_data.get("path") or "")
        match = re.search(r"neoforge:([^:]+)", path_spec, re.IGNORECASE)
        if match:
            raw_version = match.group(1)
        raw_version = re.sub(r"^neoforge-", "", raw_version, flags=re.IGNORECASE)
        if minecraft_version and raw_version.startswith(f"{minecraft_version}-"):
            raw_version = raw_version[len(minecraft_version) + 1 :]
        match = re.search(r"(?:^|-)neoforge-([^/\\]+)$", raw_version, re.IGNORECASE)
        if match:
            raw_version = match.group(1)

    if loader == "forge" and not raw_version:
        match = re.match(
            r"forge-(?P<mc>\d+\.\d+(?:\.\d+)?)-(?P<loader>.+?)(?:-installer)?\.jar$",
            path.name,
            re.IGNORECASE,
        )
        if match:
            minecraft_version = match.group("mc")
            raw_version = match.group("loader")
    elif loader == "neoforge" and not raw_version:
        match = re.match(
            r"neoforge-(?P<loader>.+?)(?:-installer)?\.jar$",
            path.name,
            re.IGNORECASE,
        )
        if match:
            raw_version = match.group("loader")

    if loader == "neoforge" and not minecraft_version:
        match = re.match(r"(\d+)\.(\d+)(?:\.|$)", raw_version)
        if match:
            major, minor = match.groups()
            minecraft_version = f"1.{major}" if minor == "0" else f"1.{major}.{minor}"

    if not loader:
        raise ValueError("无法从安装包识别加载器类型，请确认下载的是 Forge、NeoForge、Fabric 或 Quilt 安装器")
    if not profile and loader not in {"fabric", "quilt"}:
        raise ValueError("该 JAR 不是可用的加载器安装包，缺少 install_profile.json")
    if loader in {"fabric", "quilt"}:
        installer_text = f"{manifest}\n" + "\n".join(entry_names)
        markers = (
            ("fabricmc/installer", "fabricmc.installer")
            if loader == "fabric"
            else ("quiltmc/installer", "quiltmc.installer")
        )
        if not any(marker.lower() in installer_text.lower() for marker in markers):
            raise ValueError(f"该 JAR 不是有效的 {loader.title()} 官方安装器")

    return {
        "path": str(path),
        "file_name": path.name,
        "size": path.stat().st_size,
        "sha256": digest.hexdigest(),
        "loader": loader,
        "minecraft_version": minecraft_version,
        "loader_version": raw_version,
    }


def cache_mod_loader_jar(config: Config, installer_path: str | Path) -> Path:
    details = inspect_mod_loader_jar(installer_path)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(details["file_name"]).name)
    target_dir = config.dir / "loader-installers"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{details['sha256'][:16]}-{safe_name}"
    if not target.is_file():
        shutil.copyfile(details["path"], target)
    return target


def _loader_installer_command(
    loader: str,
    minecraft_version: str,
    loader_version: str,
    minecraft_directory: str,
    installer_path: str,
    java_path: str,
) -> list[str]:
    if loader in {"forge", "neoforge"}:
        return [java_path, "-jar", installer_path, "--installClient", minecraft_directory]
    if loader == "fabric":
        return [
            java_path,
            "-jar",
            installer_path,
            "client",
            "-dir",
            minecraft_directory,
            "-mcversion",
            minecraft_version,
            "-loader",
            loader_version,
            "-noprofile",
            "-snapshot",
        ]
    if loader == "quilt":
        return [
            java_path,
            "-jar",
            installer_path,
            "install",
            "client",
            minecraft_version,
            loader_version,
            f"--install-dir={minecraft_directory}",
            "--no-profile",
        ]
    raise ValueError(f"不支持从 JAR 安装的加载器: {loader}")


def install_mod_loader_from_jar(
    loader: str,
    minecraft_version: str,
    minecraft_directory: str,
    loader_version: str,
    installer_path: str | Path,
    callback: dict[str, Any],
    java_path: str,
) -> tuple[str, str]:
    details = inspect_mod_loader_jar(installer_path)
    detected_loader = str(details.get("loader") or "").lower()
    if loader != detected_loader:
        raise ValueError(
            f"安装包属于 {detected_loader.title()}，与当前选择的 {loader.title()} 不一致"
        )
    detected_mc = str(details.get("minecraft_version") or "")
    if detected_mc and detected_mc != minecraft_version:
        raise ValueError(
            f"安装包适用于 Minecraft {detected_mc}，与实例的 {minecraft_version} 不一致"
        )
    selected_version = (loader_version or str(details.get("loader_version") or "")).strip()
    if not selected_version:
        raise ValueError("无法从该安装包读取加载器版本，请手动填写")

    set_status = callback.get("setStatus", lambda _: None)
    set_status(f"准备 Minecraft {minecraft_version}")
    mll.install.install_minecraft_version(
        minecraft_version,
        minecraft_directory,
        callback=callback,
    )
    if loader in {"forge", "neoforge"} and not mll.vanilla_launcher.do_vanilla_launcher_profiles_exists(
        minecraft_directory
    ):
        mll.vanilla_launcher.create_empty_vanilla_launcher_profiles_file(minecraft_directory)

    command = _loader_installer_command(
        loader,
        minecraft_version,
        selected_version,
        minecraft_directory,
        str(Path(installer_path).resolve()),
        java_path,
    )
    set_status(f"运行 {loader.title()} 官方安装器")
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with tempfile.TemporaryDirectory(prefix="neo-loader-installer-") as tempdir:
        result = subprocess.run(
            command,
            cwd=tempdir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation_flags,
            check=False,
        )
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        tail = "\n".join(output.splitlines()[-18:])
        raise RuntimeError(
            f"官方安装器执行失败（退出码 {result.returncode}）"
            + (f":\n{tail}" if tail else "")
        )

    module = mll.mod_loader.get_mod_loader(loader)
    installed_version = module.get_installed_version(minecraft_version, selected_version)
    version_json = (
        Path(minecraft_directory)
        / "versions"
        / installed_version
        / f"{installed_version}.json"
    )
    if not version_json.is_file():
        raise RuntimeError(
            f"安装器已结束，但没有生成版本 {installed_version}。"
            "请确认 Minecraft 与加载器版本匹配。"
        )
    set_status("检查加载器文件")
    mll.install.install_minecraft_version(
        installed_version,
        minecraft_directory,
        callback=callback,
    )
    return installed_version, parse_loader_version(
        loader, installed_version, minecraft_version
    ) or selected_version


class LauncherService:
    def __init__(
        self,
        config: Config,
        tasks: TaskManager,
        bus: EventBus,
        instances: InstanceManager,
        java: JavaManager,
        auth: AuthService,
    ) -> None:
        self.config = config
        self.tasks = tasks
        self.bus = bus
        self.instances = instances
        self.java = java
        self.auth = auth
        self._version_cache: tuple[float, list[dict[str, Any]]] | None = None
        self._processes: dict[int, subprocess.Popen] = {}
        self._lock = threading.Lock()

    # ---------- 版本 ----------

    def library_version(self) -> str:
        return mll.utils.get_library_version()

    def available_versions(self, force: bool = False) -> list[dict[str, Any]]:
        now = time.time()
        if not force and self._version_cache and now - self._version_cache[0] < 300:
            return self._version_cache[1]
        raw = mll.utils.get_version_list()
        versions = [
            {
                "id": item["id"],
                "type": item["type"],
                "category": classify_version(item["id"], item["type"], item.get("releaseTime")),
                "releaseTime": item["releaseTime"].isoformat() if hasattr(item["releaseTime"], "isoformat") else str(item["releaseTime"]),
            }
            for item in raw
        ]
        self._version_cache = (now, versions)
        return versions

    def installed_versions(self) -> list[dict[str, Any]]:
        directory = str(self.config.minecraft_directory)
        result = []
        for item in mll.utils.get_installed_versions(directory):
            version_id = item["id"]
            release = item.get("releaseTime")
            result.append(
                {
                    "id": version_id,
                    "type": item.get("type", "unknown"),
                    "category": classify_version(version_id, item.get("type", "unknown"), release),
                    "loader": guess_loader(version_id),
                    "releaseTime": release.isoformat() if hasattr(release, "isoformat") else str(release),
                }
            )
        result.sort(key=lambda entry: entry["releaseTime"], reverse=True)
        return result

    def install_version(self, version_id: str, instance_id: str | None = None) -> dict[str, Any]:
        task = self.tasks.create("install", f"安装 Minecraft {version_id}")
        self.bus.log(f"开始安装 Minecraft {version_id}", source="install")

        def worker() -> None:
            try:
                mll.install.install_minecraft_version(
                    version_id,
                    str(self.config.minecraft_directory),
                    callback=self._callback(task.id),
                )
                self.tasks.finish(task.id, {"version": version_id}, "安装完成")
                self._version_cache = None
                if instance_id:
                    self.instances.update(instance_id, {"version_id": version_id, "mc_version": version_id, "loader": "vanilla"})
                self.bus.publish(make_event("versions.changed"))
                self.bus.publish(make_event("instances.changed"))
                self.bus.log(f"Minecraft {version_id} 安装完成", source="install")
            except Exception as error:
                self.tasks.fail(task.id, str(error))
                self.bus.log(f"安装失败: {error}", source="install", level="error")

        threading.Thread(target=worker, daemon=True).start()
        return task.snapshot()

    # ---------- 实例编排 ----------

    def provision_instance(self, payload: dict[str, Any]) -> dict[str, Any]:
        instance = self.instances.create(payload)
        instance_id = instance["id"]
        mc_version = instance["mc_version"]
        loader = instance.get("loader") or "vanilla"
        loader_version = instance.get("loader_version") or None
        local_installer = instance.get("loader_installer") or ""
        task = self.tasks.create("instance", f"创建实例 {instance['name']}")
        self.bus.log(f"创建实例 {instance['name']}（{mc_version} / {loader}）", source="instance")

        def worker() -> None:
            try:
                self.tasks.progress(task.id, message=f"安装 Minecraft {mc_version}")
                version_id = mc_version
                if loader and loader != "vanilla":
                    self.tasks.progress(task.id, message=f"安装 {loader} 加载器")
                    java_path = self.java.resolve_for_install(mc_version)
                    if local_installer:
                        cached_installer = cache_mod_loader_jar(self.config, local_installer)
                        local_installer = str(cached_installer)
                        self.instances.update(
                            instance_id,
                            {"loader_installer": local_installer},
                        )
                        version_id, resolved_loader_version = install_mod_loader_from_jar(
                            loader,
                            mc_version,
                            str(self.config.minecraft_directory),
                            loader_version or "",
                            cached_installer,
                            self._callback(task.id),
                            java_path,
                        )
                    else:
                        version_id, resolved_loader_version = install_mod_loader(
                            loader,
                            mc_version,
                            str(self.config.minecraft_directory),
                            loader_version,
                            self._callback(task.id),
                            java_path,
                        )
                else:
                    mll.install.install_minecraft_version(
                        mc_version,
                        str(self.config.minecraft_directory),
                        callback=self._callback(task.id),
                    )
                    resolved_loader_version = ""
                self.instances.update(
                    instance_id,
                    {
                        "version_id": version_id,
                        "loader": loader,
                        "loader_version": resolved_loader_version or (loader_version or ""),
                        "loader_installer": local_installer,
                    },
                )
                self._version_cache = None
                self.tasks.finish(task.id, {"instance": instance_id, "version": version_id}, "实例创建完成")
                self.bus.publish(make_event("versions.changed"))
                self.bus.publish(make_event("instances.changed"))
                self.bus.log(f"实例 {instance['name']} 创建完成，版本 ID: {version_id}", source="instance")
            except Exception as error:
                self.tasks.fail(task.id, str(error))
                self.bus.log(f"实例创建失败: {error}", source="instance", level="error")

        threading.Thread(target=worker, daemon=True).start()
        return {"instance": self.instances.snapshot(self.instances.require(instance_id)), "task": task.snapshot()}

    def repair_instance(self, instance_id: str) -> dict[str, Any]:
        instance = self.instances.require(instance_id)
        task = self.tasks.create("instance", f"修复实例 {instance['name']}")

        def worker() -> None:
            try:
                mc_version = instance["mc_version"]
                loader = instance.get("loader") or "vanilla"
                self.tasks.progress(task.id, message=f"校验 Minecraft {mc_version}")
                version_id = mc_version
                if loader and loader != "vanilla":
                    local_installer = str(instance.get("loader_installer") or "")
                    if local_installer and Path(local_installer).is_file():
                        version_id, resolved_loader_version = install_mod_loader_from_jar(
                            loader,
                            mc_version,
                            str(self.config.minecraft_directory),
                            instance.get("loader_version") or "",
                            local_installer,
                            self._callback(task.id),
                            self.java.resolve_for_install(mc_version),
                        )
                    else:
                        version_id, resolved_loader_version = install_mod_loader(
                            loader,
                            mc_version,
                            str(self.config.minecraft_directory),
                            instance.get("loader_version") or None,
                            self._callback(task.id),
                            self.java.resolve_for_install(mc_version),
                        )
                else:
                    mll.install.install_minecraft_version(
                        mc_version,
                        str(self.config.minecraft_directory),
                        callback=self._callback(task.id),
                    )
                    resolved_loader_version = ""
                self.instances.update(
                    instance_id,
                    {
                        "version_id": version_id,
                        "loader": loader,
                        "loader_version": resolved_loader_version or instance.get("loader_version") or "",
                        "loader_installer": instance.get("loader_installer") or "",
                    },
                )
                self.tasks.finish(task.id, {"instance": instance_id}, "实例修复完成")
                self.bus.publish(make_event("instances.changed"))
            except Exception as error:
                self.tasks.fail(task.id, str(error))

        threading.Thread(target=worker, daemon=True).start()
        return task.snapshot()

    # ---------- 模组加载器 ----------

    def loader_list(self) -> list[dict[str, str]]:
        return [
            {"id": loader, "name": mll.mod_loader.get_mod_loader(loader).get_name()}
            for loader in mll.mod_loader.list_mod_loader()
        ]

    def loader_versions(self, loader: str, minecraft_version: str) -> dict[str, Any]:
        module = mll.mod_loader.get_mod_loader(loader)
        supported = module.is_minecraft_version_supported(minecraft_version)
        versions = module.get_loader_versions(minecraft_version, True) if supported else []
        return {
            "loader": loader,
            "minecraft_version": minecraft_version,
            "supported": supported,
            "versions": versions,
        }

    def loader_minecraft_versions(self, loader: str, stable_only: bool = True) -> list[str]:
        return mll.mod_loader.get_mod_loader(loader).get_minecraft_versions(stable_only)

    def inspect_loader_jar(self, installer_path: str) -> dict[str, Any]:
        return inspect_mod_loader_jar(installer_path)

    def install_loader(
        self,
        loader: str,
        minecraft_version: str,
        loader_version: str | None = None,
        instance_id: str | None = None,
        installer_path: str | None = None,
    ) -> dict[str, Any]:
        module = mll.mod_loader.get_mod_loader(loader)
        name = module.get_name()
        source_label = "本地安装包" if installer_path else "自动下载官方安装器"
        task = self.tasks.create("loader", f"安装 {name} @ {minecraft_version} · {source_label}")
        self.bus.log(f"开始安装 {name} ({minecraft_version})", source="loader")

        def worker() -> None:
            try:
                cached_installer = ""
                if installer_path:
                    cached_path = cache_mod_loader_jar(self.config, installer_path)
                    cached_installer = str(cached_path)
                    installed, resolved_loader_version = install_mod_loader_from_jar(
                        loader,
                        minecraft_version,
                        str(self.config.minecraft_directory),
                        loader_version or "",
                        cached_path,
                        self._callback(task.id),
                        self.java.resolve_for_install(minecraft_version),
                    )
                else:
                    installed, resolved_loader_version = install_mod_loader(
                        loader,
                        minecraft_version,
                        str(self.config.minecraft_directory),
                        loader_version,
                        self._callback(task.id),
                        self.java.resolve_for_install(minecraft_version),
                    )
                self.tasks.finish(task.id, {"version": installed, "loader": loader}, "加载器安装完成")
                self._version_cache = None
                if instance_id:
                    self.instances.update(
                        instance_id,
                        {
                            "version_id": installed,
                            "loader": loader,
                            "loader_version": resolved_loader_version,
                            "loader_installer": cached_installer,
                        },
                    )
                self.bus.publish(make_event("versions.changed"))
                self.bus.publish(make_event("instances.changed"))
                self.bus.log(f"{name} 安装完成，版本 ID: {installed}", source="loader")
            except Exception as error:
                self.tasks.fail(task.id, str(error))
                self.bus.log(f"{name} 安装失败: {error}", source="loader", level="error")

        threading.Thread(target=worker, daemon=True).start()
        return task.snapshot()

    # ---------- 启动 ----------

    def java_executable(self, instance: dict[str, Any] | None = None) -> str:
        resolved = self.java.resolve(instance)
        if resolved and resolved.get("path"):
            executable = Path(str(resolved["path"]))
            if os.name == "nt" and executable.name.lower() == "javaw.exe":
                console_java = executable.with_name("java.exe")
                try:
                    if console_java.is_file():
                        return str(console_java)
                except OSError:
                    pass
            return str(executable)
        raise JavaError("未找到可用的 Java。请先在 Java 运行时页面下载 Zulu。")

    def _validate_java_runtime(
        self,
        executable: str,
        required_major: int,
        memory: int,
        min_memory: int,
        jvm_arguments: list[str],
    ) -> None:
        try:
            binary = Path(executable)
            if not binary.is_file():
                raise JavaError(f"Java 可执行文件不存在或无法访问: {executable}")
            command = [
                str(binary),
                f"-Xmx{memory}M",
                f"-Xms{min_memory}M",
                *jvm_arguments,
                "-XshowSettings:properties",
                "-version",
            ]
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            probe = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                creationflags=creationflags,
            )
        except JavaError:
            raise
        except Exception as error:
            raise JavaError(f"无法启动 Java 运行环境: {error}") from error
        output = ((probe.stdout or "") + "\n" + (probe.stderr or "")).strip()
        if probe.returncode != 0:
            detail = output.splitlines()[-3:] if output else []
            raise JavaError(
                "Java 运行环境预检失败"
                + ("：" + " / ".join(detail) if detail else "，请重新安装或更换 Java")
            )
        version_match = re.search(r'version "([^"]+)"', output)
        if version_match:
            detected = version_match.group(1)
            detected_major = int(detected.split(".")[0])
            if detected_major == 1 and "." in detected:
                detected_major = int(detected.split(".")[1])
            if detected_major < required_major:
                raise JavaError(
                    f"当前 Java {detected_major} 低于实例要求的 Java {required_major}"
                )
        if "sun.arch.data.model = 32" in output and memory > 1300:
            raise JavaError("当前是 32 位 Java，无法分配 " + str(memory) + " MB 内存")

    def build_command(self, instance: dict[str, Any], account: dict[str, Any]) -> list[str]:
        settings = self.config.settings
        try:
            memory = int(instance.get("memory_mb") or settings.get("memory_mb", 4096))
            min_memory = int(instance.get("min_memory_mb") or settings.get("min_memory_mb", 512))
        except (TypeError, ValueError) as error:
            raise JavaError("内存设置无效，请检查实例与启动器设置") from error
        if memory < 512 or min_memory < 256 or min_memory > memory:
            raise JavaError("内存设置无效：最小内存不能高于最大内存")
        extra = instance.get("jvm_args")
        if extra is None:
            extra = settings.get("jvm_args") or ""
        if str(extra).strip() == LEGACY_JVM_ARGS:
            extra = SAFE_JVM_ARGS
        resolution = instance.get("resolution") or settings.get("resolution") or {}

        jvm_arguments = [f"-Xmx{memory}M", f"-Xms{min_memory}M"]
        for token in str(extra).split():
            if token.strip():
                jvm_arguments.append(token)
        executable = self.java_executable(instance)
        self._validate_java_runtime(
            executable,
            java_major_for_minecraft(str(instance.get("mc_version") or "")),
            memory,
            min_memory,
            [token for token in str(extra).split() if token.strip()],
        )
        try:
            jvm_arguments.extend(self.auth.authlib_arguments(account))
        except Exception as error:
            self.bus.log(f"注入 authlib-injector 失败: {error}", source="launch", level="error")

        version_id = instance.get("version_id") or instance.get("mc_version")
        directory = self.instances.directory_of(instance)
        options: dict[str, Any] = {
            "username": account.get("name", "Player"),
            "uuid": account.get("uuid", ""),
            "token": account.get("access_token") or "0",
            "executablePath": executable,
            "jvmArguments": jvm_arguments,
            "launcherName": APP_NAME,
            "launcherVersion": APP_VERSION,
            "gameDirectory": str(directory),
        }
        if resolution.get("enabled"):
            options["customResolution"] = True
            options["resolutionWidth"] = str(resolution.get("width", 1280))
            options["resolutionHeight"] = str(resolution.get("height", 720))

        return mll.command.get_minecraft_command(version_id, str(self.config.minecraft_directory), options)

    def launch(self, instance_id: str, account: dict[str, Any]) -> dict[str, Any]:
        instance = self.instances.require(instance_id)
        if not self.instances.version_installed(instance):
            raise InstanceError("该实例的版本文件缺失，请先修复实例")
        command = self.build_command(instance, account)
        task = self.tasks.create("launch", f"启动 {instance['name']}")
        self.bus.log(f"启动实例 {instance['name']}（PID 即将分配）", source="launch")

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        directory = self.instances.directory_of(instance)
        process = subprocess.Popen(
            command,
            cwd=str(directory),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
        with self._lock:
            self._processes[process.pid] = process
        self.tasks.finish(task.id, {"pid": process.pid}, "游戏进程已启动")
        self.instances.touch_played(instance_id)
        self.bus.publish(make_event("game.started", pid=process.pid, instance=instance_id, version=instance.get("version_id")))
        self.bus.publish(make_event("instances.changed"))

        def reader() -> None:
            started_at = time.time()
            try:
                if process.stdout is not None:
                    for line in process.stdout:
                        self.bus.publish(make_event("log", source="game", line=line.rstrip(), level="game"))
            finally:
                code = process.wait()
                with self._lock:
                    self._processes.pop(process.pid, None)
                self._add_playtime(instance_id, int(time.time() - started_at))
                self.bus.publish(make_event("game.exited", pid=process.pid, code=code, instance=instance_id))
                self.bus.publish(make_event("instances.changed"))

        threading.Thread(target=reader, daemon=True).start()
        return {"pid": process.pid, "instance": instance_id, "task": task.snapshot()}

    def running_games(self) -> list[dict[str, Any]]:
        alive = []
        for pid, process in list(self._processes.items()):
            if process.poll() is None:
                alive.append({"pid": pid})
            else:
                self._processes.pop(pid, None)
        return alive

    def stop_all(self) -> None:
        for process in list(self._processes.values()):
            try:
                process.terminate()
            except Exception:
                pass
        self._processes.clear()

    # ---------- 内部 ----------

    def _add_playtime(self, instance_id: str, seconds: int) -> None:
        instance = self.instances.get(instance_id)
        if not instance:
            return
        try:
            self.instances.update(instance_id, {"playtime": int(instance.get("playtime") or 0) + max(0, seconds)})
        except Exception:
            pass

    def _callback(self, task_id: str) -> dict[str, Any]:
        def set_status(status: str) -> None:
            self.tasks.progress(task_id, message=str(status))

        def set_progress(progress: int) -> None:
            self.tasks.progress(task_id, progress=int(progress))

        def set_max(maximum: int) -> None:
            self.tasks.progress(task_id, total=int(maximum))

        return {"setStatus": set_status, "setProgress": set_progress, "setMax": set_max}
