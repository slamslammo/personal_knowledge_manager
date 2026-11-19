"""运行时路径与归档契约的回归测试。

覆盖路径推导、固定命名、状态保留和按周归档。
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import paths  # noqa: E402
import workdir  # noqa: E402


class RuntimeRootTest(unittest.TestCase):
    def test_default_root_is_outside_repo_and_stable(self):
        repo = pathlib.Path("/tmp/checkout/repo")
        with mock.patch.dict(os.environ, {}, clear=True):
            a = paths.runtime_root(repo)
            b = paths.runtime_root(repo)
        self.assertEqual(a, b)
        self.assertEqual(a.name, paths.RUNTIME_DIR_NAME)
        # macOS 的 /tmp 是 /private/tmp 的符号链接，比较前统一 resolve。
        self.assertEqual(a.parent, repo.resolve().parent)
        self.assertNotIn(repo.resolve(), a.parents)

    def test_same_environment_repeated_runs_same_work_dir(self):
        repo = pathlib.Path("/tmp/checkout/repo")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(paths.work_dir(repo), paths.work_dir(repo))
            self.assertEqual(paths.work_dir(repo).name, paths.WORK_DIR_NAME)

    def test_home_override_is_deployment_level(self):
        repo = pathlib.Path("/tmp/checkout/repo")
        with tempfile.TemporaryDirectory() as d:
            env = {"AI_WEEKLY_HOME": d}
            self.assertEqual(paths.runtime_root(repo, env), pathlib.Path(d).resolve())
            self.assertEqual(paths.work_dir(repo, env), pathlib.Path(d).resolve() / "work")

    def test_legacy_tmp_override_still_wins(self):
        repo = pathlib.Path("/tmp/checkout/repo")
        with tempfile.TemporaryDirectory() as d:
            env = {"AI_WEEKLY_HOME": "/tmp/other", "AI_WEEKLY_TMP": d}
            self.assertEqual(paths.work_dir(repo, env), pathlib.Path(d).resolve())

    def test_archive_week_format_is_enforced(self):
        repo = pathlib.Path("/tmp/checkout/repo")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(paths.archive_dir("2026-W41", repo).name == "2026-W41")
            for bad in ("w41", "2026-W1", "2026-W41-backup", "", None):
                with self.assertRaises(ValueError, msg=bad):
                    paths.archive_dir(bad, repo)

    def test_different_weeks_never_collide(self):
        repo = pathlib.Path("/tmp/checkout/repo")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertNotEqual(paths.archive_dir("2026-W40", repo),
                                paths.archive_dir("2026-W41", repo))

    def test_work_dir_inside_repo_is_rejected(self):
        repo = pathlib.Path("/tmp/checkout/repo")
        with self.assertRaises(ValueError):
            paths.validate_work_dir(repo / "scratch", repo)
        with self.assertRaises(ValueError):
            paths.validate_work_dir(pathlib.Path("/"), repo)
        paths.validate_work_dir(repo.parent / ".ai-weekly" / "work", repo)

    def test_file_names_are_fixed(self):
        self.assertEqual(paths.FILES["checks"], "checks.txt")
        self.assertEqual(paths.FILES["manifest"], "MANIFEST.json")
        self.assertTrue(paths.FILES["feishu"] in paths.CLEAN_PRESERVE)
        self.assertTrue(paths.FILES["trace"] in paths.ARCHIVE_EVIDENCE)


class CleanAndArchiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = pathlib.Path(self.tmp.name) / "work"
        self.work.mkdir()
        self.repo = pathlib.Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.env_patch = mock.patch.dict(os.environ, {
            "AI_WEEKLY_TMP": str(self.work),
            "AI_WEEKLY_HOME": str(pathlib.Path(self.tmp.name) / "runtime"),
        }, clear=True)
        self.env_patch.start()
        self.work_patch = mock.patch.object(workdir, "WORK_DIR", self.work)
        self.work_patch.start()
        self.repo_patch = mock.patch.object(workdir, "REPO_DIR", self.repo)
        self.repo_patch.start()

    def tearDown(self):
        self.repo_patch.stop()
        self.work_patch.stop()
        self.env_patch.stop()
        self.tmp.cleanup()

    def _write(self, name, obj=None, text=None):
        p = self.work / name
        p.write_text(text if text is not None else json.dumps(obj or {}), encoding="utf-8")
        return p

    def test_clean_preserves_cross_run_state(self):
        for name in paths.CLEAN_PRESERVE:
            self._write(name, {"kept": name})
        self._write(paths.FILES["digest"], text="scratch")
        self._write(paths.FILES["week"], {"week": "2026-W41"})
        (self.work / "out").mkdir()
        (self.work / "out" / "report.md").write_text("x", encoding="utf-8")

        rc = workdir.main(["clean", "--no-archive"])
        self.assertEqual(rc, 0)
        for name in paths.CLEAN_PRESERVE:
            self.assertTrue((self.work / name).exists(), f"{name} 不应被清理")
        self.assertFalse((self.work / paths.FILES["digest"]).exists())
        self.assertFalse((self.work / "out").exists())

    def test_clean_archives_previous_run_before_removing(self):
        self._write(paths.FILES["week"], {"week": "2026-W41", "report_path": "r/2026-W41.md"})
        self._write(paths.FILES["coord"], {"week": "2026-W41", "run_id": "run-1",
                                           "mode": "backfill", "test": False})
        self._write(paths.FILES["checks"], text="完整性检查通过\n")
        self._write(paths.FILES["feishu"], {"week": "2026-W41", "action": "created"})

        rc = workdir.main(["clean"])
        self.assertEqual(rc, 0)
        manifest = paths.archive_dir("2026-W41", self.repo) / paths.FILES["manifest"]
        self.assertTrue(manifest.exists())
        data = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(data["week"], "2026-W41")
        self.assertEqual(data["runs"][0]["run_id"], "run-1")
        self.assertIn(paths.FILES["checks"], data["files"])
        self.assertTrue((paths.archive_dir("2026-W41", self.repo) / paths.FILES["checks"]).exists())
        # 跨运行状态仍在，scratch 已清
        self.assertTrue((self.work / paths.FILES["feishu"]).exists())
        self.assertFalse((self.work / paths.FILES["checks"]).exists())

    def test_archive_is_idempotent_per_run_id(self):
        self._write(paths.FILES["week"], {"week": "2026-W41"})
        self._write(paths.FILES["coord"], {"week": "2026-W41", "run_id": "run-1"})
        self._write(paths.FILES["checks"], text="ok")
        workdir.main(["archive", "--week", "2026-W41"])
        workdir.main(["archive", "--week", "2026-W41"])
        data = json.loads((paths.archive_dir("2026-W41", self.repo) /
                           paths.FILES["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(len(data["runs"]), 1)

    def test_archive_rejects_bad_week(self):
        with self.assertRaises(ValueError):
            workdir.main(["archive", "--week", "W41-backup"])


if __name__ == "__main__":
    unittest.main()
