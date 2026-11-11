"""coord.py 的测试：状态流转（纯函数）与多智能体并发（本地裸仓库模拟远端，不调用模型、不碰 GitHub）。"""
import concurrent.futures
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import coord  # noqa: E402

CFG = {"max_attempts": 3, "clock_skew_minutes": 5, "run_lease_minutes": 60, "verify_lease_minutes": 20,
       "renew_below_minutes": 30, "push_retries": 5, "branch": "main"}
T0 = dt.datetime(2026, 11, 9, 10, 0, tzinfo=coord.BJT)


def ctx_for(run_id="claude-1", platform="claude", **kw):
    base = dict(repo=pathlib.Path("."), work=pathlib.Path("."), remote="origin", branch="main", week="2026-W45",
                mode="normal", report_path="r.md", data_path="d.json", state_path="s.json", run_id=run_id,
                platform=platform, test=True, cfg=CFG)
    base.update(kw)
    return coord.Ctx(**base)


class DecideTest(unittest.TestCase):
    def state(self, phase, lock_run="other", lease_min=30, attempts=1, produced_by="other"):
        s = coord.empty_state("2026-W45")
        s["phase"], s["attempts"] = phase, attempts
        if phase in ("running", "verifying"):
            s["lock"] = {"purpose": "run" if phase == "running" else "verify", "run_id": lock_run,
                         "platform": "codex", "lease_until": coord.iso(T0 + dt.timedelta(minutes=lease_min))}
        if phase in ("produced", "verifying", "done"):
            s["produced"] = {"run_id": produced_by, "platform": "codex", "quality": "full"}
        return s

    def act(self, state, run_id="me"):
        return coord.decide(state, T0, run_id, CFG)[0]

    def test_matrix(self):
        self.assertEqual(self.act(None), "run")
        self.assertEqual(self.act(self.state("idle", attempts=1)), "run")
        self.assertEqual(self.act(self.state("idle", attempts=3)), "needs_human")
        self.assertEqual(self.act(self.state("running")), "wait")
        self.assertEqual(self.act(self.state("running", lease_min=-4)), "wait")  # 还在 5 分钟时钟余量内
        self.assertEqual(self.act(self.state("running", lease_min=-6)), "takeover")
        self.assertEqual(self.act(self.state("running", lease_min=-6, attempts=3)), "needs_human")
        self.assertEqual(self.act(self.state("running", lock_run="me")), "run")
        self.assertEqual(self.act(self.state("produced")), "verify")
        self.assertEqual(self.act(self.state("produced", produced_by="me")), "exit")
        self.assertEqual(self.act(self.state("verifying")), "exit")
        self.assertEqual(self.act(self.state("verifying", lease_min=-6)), "verify_takeover")
        self.assertEqual(self.act(self.state("done")), "exit")
        self.assertEqual(self.act(self.state("needs_human")), "exit")

    def test_validate_state(self):
        good = self.state("running")
        self.assertIsNone(coord.validate_state(good, "2026-W45"))
        self.assertIn("不匹配", coord.validate_state(good, "2026-W46"))
        bad = dict(good, phase="weird")
        self.assertIn("phase", coord.validate_state(bad, "2026-W45"))
        self.assertIn("没有锁", coord.validate_state(dict(good, lock=None), "2026-W45"))
        self.assertIsNotNone(coord.validate_state([], "2026-W45"))


