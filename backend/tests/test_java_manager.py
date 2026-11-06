from __future__ import annotations

import hashlib
import os
import shutil
import time
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest import mock

import httpx

from neo.config import Config
from neo.events import EventBus
from neo.java_manager import DOWNLOAD_PROGRESS_END, EXTRACT_PROGRESS_END, JavaError, JavaManager
from neo.tasks import TaskManager


class JavaManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = (
            Path(__file__).resolve().parents[2]
            / ".test-tmp"
            / f"java-manager-{self._testMethodName}-{uuid.uuid4().hex[:8]}"
        )
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        self.previous_config = os.environ.get("NEO_CONFIG_DIR")
        os.environ["NEO_CONFIG_DIR"] = str(self.root / "config")
        self.config = Config()
        self.bus = EventBus()
        self.tasks = TaskManager(self.bus)
        self.manager = JavaManager(self.config, self.tasks, self.bus)

    def tearDown(self) -> None:
        if self.previous_config is None:
            os.environ.pop("NEO_CONFIG_DIR", None)
        else:
            os.environ["NEO_CONFIG_DIR"] = self.previous_config
        shutil.rmtree(self.root, ignore_errors=True)

    def test_download_stops_at_declared_length_and_verifies_sha256(self) -> None:
        payload = b"zulu-java-archive" * 4096
        task = self.tasks.create("java", "test java")
        target = self.root / "zulu.zip"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                stream=httpx.ByteStream(payload),
                headers={"Content-Length": str(len(payload))},
                request=request,
            )

        real_client = httpx.Client
        with mock.patch(
            "neo.java_manager.httpx.Client",
            side_effect=lambda *_, **__: real_client(
                transport=httpx.MockTransport(handler)
            ),
        ):
            written = self.manager._download(
                {
                    "name": "zulu.zip",
                    "url": "https://example.invalid/zulu.zip",
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                },
                target,
                task.id,
            )

        current = self.tasks.get(task.id)
        self.assertEqual(written, len(payload))
        self.assertEqual(target.read_bytes(), payload)
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current.total, 100)
        self.assertEqual(current.progress, DOWNLOAD_PROGRESS_END)

    def test_download_rejects_sha256_mismatch(self) -> None:
        self.config.set("download_retries", 1)
        payload = b"corrupt"
        task = self.tasks.create("java", "test java")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, stream=httpx.ByteStream(payload), request=request)

        real_client = httpx.Client
        with mock.patch(
            "neo.java_manager.httpx.Client",
            side_effect=lambda *_, **__: real_client(
                transport=httpx.MockTransport(handler)
            ),
        ):
            with self.assertRaisesRegex(JavaError, "SHA-256"):
                self.manager._download(
                    {
                        "name": "zulu.zip",
                        "url": "https://example.invalid/zulu.zip",
                        "size": len(payload),
                        "sha256": "0" * 64,
                    },
                    self.root / "zulu.zip",
                    task.id,
                )

        self.assertFalse((self.root / "zulu.zip").exists())

    def test_extracts_zip_with_visible_progress(self) -> None:
        archive = self.root / "zulu.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("zulu-21/bin/java.exe", b"java")
            bundle.writestr("zulu-21/release", 'JAVA_VERSION="21.0.8"\n')
            bundle.writestr("zulu-21/lib/modules", b"modules")
        task = self.tasks.create("java", "test java")

        extract_dir = self.root / "extract"
        self.manager._extract_zip(archive, extract_dir, task.id)

        current = self.tasks.get(task.id)
        self.assertTrue((extract_dir / "zulu-21" / "bin" / "java.exe").is_file())
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current.progress, EXTRACT_PROGRESS_END)
        self.assertIn("3/3", current.message)

    def test_install_task_finishes_after_extracting_runtime(self) -> None:
        archive = self.root / "zulu-21.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("zulu-21/bin/java.exe", b"java")
            bundle.writestr("zulu-21/release", 'JAVA_VERSION="21.0.8"\n')
        package = {
            "url": "https://example.invalid/zulu-21.zip",
            "name": archive.name,
            "size": archive.stat().st_size,
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "major": 21,
            "version": "21.0.8",
        }

        def fake_download(_: dict[str, object], target: Path, task_id: str) -> int:
            shutil.copyfile(archive, target)
            self.tasks.progress(task_id, progress=DOWNLOAD_PROGRESS_END, total=100)
            return target.stat().st_size

        with (
            mock.patch.object(self.manager, "resolve_package", return_value=package),
            mock.patch.object(self.manager, "_download", side_effect=fake_download),
        ):
            task = self.manager.install(21)
            current = self._wait_for_task(task["id"])

        self.assertEqual(current.state, "done")
        self.assertTrue(Path(current.result["path"]).is_file())
        self.assertEqual(current.result["version"], "21.0.8")

    def _wait_for_task(self, task_id: str):
        deadline = time.time() + 5
        while time.time() < deadline:
            task = self.tasks.get(task_id)
            if task is not None and task.state != "running":
                if task.state == "error":
                    self.fail(task.error or "java install failed")
                return task
            time.sleep(0.01)
        self.fail("java install task did not finish")


if __name__ == "__main__":
    unittest.main()
