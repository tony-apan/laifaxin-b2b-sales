#!/usr/bin/env python3
"""隐私护栏（规则/功能/清单/内容/环境五层）：真实运行档案必须留在本机，进仓的 runs 文件只允许「模板清单 + 导航卡」。

runs/ 下放的是运营方真实客户档案（公司名/联系人/邮箱/成单信息）。2026-09-02 对抗审查
P0-4 之后靠 .gitignore 挡；2026-10-27 三轮独立审查先后证明前几版有可复现的假绿，
本版按审查结论逐条收口：

1) 规则层：.gitignore 里凡是作用于 runs/ 树的规则，只允许 runs/* ；凡是 ! 放行规则，
   无论写不写 runs 字样，只允许 !runs/INDEX.md 与 !runs/_template；行首空白判红
   （Git 把行首空格当字面量，规则会静默失效）；! 之后的前导 / 与目录尾 / 视为同义。
   runs/.gitignore（嵌套忽略文件）一律禁止，否则根解析器看不到的放行规则会绕过检查。
2) 功能层：git check-ignore --no-index（默认模式查索引，已跟踪文件永远返回「未忽略」，
   v1 的功能断言就是这样空转的）；rc 非 0/1 一律抛错。探针取固定名 + 磁盘上真实存在的
   runs/<运营方>/ 目录，后者能在本地 pre-commit 抓到 !tony/ 这类定点放行。
3) 清单层：索引里的 runs 文件必须与 EXPECTED_TRACKED 逐字一致；合法新增模板要显式登记，
   报错文案区分「模板新增」与「疑似真实档案」。
4) 内容层：进仓的 runs 文件里不得出现非示例域名的邮箱（模板当前零 @），
   堵住「把客户资料填进模板再提交」这条最可能的误操作。
5) 环境层：只清空 core.excludesFile（-c core.excludesFile=），避免用户全局 *.md 规则假红，
   同时保留用户已配置的 safe.directory；git 缺失或报错一律 FAIL，不用跳过把护栏静默关掉；
   只有本目录不是独立 git 仓库（发布包/被 vendored 进外层仓）才 skip。

已知边界（UNKNOWN）：历史提交里已泄露的数据只能审计、不能撤回；内容层只识别邮箱格式，
混淆写法（buyer [at] acme.com）与电话/公司名不在覆盖内；已登记模板文件被改写时，
本测试只做邮箱扫描，其余改动靠 diff 评审。
"""

import os
import re
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GITIGNORE = ROOT / ".gitignore"
RUNS = ROOT / "runs"

REQUIRED_IGNORE = "runs/*"
ALLOWED_RULES = frozenset({REQUIRED_IGNORE, "!runs/INDEX.md", "!runs/_template"})

FIXED_REAL_PROBES = [
    "runs/__privacy_probe__/operation-record.md",
    "runs/__privacy_probe__/nested/deep.md",
    "runs/_test-operator/product/product-profile.md",
    "runs/__privacy_probe__.tsv",
    "runs/__privacy_probe__.xlsx",
]
TEMPLATE_PROBES = [
    "runs/INDEX.md",
    "runs/_template/product-profile.md",
    "runs/_template/__privacy_probe__.md",
    "runs/_template/segments/INDEX.md",
]

EXPECTED_TRACKED = [
    "runs/INDEX.md",
    "runs/_template/INDEX.md",
    "runs/_template/README.md",
    "runs/_template/audit-manifest.json",
    "runs/_template/compliance-check.json",
    "runs/_template/evidence.json",
    "runs/_template/inquiries.tsv",
    "runs/_template/operation-record.md",
    "runs/_template/ops-log.tsv",
    "runs/_template/product-profile.md",
    "runs/_template/recovery-manifest.json",
    "runs/_template/reflection.md",
    "runs/_template/segments.md",
    "runs/_template/segments/INDEX.md",
    "runs/_template/segments/README.md",
    "runs/_template/segments/S01-segment-profile-template.md",
    "runs/_template/templates.md",
    "runs/_template/verification-manifest.json",
    "runs/_template/website-profile-candidate.json",
    "runs/_template/website-profile-patch.json",
]