class TransitionTest(unittest.TestCase):
    def test_run_publish_verify_done(self):
        a, b = ctx_for("a", "claude"), ctx_for("b", "codex")
        s = coord.apply_acquire(None, a, "run", T0, "normal", "本周还没有运行")
        self.assertEqual((s["phase"], s["attempts"], s["lock"]["run_id"]), ("running", 1, "a"))
        s = coord.apply_publish(s, a, T0, "full", ["r.md"], [], None)
        self.assertEqual((s["phase"], s["lock"], s["produced"]["run_id"]), ("produced", None, "a"))
        s = coord.apply_acquire(s, b, "verify", T0, "verify", "")
        self.assertEqual((s["phase"], s["lock"]["purpose"], s["attempts"]), ("verifying", "verify", 1))
        s2, nxt = coord.apply_verified(s, b, T0, "pass", [], "", None)
        self.assertEqual((nxt, s2["phase"]), ("done", "done"))
        # 不通过：同一把锁转为运行，尝试次数 +1，新增一条重跑记录
        s3, nxt = coord.apply_verified(s, b, T0, "fail", ["GATE_NOT_OFFICIAL"], "", None)
        self.assertEqual((nxt, s3["phase"], s3["lock"]["purpose"], s3["attempts"]), ("run", "running", "run", 2))
        self.assertEqual(s3["runs"][-1]["mode"], "rerun")
        self.assertEqual(s3["runs"][-2]["outcome"], "verified:fail")

    def test_fail_paths(self):
        a = ctx_for("a")
        s = coord.apply_acquire(None, a, "run", T0, "normal", "")
        self.assertEqual(coord.apply_fail(s, a, T0, "WRITE_FAILED", "", None)["phase"], "idle")
        s["attempts"] = 3
        failed = coord.apply_fail(s, a, T0, "WRITE_FAILED", "", None)
        self.assertEqual(failed["phase"], "needs_human")
        self.assertIn("ATTEMPTS_EXHAUSTED", failed["runs"][-1]["codes"])
        # 校验中失败：周报已在，回到已产出，不消耗尝试次数
        s = coord.apply_publish(coord.apply_acquire(None, a, "run", T0, "normal", ""), a, T0, "full", [], [], None)
        b = ctx_for("b")
        s = coord.apply_acquire(s, b, "verify", T0, "verify", "")
        self.assertEqual(coord.apply_fail(s, b, T0, "INTERNAL", "", None)["phase"], "produced")

    def test_events_capped(self):
        s = coord.empty_state("2026-W45")
        s = coord.merge_events(s, [{"seq": i, "detail": "x"} for i in range(10)], cap=4)
        self.assertEqual([e["seq"] for e in s["events"]], [6, 7, 8, 9])


# ---------------------------------------------------------------- 多智能体集成测试


def sh(*args, cwd=None, check=True):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=check)


