from __future__ import annotations

import json
import os
import shutil
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from neo.config import Config
from neo.events import EventBus
from neo.instances import InstanceManager
from neo import modpacks
from neo.modpacks import ModpackError, ModpackService
from neo.mods.downloader import DownloadResult, sanitize_filename
from neo.tasks import TaskManager


def _write_zip(path: Path, files: dict[str, bytes | str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


class ModpackInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[2] / ".test-tmp" / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        self.previous_config = os.environ.get("NEO_CONFIG_DIR")
        os.environ["NEO_CONFIG_DIR"] = str(self.root / "config")
        self.config = Config()
        self.config.set("minecraft_directory", str(self.root / "minecraft"))
        self.bus = EventBus()
        self.tasks = TaskManager(self.bus)
        self.instances = InstanceManager(self.config)
        self.service = ModpackService(self.config, self.tasks, self.bus, self.instances, mock.Mock())

    def tearDown(self) -> None:
        if self.previous_config is None:
            os.environ.pop("NEO_CONFIG_DIR", None)
        else:
            os.environ["NEO_CONFIG_DIR"] = self.previous_config
        shutil.rmtree(self.root, ignore_errors=True)

    def test_mrpack_extension_is_preserved(self) -> None:
        self.assertEqual(sanitize_filename("Example-1.0.mrpack"), "Example-1.0.mrpack")

    def test_online_install_uses_the_downloaded_file_path(self) -> None:
        installed_path: Path | None = None
        installed_contents = b""

        def fake_download(url: str, directory: Path, filename: str, **_: object) -> DownloadResult:
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / sanitize_filename(filename)
            target.write_bytes(b"mrpack")
            return DownloadResult(str(target), target.stat().st_size, False, 1)

        def fake_install(archive: Path, *_: object, **__: object) -> dict[str, object]:
            nonlocal installed_path, installed_contents
            installed_path = archive
            installed_contents = archive.read_bytes()
            return {"id": "test-instance", "name": "Test Pack", "directory": str(self.root)}

        with (
            mock.patch.object(self.service, "_resolve_download", return_value=("https://example.invalid/pack", "Pack.mrpack")),
            mock.patch.object(self.service, "_install_archive", side_effect=fake_install),
            mock.patch.object(modpacks, "download_file", side_effect=fake_download),
            mock.patch.object(modpacks.tempfile, "mkdtemp", return_value=str(self.root / "download")),
        ):
            task = self.service.install("modrinth", "project")
            self._wait_for_task(task["id"])

        self.assertIsNotNone(installed_path)
        assert installed_path is not None
        self.assertEqual(installed_path.name, "Pack.mrpack")
        self.assertEqual(installed_contents, b"mrpack")

    def test_local_mrpack_extracts_client_overrides(self) -> None:
        archive = self.root / "pack.mrpack"
        index = {
            "formatVersion": 1,
            "game": "minecraft",
            "versionId": "1.0.0",
            "name": "Offline Test Pack",
            "summary": "integration test",
            "files": [],
            "dependencies": {"minecraft": "1.20.1", "fabric-loader": "0.15.11"},
        }
        _write_zip(
            archive,
            {
                "modrinth.index.json": json.dumps(index),
                "overrides/config/example.txt": "shared",
                "client-overrides/config/client-only.txt": "client",
            },
        )
        task = self.tasks.create("modpack", "test")

        with mock.patch.object(self.service, "_install_base", return_value="fabric-loader-0.15.11-1.20.1"):
            instance = self.service._install_archive(archive, task.id)

        instance_dir = self.instances.directory_of(instance)
        self.assertEqual((instance_dir / "config" / "example.txt").read_text(), "shared")
        self.assertEqual((instance_dir / "config" / "client-only.txt").read_text(), "client")
        self.assertEqual(instance["version_id"], "fabric-loader-0.15.11-1.20.1")

    def test_curseforge_required_file_failure_is_reported(self) -> None:
        archive = self.root / "pack.zip"
        manifest = {
            "minecraft": {
                "version": "1.20.1",
                "modLoaders": [{"id": "forge-47.2.20", "primary": True}],
            },
            "name": "Broken Pack",
            "files": [{"projectID": 123, "fileID": 456, "required": True}],
        }
        _write_zip(archive, {"manifest.json": json.dumps(manifest)})
        task = self.tasks.create("modpack", "test")

        with (
            mock.patch.object(self.service, "_install_base", return_value="1.20.1-forge-47.2.20"),
            mock.patch.object(self.service, "_curseforge_file", side_effect=RuntimeError("download denied")),
        ):
            with self.assertRaisesRegex(ModpackError, "1 个必需文件下载失败"):
                self.service._install_archive(archive, task.id)

    def _wait_for_task(self, task_id: str) -> None:
        deadline = time.time() + 5
        while time.time() < deadline:
            task = self.tasks.get(task_id)
            if task is not None and task.state != "running":
                if task.state == "error":
                    self.fail(task.error or "modpack task failed")
                return
            time.sleep(0.01)
        self.fail("modpack task did not finish")


if __name__ == "__main__":
    unittest.main()
