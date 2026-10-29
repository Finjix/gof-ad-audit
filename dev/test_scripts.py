"""gof-ad-audit 脚本的自检：python -m unittest discover -s dev -p "test_*.py"（在仓库根目录）。

text_check 的两份样例：bad.txt 每行是一个真拒审过的写法，good.txt 是合规写法。改了 standard.md 或 text_check.py 以后跑。
frames 要本机有 ffmpeg，没有就跳过那一项。
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "plugins", "gof-ad-audit", "skills", "gof-ad-audit", "scripts")
TESTS = os.path.join(ROOT, "dev", "tests")
UTF8 = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def script(name):
    return os.path.join(SCRIPTS, f"{name}.py")


def run(name, *args, env=None, cwd=None):
    return subprocess.run([sys.executable, script(name), *args], capture_output=True, text=True, encoding="utf-8",
                          env={**UTF8, **(env or {})}, cwd=cwd)


def load(name):
    spec = importlib.util.spec_from_file_location(name, script(name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TextCheck(unittest.TestCase):
    def counts(self, path):
        hits = json.loads(run("text_check", "--json", path).stdout)
        return {level: sum(1 for h in hits if h["level"] == level) for level in ("红线", "必改", "提醒")}

    def test_rejected_wordings_are_caught(self):
        self.assertGreaterEqual(self.counts(os.path.join(TESTS, "bad.txt"))["必改"], 26)
        self.assertIn("必改 26", run("text_check", os.path.join(TESTS, "bad.txt")).stdout.splitlines()[0])

    def test_compliant_wordings_pass(self):
        counts = self.counts(os.path.join(TESTS, "good.txt"))
        self.assertEqual((counts["红线"], counts["必改"]), (0, 0))

    def test_stdin(self):
        out = subprocess.run([sys.executable, script("text_check"), "--json", "-"], input="零氪也能玩", capture_output=True,
                             text=True, encoding="utf-8", env=UTF8).stdout
        self.assertTrue(any(h["level"] == "必改" for h in json.loads(out)))


class ExtractSrt(unittest.TestCase):
    def test_takes_the_srt_block_of_the_report(self):
        with tempfile.TemporaryDirectory() as d:
            report = os.path.join(d, "report.md")
            with open(report, "w", encoding="utf-8") as f:
                f.write("[模型] x\n\n## 一\n```srt\n1\n00:00:01,000 --> 00:00:02,000\n字幕：不用氪金\n\n2\n00:00:02,000 --> 00:00:03,000\n口播：全球3亿\n```\n## 二\n无\n")
            out = run("extract_srt", report, os.path.join(d, "subs.srt"))
            self.assertEqual(out.returncode, 0)
            self.assertIn("2 条", out.stdout)
            with open(os.path.join(d, "subs.srt"), encoding="utf-8") as f:
                self.assertIn("口播：全球3亿", f.read())
            with open(report, "w", encoding="utf-8") as f:
                f.write("没有代码块")
            self.assertNotEqual(run("extract_srt", report, os.path.join(d, "x.srt")).returncode, 0)


class Sampling(unittest.TestCase):
    def test_long_videos_lower_the_frame_rate_to_stay_in_budget(self):
        plan = load("analyze_video").plan_sampling
        self.assertEqual(plan(30, None, None)[:2], (4, True))
        fps, hi, _ = plan(1800, None, None)
        self.assertTrue(fps < 4 and 1800 * (fps * (258 if hi else 66) + 32) <= 700_000)
        self.assertFalse(plan(7200, None, None)[1], "very long ones fall back to low resolution")
        self.assertEqual(plan(None, None, None)[:2], (4, True))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "没有 ffmpeg")
class Frames(unittest.TestCase):
    def test_frames_of_a_stretch_are_written_with_their_time(self):
        with tempfile.TemporaryDirectory() as d:
            video = os.path.join(d, "v.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=3",
                            "-pix_fmt", "yuv420p", video], check=True)
            out = run("frames", video, "--start", "1", "--end", "2", "--fps", "4", "--out", os.path.join(d, "f"))
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            names = sorted(os.listdir(os.path.join(d, "f")))
            self.assertEqual(names[0], "f_0001.00s.jpg")
            self.assertEqual(len(names), 4)
            self.assertNotEqual(run("frames", video, "--fps", "30", "--max-frames", "10").returncode, 0, "too many frames are refused")


class WorkDir(unittest.TestCase):
    def test_under_lark_agent_the_work_goes_to_the_users_own_folder_and_old_work_is_removed(self):
        with tempfile.TemporaryDirectory() as user:
            work = os.path.join(user, "gof-ad-audit", "work")
            old = os.path.join(work, "20260101-000000_旧片")
            os.makedirs(old)
            stale = time.time() - 8 * 86400
            os.utime(old, (stale, stale))
            out = run("workdir", "新片:1", env={"LARK_AGENT_USER_DIR": user})
            made = json.loads(out.stdout)["dir"]
            self.assertTrue(os.path.isdir(made) and made.startswith(work) and made.endswith("_新片_1"))
            self.assertFalse(os.path.exists(old))

    def test_without_a_host_it_is_a_folder_in_the_current_directory(self):
        with tempfile.TemporaryDirectory() as d:
            env = {k: v for k, v in UTF8.items() if k != "LARK_AGENT_USER_DIR"}
            out = subprocess.run([sys.executable, script("workdir"), "片"], capture_output=True, text=True, encoding="utf-8", env=env, cwd=d)
            self.assertEqual(json.loads(out.stdout)["dir"], os.path.join(os.path.realpath(d), "审核_片"))


class Feishu(unittest.TestCase):
    def test_runs_the_feishu_plugins_command_with_this_environment(self):
        with tempfile.TemporaryDirectory() as d:
            fake = os.path.join(d, "feishu.mjs")
            with open(fake, "w", encoding="utf-8") as f:
                f.write("process.stdout.write(JSON.stringify({argv: process.argv.slice(2), user: process.env.LARK_AGENT_USER_DIR})); process.exitCode = 2;")
            out = run("feishu", "doc", "fetch", "--url", "https://x.feishu.cn/docx/ABCDEFGH", env={"FEISHU_PLUGIN": fake, "LARK_AGENT_USER_DIR": d})
            self.assertEqual(out.returncode, 2, "its exit code comes along")
            self.assertEqual(json.loads(out.stdout), {"argv": ["doc", "fetch", "--url", "https://x.feishu.cn/docx/ABCDEFGH"], "user": d})

    def test_finds_the_plugin_in_codex_cache_newest_version_first(self):
        locate = load("feishu").locate
        with tempfile.TemporaryDirectory() as cache:
            def entry(*parts):
                path = os.path.join(cache, *parts, "server", "dist", "feishu.mjs")
                os.makedirs(os.path.dirname(path))
                open(path, "w").close()
                return path
            entry("lark-agent", "feishu", "1.2.0")
            newest = entry("lark-agent", "feishu", "1.10.0")
            here = os.path.join(cache, "lark-agent", "gof-ad-audit", "1.1.0", "skills", "gof-ad-audit", "scripts")
            os.makedirs(here)
            self.assertEqual(locate({}, here), newest)
            other = os.path.join(cache, "gof-ad-audit", "gof-ad-audit", "1.1.0", "skills", "gof-ad-audit", "scripts")
            os.makedirs(other)
            self.assertEqual(locate({}, other), newest, "another marketplace's copy is found too")

    def test_says_so_when_the_plugin_is_missing(self):
        with tempfile.TemporaryDirectory() as d:
            missing = os.path.join(d, "nope.mjs")
            out = run("feishu", "login", "check", env={"FEISHU_PLUGIN": missing})
            self.assertNotEqual(out.returncode, 0)
            self.assertIn("FEISHU_PLUGIN", out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