# 只认 RFC 2606 保留域与自有域名的占位写法；真实客户可能用 yourcompany.com 这类域名，不能放行
EXAMPLE_DOMAINS = ("example.com", "example.org", "example.net", "laifa.xin")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})")

# 只把 core.excludesFile 清空（防用户全局 *.md 规则造成假红）；
# 不覆盖 GIT_CONFIG_GLOBAL/SYSTEM，否则会丢掉用户已配置的 safe.directory，异主仓库下整片假红。
GIT_ENV = dict(os.environ)


def _git(*args):
    return subprocess.run(
        ["git", "-c", "core.excludesFile=", *args], cwd=str(ROOT),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=GIT_ENV,
    )


def _git_rc(*args):
    return _git(*args).returncode


_TMP_GITDIR = None


def _isolation_gitdir():
    """临时 gitdir：让 check-ignore 读 ROOT/.gitignore 与 ROOT 下规则，但不读仓库本地 .git/info/exclude。

    否则用户/工具在 info/exclude 里写 *.md 会让模板功能断言假红（.gitignore 本身没问题）。
    """
    global _TMP_GITDIR
    if _TMP_GITDIR is None:
        _TMP_GITDIR = tempfile.mkdtemp(prefix="runs-privacy-git-")
        subprocess.run(["git", "init", "-q", _TMP_GITDIR], check=True,
                       capture_output=True, text=True, env=GIT_ENV)
    return os.path.join(_TMP_GITDIR, ".git")


def _ignored(path):
    """--no-index 不查索引：0=命中忽略，1=未命中，其它一律当错误抛出（不掩盖 128）。"""
    proc = subprocess.run(
        ["git", "-c", "core.excludesFile=", f"--git-dir={_isolation_gitdir()}",
         f"--work-tree={ROOT}", "check-ignore", "-q", "--no-index", "--", path],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=GIT_ENV,
    )
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    raise AssertionError(
        f"git check-ignore 出错（rc={proc.returncode}）路径 {path}：{proc.stderr.strip()[:200]}"
    )


def _norm(rule):
    """把规则规范化到可比较形态：! 前导 / 与目录尾 / 视为同义；忽略规则必须精确是 runs/*。

    忽略规则不归一化尾斜杠：runs/*/ 只挡目录、不挡 runs/ 顶层文件，二者不等价，
    不能因为写法相近就放行。
    """
    neg = rule.startswith("!")
    body = rule[1:] if neg else rule
    body = body.lstrip("/")
    if neg:
        body = body.rstrip("/")
    return ("!" if neg else "") + body


