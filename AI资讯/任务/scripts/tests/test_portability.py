import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import check_portability as cp  # noqa: E402

GOOD_PROMPT = """读取 `AI资讯/任务/prompts/weekly.md`，确认第一行是 `<!-- task: ai-weekly -->`，然后按它执行。
用你所在平台的通知方式发给我。
"""


class PortabilityTest(unittest.TestCase):
    def test_repository_is_platform_neutral(self):
        self.assertEqual(cp.run(), [])

    def make_task_dir(self, root: pathlib.Path, prompt: str, manual: str = "", config: str = "") -> pathlib.Path:
        task = root / "AI资讯" / "任务"
        for sub in ("prompts", "templates", "config", "scripts"):
            (task / sub).mkdir(parents=True)
        (task / "prompts" / "routine-prompt.md").write_text(prompt, encoding="utf-8")
        (task / "prompts" / "weekly.md").write_text(manual, encoding="utf-8")
        (task / "config" / "task.yaml").write_text(config, encoding="utf-8")
        (task / "部署指南.md").write_text("Claude Code 用 PushNotification；Codex 用 codex exec。", encoding="utf-8")
        return task

    def test_flags_platform_terms_but_not_deploy_guide(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = self.make_task_dir(
                pathlib.Path(tmp), GOOD_PROMPT,
                manual="用 PushNotification 发送，内容放在 <routine_summary> 里。\n推送到 claude/ai-weekly。\n",
                config="topic: MCP 与工具调用\npr: GitHub MCP\n",
            )
            problems = "\n".join(cp.run(task))
            self.assertIn("weekly.md:1", problems)
            self.assertIn("PushNotification", problems)
            self.assertIn("routine_summary", problems)
            self.assertIn("weekly.md:2", problems)
            self.assertIn("GitHub MCP", problems)
            self.assertNotIn("MCP 与工具调用", problems)  # 内容层面的主题词不算平台绑定
            self.assertNotIn("部署指南", problems)          # 部署指南可以写具体平台

    def test_entry_prompt_must_only_guide(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = self.make_task_dir(pathlib.Path(tmp), "执行手册第 5 步的合并是授权动作。\n")
            problems = "\n".join(cp.run(task))
            self.assertIn("没有指向执行手册", problems)
            self.assertIn("任务标记", problems)
            self.assertIn("第 5 步", problems)

    def test_good_entry_prompt_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = self.make_task_dir(pathlib.Path(tmp), GOOD_PROMPT)
            self.assertEqual(cp.run(task), [])


if __name__ == "__main__":
    unittest.main()