class Lab:
    """一个本地裸仓库作远端，若干克隆各自扮演一个智能体（独立的仓库和工作目录）。"""

    def __init__(self, root: pathlib.Path, week="2026-W45", overrides=None):
        self.root, self.week = root, week
        self.remote = root / "remote.git"
        sh("git", "init", "-q", "--bare", "-b", "main", str(self.remote))
        seed = root / "seed"
        sh("git", "clone", "-q", str(self.remote), str(seed))
        (seed / "README.md").write_text("seed\n")
        self.git(seed, "add", "README.md")
        self.git(seed, "commit", "-q", "-m", "init")
        self.git(seed, "push", "-q", "origin", "HEAD:main")
        self.overrides = {"wait_poll_seconds": 1, "wait_call_max_seconds": 30, "wait_max_minutes": 1}
        self.overrides.update(overrides or {})
        self.gate_pass = self.gate("pass")
        self.gate_fail = self.gate("fail")
        # 测试无法产出真实的采集中间文件，coord.py publish 前的门槛用替身（--test 模式下才生效）
        self.overrides.setdefault("publish", {}).setdefault("gate_script", str(self.gate_pass))

    def gate(self, kind: str) -> pathlib.Path:
        """写一个门槛替身：pass 退出 0；fail 输出 CODES 并退出 1。"""
        path = self.root / f"gate_{kind}.py"
        body = "raise SystemExit(0)\n" if kind == "pass" else \
            'print("CODES=GATE_NUMBERS")\nraise SystemExit(1)\n'
        path.write_text(body, encoding="utf-8")
        return path

    @staticmethod
    def git(repo, *args):
        return sh("git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args)

    def agent(self, name, week=None):
        week = week or self.week
        repo = self.root / f"repo-{name}"
        if not repo.exists():
            sh("git", "clone", "-q", str(self.remote), str(repo))
            self.git(repo, "config", "user.name", name)
            self.git(repo, "config", "user.email", f"{name}@example.invalid")
        work = self.root / f"work-{name}-{week}"
        work.mkdir(exist_ok=True)
        info = {"week": week, "mode": "normal", "iso_year": 2026,
                "report_path": f"AI资讯/周报/2026/{week}.md",
                "data_path": f"AI资讯/数据/github-weekly/{week}.json",
                "state_path": f"AI资讯/数据/运行记录/{week}.json"}
        (work / "week.json").write_text(json.dumps(info, ensure_ascii=False))
        return Agent(self, name, repo, work, info)

    def show(self, path, ref="main"):
        p = sh("git", "--git-dir", str(self.remote), "show", f"{ref}:{path}", check=False)
        return p.stdout if p.returncode == 0 else None

    def state(self, week=None):
        raw = self.show(f"AI资讯/数据/运行记录/{week or self.week}.json")
        return json.loads(raw) if raw else None

    def log(self, fmt="%s"):
        return sh("git", "--git-dir", str(self.remote), "log", f"--format={fmt}", "main").stdout.splitlines()


class Agent:
    def __init__(self, lab, name, repo, work, info):
        self.lab, self.name, self.repo, self.work, self.info = lab, name, repo, work, info

    def env(self):
        e = dict(os.environ)
        e.update(AI_WEEKLY_TMP=str(self.work), AI_WEEKLY_REPO=str(self.repo),
                 AI_WEEKLY_COORD=json.dumps(self.lab.overrides))
        return e

    def coord(self, *args):
        p = subprocess.run([sys.executable, str(SCRIPTS / "coord.py"), *args], capture_output=True, text=True,
                           env=self.env())
        first = (p.stdout.splitlines() or ["ACTION=?"])[0]
        return first.split("=", 1)[1], p

    def start(self, test=True):
        args = ["start"] + (["--test"] if test else []) + ["--platform", self.name, "--remote", str(self.lab.remote)]
        return self.coord(*args)

    def write_outputs(self, text="周报正文", degraded=False):
        head = f"---\nweek: {self.info['week']}\nquality: degraded\n---\n\n" if degraded else ""
        for rel, content in ((self.info["report_path"], f"{head}# {self.name} {text}\n"),
                             (self.info["data_path"], json.dumps({"by": self.name}) + "\n")):
            path = self.work / "out" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")


class MultiAgentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_concurrent_start_exactly_one_runs(self):
        lab = Lab(self.root)
        rounds = 12
        for i in range(rounds):
            week = f"2026-W{i + 1:02d}"
            a, b = lab.agent("a", week), lab.agent("b", week)
            with concurrent.futures.ThreadPoolExecutor(2) as ex:
                results = list(ex.map(lambda ag: ag.start()[0], (a, b)))
            self.assertEqual(sorted(results), ["run", "wait"], f"第 {i + 1} 轮：{results}")
            self.assertEqual(lab.state(week)["attempts"], 1)
        self.assertEqual(sh("git", "--git-dir", str(lab.remote), "rev-list", "--merges", "main").stdout, "")

    def test_full_flow_run_verify_exit(self):
        lab = Lab(self.root)
        a, b, c = lab.agent("a"), lab.agent("b"), lab.agent("c")
        self.assertEqual(a.start()[0], "run")
        self.assertEqual(b.start()[0], "wait")
        # 用户在 a 运行期间推送了无关提交：a 的发布要重试并成功，且不产生合并提交
        user = self.root / "user"
        sh("git", "clone", "-q", str(lab.remote), str(user))
        (user / "笔记.md").write_text("note\n")
        Lab.git(user, "add", "笔记.md")
        Lab.git(user, "commit", "-q", "-m", "用户笔记")
        Lab.git(user, "push", "-q", "origin", "HEAD:main")
        a.write_outputs()
        action, p = a.coord("publish")
        self.assertEqual(action, "published", p.stdout + p.stderr)
        self.assertIn("a 周报正文", lab.show(a.info["report_path"]))
        self.assertEqual(lab.show("笔记.md"), "note\n")
        # b 等待后转为校验，通过后完成；c 直接退出
        action, p = b.coord("wait")
        self.assertEqual(action, "verify", p.stdout)
        self.assertEqual(b.coord("verified", "--result", "pass")[0], "done")
        self.assertEqual(c.start()[0], "exit")
        st = lab.state()
        self.assertEqual((st["phase"], st["produced"]["platform"], st["verified"]["platform"]), ("done", "a", "b"))
        subjects = lab.log()
        self.assertIn("AI 周报 2026-W45", subjects)
        self.assertIn("AI 周报状态 2026-W45：校验通过（b）", subjects)
        self.assertEqual(sh("git", "--git-dir", str(lab.remote), "rev-list", "--merges", "main").stdout, "")

    def test_two_verifiers_only_one_verifies(self):
        lab = Lab(self.root)
        a = lab.agent("a")
        a.start()
        a.write_outputs()
        a.coord("publish")
        b, c = lab.agent("b"), lab.agent("c")
        with concurrent.futures.ThreadPoolExecutor(2) as ex:
            results = list(ex.map(lambda ag: ag.start()[0], (b, c)))
        self.assertEqual(sorted(results), ["exit", "verify"])

    def test_takeover_and_lost_lock(self):
        lab = Lab(self.root, overrides={"run_lease_minutes": 0, "clock_skew_minutes": 0})
        a, b = lab.agent("a"), lab.agent("b")
        self.assertEqual(a.start()[0], "run")
        time.sleep(1.1)  # a 的租约已过期（测试里租约为 0 分钟）
        self.assertEqual(b.start()[0], "run")
        st = lab.state()
        self.assertEqual((st["lock"]["platform"], st["attempts"], st["runs"][-1]["mode"]), ("b", 2, "takeover"))
        a.write_outputs()
        action, p = a.coord("publish")
        self.assertEqual((action, p.returncode), ("lost", coord.EXIT_LOST))
        self.assertIsNone(lab.show(a.info["report_path"]))
        b.write_outputs()
        self.assertEqual(b.coord("publish")[0], "published")
        self.assertIn("AI 周报 2026-W45（接管）", lab.log())

    def test_verify_fail_reruns_then_attempts_exhausted(self):
        lab = Lab(self.root, overrides={"max_attempts": 2})
        a, b = lab.agent("a"), lab.agent("b")
        a.start()
        a.write_outputs(degraded=True)  # 降级版的元数据由脚本写在周报里，quality 从元数据推导
        self.assertEqual(a.coord("publish")[0], "published")
        self.assertIn("AI 周报 2026-W45（降级）", lab.log())
        self.assertEqual(b.start()[0], "verify")
        action, _ = b.coord("verified", "--result", "fail", "--codes", "GATE_NOT_OFFICIAL")
        self.assertEqual(action, "run")
        b.write_outputs("重跑正文")
        self.assertEqual(b.coord("publish")[0], "published")
        self.assertIn("AI 周报 2026-W45（重跑）", lab.log())
        self.assertIn("b 重跑正文", lab.show(b.info["report_path"]))
        st = lab.state()
        self.assertEqual((st["phase"], st["attempts"], st["produced"]["run_id"].startswith("b-")),
                         ("produced", 2, True))
        # 第三个智能体校验仍不通过：尝试已用完，标为需人工；之后到达的直接退出
        c = lab.agent("c")
        self.assertEqual(c.start()[0], "verify")
        self.assertEqual(c.coord("verified", "--result", "fail", "--codes", "GATE_NUMBERS")[0], "exit")
        self.assertEqual(lab.state()["phase"], "needs_human")
        self.assertEqual(lab.agent("d").start()[0], "exit")

    def test_fail_releases_lock_and_records(self):
        lab = Lab(self.root)
        a, b = lab.agent("a"), lab.agent("b")
        a.start()
        action, _ = a.coord("fail", "--code", "WRITE_FAILED", "--detail", "写作中断")
        self.assertEqual(action, "exit")
        st = lab.state()
        self.assertEqual((st["phase"], st["runs"][-1]["outcome"], st["runs"][-1]["codes"]),
                         ("idle", "failed", ["WRITE_FAILED"]))
        self.assertTrue(any(e.get("code") == "WRITE_FAILED" for e in st["events"]))
        self.assertEqual(b.start()[0], "run")
        self.assertEqual(lab.state()["attempts"], 2)

    def test_manual_edit_not_overwritten(self):
        lab = Lab(self.root)
        a = lab.agent("a")
        user = self.root / "user"
        sh("git", "clone", "-q", str(lab.remote), str(user))
        path = user / a.info["report_path"]
        path.parent.mkdir(parents=True)
        path.write_text("我手工改的\n", encoding="utf-8")
        Lab.git(user, "add", "-A")
        Lab.git(user, "commit", "-q", "-m", "手工修改周报")
        Lab.git(user, "push", "-q", "origin", "HEAD:main")
        self.assertEqual(a.start()[0], "run")
        self.assertEqual(lab.state()["runs"][-1]["mode"], "rerun")
        a.write_outputs()
        action, p = a.coord("publish")
        self.assertEqual(action, "published")
        self.assertIn("未覆盖", p.stdout)
        self.assertEqual(lab.show(a.info["report_path"]), "我手工改的\n")
        self.assertIn('"by": "a"', lab.show(a.info["data_path"]))
        # 门槛检的是 OUT_DIR 的候选，提交的是人工改过的那份：不能记成 full/pass
        st = lab.state()["produced"]
        self.assertEqual((st["quality"], st["gates"]["check_run"]), ("check_failed", "skipped"))
        self.assertIn("GATE_UNVERIFIED", st["gates"]["codes"])
        self.assertIn("检查未通过", lab.log()[0])

    def test_invalid_state_stops(self):
        lab = Lab(self.root)
        a = lab.agent("a")
        user = self.root / "user"
        sh("git", "clone", "-q", str(lab.remote), str(user))
        path = user / a.info["state_path"]
        path.parent.mkdir(parents=True)
        path.write_text("{坏掉的", encoding="utf-8")
        Lab.git(user, "add", "-A")
        Lab.git(user, "commit", "-q", "-m", "坏状态")
        Lab.git(user, "push", "-q", "origin", "HEAD:main")
        action, p = a.start()
        self.assertEqual((action, p.returncode), ("error", coord.EXIT_INVALID))
        self.assertIn("STATE_INVALID", p.stdout)

    def test_outputs_outside_whitelist_not_committed(self):
        lab = Lab(self.root)
        a = lab.agent("a")
        a.start()
        a.write_outputs()
        stray = a.work / "out" / "AI资讯" / "任务" / "方案.md"
        stray.parent.mkdir(parents=True)
        stray.write_text("不该提交\n", encoding="utf-8")
        self.assertEqual(a.coord("publish")[0], "published")
        self.assertIsNone(lab.show("AI资讯/任务/方案.md"))

    def test_gate_failure_publishes_check_failed(self):
        lab = Lab(self.root)
        lab.overrides["publish"]["gate_script"] = str(lab.gate_fail)
        a = lab.agent("a")
        a.start()
        a.write_outputs()
        action, p = a.coord("publish")
        self.assertEqual(action, "published", p.stdout + p.stderr)
        self.assertIn("AI 周报 2026-W45（检查未通过）", lab.log())
        prod = lab.state()["produced"]
        self.assertEqual((prod["quality"], prod["gates"]["check_run"]), ("check_failed", "fail"))
        self.assertIn("GATE_NUMBERS", prod["gates"]["codes"])
        self.assertEqual(prod["gates"]["script"], str(lab.gate_fail))  # 用了哪支门槛脚本要留痕

    def test_declared_quality_must_match_gate(self):
        lab = Lab(self.root)
        lab.overrides["publish"]["gate_script"] = str(lab.gate_fail)
        a = lab.agent("a")
        a.start()
        a.write_outputs()
        action, p = a.coord("publish", "--quality", "full")
        self.assertEqual((action, p.returncode), ("error", coord.EXIT_ERROR))
        self.assertIn("GATE_MISMATCH", p.stdout)
        self.assertIsNone(lab.show(a.info["report_path"]))
        self.assertEqual(lab.state()["phase"], "running")  # 锁还在，返工后可以再发

    def test_quality_override_is_recorded(self):
        lab = Lab(self.root)
        lab.overrides["publish"]["gate_script"] = str(lab.gate_fail)
        a = lab.agent("a")
        a.info["mode"] = "backfill"  # 覆盖只对回溯放行
        (a.work / "week.json").write_text(json.dumps(a.info, ensure_ascii=False))
        a.start()
        a.write_outputs()
        action, p = a.coord("publish", "--allow-quality-override")  # 没给 --quality：用法错误
        self.assertEqual((action, p.returncode), ("error", coord.EXIT_ERROR))
        self.assertIn("--quality", p.stdout)
        action, p = a.coord("publish", "--quality", "full", "--allow-quality-override")
        self.assertEqual(action, "published", p.stdout + p.stderr)
        prod = lab.state()["produced"]
        self.assertEqual((prod["quality"], prod["gates"]["override"]), ("full", "full"))

    def test_override_must_match_report_metadata(self):
        # 覆盖不能改产物本身的质量：降级版周报不能声明 full
        lab = Lab(self.root)
        lab.overrides["publish"]["gate_script"] = str(lab.gate_fail)
        a = lab.agent("a")
        a.info["mode"] = "backfill"
        (a.work / "week.json").write_text(json.dumps(a.info, ensure_ascii=False))
        a.start()
        a.write_outputs(degraded=True)
        action, p = a.coord("publish", "--quality", "full", "--allow-quality-override")
        self.assertEqual((action, p.returncode), ("error", coord.EXIT_ERROR))
        self.assertIn("GATE_OVERRIDE_CONFLICT", p.stdout)
        action, p = a.coord("publish", "--quality", "degraded", "--allow-quality-override")
        self.assertEqual(action, "published", p.stdout + p.stderr)

    def test_override_denied_in_production_run(self):
        # 正式运行（非 --test、mode=normal）不许覆盖门槛结果：否则门槛失败的产出能被标成 full
        lab = Lab(self.root)
        lab.overrides["publish"]["gate_script"] = str(lab.gate_fail)
        a = lab.agent("a")
        a.start(test=False)
        a.write_outputs()
        action, p = a.coord("publish", "--quality", "full", "--allow-quality-override")
        self.assertEqual((action, p.returncode), ("error", coord.EXIT_ERROR))
        self.assertIn("GATE_OVERRIDE_DENIED", p.stdout)
        self.assertIsNone(lab.show(a.info["report_path"]))

    def test_override_allowed_in_backfill(self):
        lab = Lab(self.root)
        lab.overrides["publish"]["gate_script"] = str(lab.gate_fail)
        a = lab.agent("a")
        a.info["mode"] = "backfill"
        (a.work / "week.json").write_text(json.dumps(a.info, ensure_ascii=False))
        a.start(test=False)
        a.write_outputs()
        action, p = a.coord("publish", "--quality", "full", "--allow-quality-override")
        self.assertEqual(action, "published", p.stdout + p.stderr)
        self.assertIn("AI 周报 2026-W45（回溯）", lab.log())
        self.assertEqual(lab.state()["produced"]["gates"]["override"], "full")


if __name__ == "__main__":
    unittest.main()


class VerifyTest(unittest.TestCase):
    """verify.py：在远端版本上重跑门槛，结果写回状态文件。HN 采集和链接检查用假数据，不联网。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def produce(self, lab, report, mode="normal"):
        from test_validate import DATA
        a = lab.agent("a")
        a.info["mode"] = mode
        (a.work / "week.json").write_text(json.dumps(a.info, ensure_ascii=False))
        a.start()
        for rel, content in ((a.info["report_path"], report), (a.info["data_path"], json.dumps(DATA))):
            path = a.work / "out" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self.assertEqual(a.coord("publish")[0], "published")

    def run_verify(self, lab, hn_points=899):
        import verify
        from unittest import mock
        b = lab.agent("b")
        self.assertEqual(b.start()[0], "verify")
        stories = [{"id": str(i), "points": hn_points - i + 1, "num_comments": 10, "title": "t",
                    "url": f"https://example.com/a{i}", "hn_url": f"https://news.ycombinator.com/item?id={i}"}
                   for i in range(1, 6)]
        from common import FetchResult
        with mock.patch.dict(os.environ, b.env()), \
                mock.patch.object(verify.collect_hn, "collect", return_value={"status": "ok", "stories": stories}), \
                mock.patch.object(verify, "fetch", return_value=FetchResult(200, b"", None)):
            ctx = coord.load_ctx(b.work)
            return verify.verify(ctx, 0.15), b

    def test_pass_and_fail(self):
        from test_validate import REPORT
        import finalize
        lab = Lab(self.root, week="2026-W43")
        good = finalize.apply(REPORT, ["- 联网搜索：24 次。"])
        self.produce(lab, good)
        (ok, codes, notes), b = self.run_verify(lab)
        self.assertTrue(ok, notes)
        self.assertEqual(b.coord("verified", "--result", "pass")[0], "done")

    def test_numbers_drift_beyond_tolerance_fails(self):
        from test_validate import REPORT
        import finalize
        lab = Lab(self.root, week="2026-W43")
        self.produce(lab, finalize.apply(REPORT, ["- 联网搜索：24 次。"]))
        (ok, codes, _), _ = self.run_verify(lab, hn_points=2000)
        self.assertFalse(ok)
        self.assertIn("GATE_NUMBERS", codes)

    def test_title_checked_against_producer_mode(self):
        # 回溯产出的周报（标题带"回溯版"）由正常模式的定时运行来校验，不能因模式不同判为不通过
        from test_validate import REPORT
        import finalize
        lab = Lab(self.root, week="2026-W43")
        backfill = REPORT.replace("（10/19–10/25）\n", "（10/19–10/25）（回溯版）\n", 1)
        self.produce(lab, finalize.apply(backfill, ["- 联网搜索：24 次。"]), mode="backfill")
        (ok, codes, notes), _ = self.run_verify(lab)
        self.assertTrue(ok, notes)

    def test_degraded_output_triggers_rerun(self):
        from test_validate import REPORT
        import finalize
        lab = Lab(self.root, week="2026-W43")
        # 降级版的标记写在周报元数据里（draft.py --degraded 的产物），publish 据此推导 quality
        degraded = finalize.apply(REPORT, ["- 联网搜索：24 次。"]).replace(
            "---\nweek: 2026-W43\n", "---\nweek: 2026-W43\nquality: degraded\n", 1)
        self.produce(lab, degraded)
        (ok, codes, _), b = self.run_verify(lab)
        self.assertFalse(ok)
        self.assertIn("WRITE_FAILED", codes)
        self.assertEqual(b.coord("verified", "--result", "fail", "--codes", ",".join(codes))[0], "run")

    def test_override_full_on_degraded_report_is_conflict(self):
        # publish 侧已拒绝这种组合；verify 侧防的是旧状态文件与手工写入
        import verify
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "r.md"
            p.write_text("---\nweek: 2026-W43\nquality: degraded\n---\n\n# t\n", encoding="utf-8")
            self.assertTrue(verify.override_conflict({"quality": "full", "gates": {"override": "full"}}, p))
            self.assertFalse(verify.override_conflict({"quality": "degraded"}, p))
            p.write_text("---\nweek: 2026-W43\n---\n\n# t\n", encoding="utf-8")
            self.assertFalse(verify.override_conflict({"quality": "full"}, p))


class PublishGateTest(unittest.TestCase):
    """发布前的质量推导：quality 由门槛结果决定，不再由智能体声明（提案 2.1、2.2）。"""

    def test_derive_matrix(self):
        self.assertEqual(coord.derive_quality(True, False, None), ("full", None))
        self.assertEqual(coord.derive_quality(False, False, None), ("check_failed", None))
        self.assertEqual(coord.derive_quality(True, True, None), ("degraded", None))
        self.assertEqual(coord.derive_quality(False, True, None), ("degraded", None))

    def test_requested_mismatch_is_rejected(self):
        self.assertEqual(coord.derive_quality(False, False, "full"), ("check_failed", "GATE_MISMATCH"))
        self.assertEqual(coord.derive_quality(True, True, "check_failed"), ("degraded", "GATE_MISMATCH"))

    def test_requested_matches(self):
        self.assertEqual(coord.derive_quality(False, False, "check_failed"), ("check_failed", None))
        self.assertEqual(coord.derive_quality(True, False, "full"), ("full", None))

    def test_report_is_degraded(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "r.md"
            p.write_text("---\nweek: 2026-W45\nquality: degraded\n---\n\n# t\n", encoding="utf-8")
            self.assertTrue(coord.report_is_degraded(p))
            # 与 validate.py 同一套 YAML 解析：带引号、行尾带注释都算降级版
            p.write_text('---\nweek: 2026-W45\nquality: "degraded"\n---\n\n# t\n', encoding="utf-8")
            self.assertTrue(coord.report_is_degraded(p))
            p.write_text("---\nweek: 2026-W45\nquality: degraded  # 写作中断\n---\n\n# t\n", encoding="utf-8")
            self.assertTrue(coord.report_is_degraded(p))
            p.write_text("---\nweek: 2026-W45\n---\n\n# t\n", encoding="utf-8")
            self.assertFalse(coord.report_is_degraded(p))
            p.write_text("---\nweek: 2026-W45\nquality: full\n---\n\n# t\n", encoding="utf-8")
            self.assertFalse(coord.report_is_degraded(p))
            p.write_text("没有元数据\n", encoding="utf-8")
            self.assertFalse(coord.report_is_degraded(p))
            self.assertFalse(coord.report_is_degraded(pathlib.Path(d) / "missing.md"))

    def test_gate_script_only_injected_in_test_mode(self):
        injected = dict(CFG, publish={"gate_script": "/tmp/替身.py"})
        self.assertEqual(coord.gate_script(ctx_for(test=False, cfg=injected)).name, "check_run.py")
        self.assertEqual(coord.gate_script(ctx_for(test=True, cfg=injected)).name, "替身.py")
        self.assertEqual(coord.gate_script(ctx_for(test=True)).name, "check_run.py")

    def test_gate_unverified_when_runner_fails(self):
        ctx = ctx_for()
        orig = coord.subprocess.run

        def boom(*a, **kw):
            raise coord.subprocess.TimeoutExpired(cmd="check_run.py", timeout=1)

        coord.subprocess.run = boom
        try:
            ok, codes = coord.publish_gate(ctx)
        finally:
            coord.subprocess.run = orig
        self.assertFalse(ok)
        self.assertEqual(codes, ["GATE_UNVERIFIED"])

    def test_gate_crash_without_codes_is_unverified(self):
        # 崩溃、输出里没有 CODES=：说明没拿到门槛结果（排查脚本/环境），不是「步骤没做」
        ctx = ctx_for()
        orig = coord.subprocess.run
        coord.subprocess.run = lambda *a, **kw: coord.subprocess.CompletedProcess(
            a, 1, stdout="Traceback (most recent call last): ...\n", stderr="")
        try:
            ok, codes = coord.publish_gate(ctx)
        finally:
            coord.subprocess.run = orig
        self.assertEqual((ok, codes), (False, ["GATE_UNVERIFIED"]))

    def test_override_allowed_scope(self):
        # 只认回溯运行：--test 允许指定任意远端（含 origin / 生产 URL），按名字排除挡不住
        self.assertTrue(coord.override_allowed(ctx_for(test=False, mode="backfill")))
        self.assertFalse(coord.override_allowed(ctx_for(test=False, mode="normal")))
        self.assertFalse(coord.override_allowed(ctx_for(test=True, mode="normal", remote="/tmp/sandbox.git")))
        self.assertFalse(coord.override_allowed(ctx_for(test=True, mode="normal", remote="origin")))

    def test_apply_publish_records_gates(self):
        state = coord.empty_state("2026-W45")
        out = coord.apply_publish(state, ctx_for(), T0, "check_failed", ["r.md"], ["GATE_NUMBERS"], None,
                                  {"check_run": "fail", "codes": ["GATE_NUMBERS"]})
        self.assertEqual(out["produced"]["quality"], "check_failed")
        self.assertEqual(out["produced"]["gates"]["check_run"], "fail")
        self.assertEqual(out["produced"]["gates"]["codes"], ["GATE_NUMBERS"])
        self.assertEqual(out["phase"], "produced")