class RunsPrivacyGuardTest(unittest.TestCase):
    def setUp(self):
        if shutil.which("git") is None:
            self.fail("找不到 git 可执行文件：隐私护栏无法验证，不允许静默跳过")
        top = _git("rev-parse", "--show-toplevel")
        if top.returncode != 0:
            if "not a git repository" in top.stderr.lower() and not (ROOT / ".git").exists():
                self.skipTest("本目录是发布包解压目录（无 .git），隐私护栏不适用")
            self.fail(f"git rev-parse 失败（rc={top.returncode}）：{top.stderr.strip()[:200]}")
        if Path(top.stdout.strip()).resolve() != ROOT:
            self.skipTest(f"本目录不是独立 git 仓库（外层仓库 {top.stdout.strip()}），隐私护栏不适用")

    # ---------- 规则层 ----------

    def test_gitignore_rules_are_exact(self):
        if not GITIGNORE.exists():
            self.fail("缺少 .gitignore：真实运行档案会直接进公开仓")
        problems = []
        seen = []
        for lineno, raw in enumerate(GITIGNORE.read_text(encoding="utf-8").splitlines(), 1):
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if raw[:1] in (" ", "\t"):
                problems.append(f".gitignore:{lineno} 行首有空白（Git 按字面量处理，规则会失效）：{raw!r}")
            norm = _norm(stripped)
            body = norm.lstrip("!")
            touches_runs = body == "runs" or body.startswith("runs/")
            if norm.startswith("!") or touches_runs:
                seen.append((lineno, stripped, norm))
                if norm not in ALLOWED_RULES:
                    problems.append(
                        f".gitignore:{lineno} 出现未登记的存放行 {stripped!r}"
                        f"（只允许 {sorted(ALLOWED_RULES)}）"
                    )
        norms = [norm for _, _, norm in seen]
        if REQUIRED_IGNORE not in norms:
            problems.append(f".gitignore 缺少必需规则 {REQUIRED_IGNORE!r}")
        for need in ("!runs/INDEX.md", "!runs/_template"):
            if need not in norms:
                problems.append(f".gitignore 缺少必需放行规则 {need!r}")
        self.assertEqual([], problems, "runs 忽略规则不合规：" + "; ".join(problems))

    def test_no_nested_gitignore_under_runs(self):
        nested = [p for p in RUNS.rglob(".gitignore")] if RUNS.exists() else []
        rel = [str(p.relative_to(ROOT)) for p in nested]
        self.assertEqual([], rel, f"runs/ 下不得有嵌套 .gitignore（会绕过本检查）：{rel}")

    # ---------- 功能层 ----------

    def test_real_run_paths_are_ignored(self):
        probes = list(FIXED_REAL_PROBES)
        if RUNS.exists():
            for child in RUNS.iterdir():
                if child.is_dir() and child.name != "_template":
                    probes.append(f"runs/{child.name}/operation-record.md")
                elif child.is_file() and child.name != "INDEX.md":
                    probes.append(f"runs/{child.name}")
        leaks = [p for p in probes if not _ignored(p)]
        self.assertEqual([], leaks, f"以下真实运行档案路径未被忽略，会被提交进公开仓：{leaks}")

    def test_template_paths_are_not_ignored(self):
        blocked = [p for p in TEMPLATE_PROBES if _ignored(p)]
        self.assertEqual([], blocked, f"以下模板路径被忽略了，新用户拿不到模板：{blocked}")

    # ---------- 清单层 ----------

    def test_tracked_runs_files_are_exact_template_inventory(self):
        proc = _git("ls-files", "-z", "--", "runs")
        self.assertEqual(0, proc.returncode, f"git ls-files 失败：{proc.stderr.strip()[:200]}")
        tracked = sorted(p for p in proc.stdout.split("\0") if p)
        extra = sorted(set(tracked) - set(EXPECTED_TRACKED))
        missing = sorted(set(EXPECTED_TRACKED) - set(tracked))
        if not extra and not missing:
            return
        msg = "runs 进仓文件与模板清单不一致："
        if extra:
            msg += f"多出 {extra}（若为合法模板新增，请同步更新 EXPECTED_TRACKED；否则疑为真实档案）；"
        if missing:
            msg += f"缺少 {missing}（模板丢失）"
        self.fail(msg)

    # ---------- 内容层 ----------

    def test_tracked_runs_files_have_no_real_contact_data(self):
        proc = _git("ls-files", "-z", "--", "runs")
        tracked = [p for p in proc.stdout.split("\0") if p]
        leaks = []
        unreadable = []
        for rel in tracked:
            # 读索引而不是工作树：git commit 提交的是索引，工作树可能已被还原成干净内容
            blob = _git("show", f":{rel}")
            if blob.returncode != 0:
                unreadable.append(f"{rel}（rc={blob.returncode}）")
                continue
            for lineno, line in enumerate(blob.stdout.splitlines(), 1):
                for domain in EMAIL_RE.findall(line):
                    low = domain.lower()
                    if not any(low == d or low.endswith("." + d) for d in EXAMPLE_DOMAINS):
                        leaks.append(f"{rel}:{lineno} 域名 {domain}")
        self.assertEqual([], unreadable, f"读不到索引内容（无法验证，按失败处理）：{unreadable}")
        self.assertEqual([], leaks, f"进仓的 runs 文件里出现疑似真实联系邮箱：{leaks}")


if __name__ == "__main__":
    unittest.main()
