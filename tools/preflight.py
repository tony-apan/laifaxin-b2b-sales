#!/usr/bin/env python3
"""跨平台发布前自检（Windows / macOS / Linux 通用）。

依次执行：文档引用核验 -> 全量测试 -> 规则检查；任一失败返回非零。
这是 tools/preflight.sh 的跨平台等价物：Windows 没有 bash 时用本脚本。

用法：
    python tools/preflight.py        # Windows
    python3 tools/preflight.py       # macOS / Linux
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _utf8_stdout():
    """Windows 控制台默认 GBK，输出中文/emoji 需要显式 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _run_gate(name, cmd):
    print(f"\n===== {name} =====")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    # 即使 rc=0，输出里出现 [FAIL] 也算失败（防规则检查漏退出码）
    failed = proc.returncode != 0 or "[FAIL]" in out
    if not failed:
        keep = ("TOTAL_BAD", "坏链", "坏引用", "缺失同名", "Ran ", "OK", "检查完成")
        for line in out.splitlines():
            if any(k in line for k in keep):
                print(line)
        print(f"✅ {name}：通过")
        return True
    print(out)
    print(f"❌ {name}：失败（上面是完整输出）")
    return False


def main():
    _utf8_stdout()
    print(f"平台：{sys.platform}｜Python：{sys.executable}")
    py = sys.executable
    ok = _run_gate("1/3 文档引用与索引核验", [py, "tools/check_doc_links.py"])
    ok = _run_gate("2/3 全量测试", [py, "-m", "unittest", "discover", "-s", "tests"]) and ok
    bash = shutil.which("bash")
    if bash and sys.platform.startswith("win") and "system32" in bash.lower():
        bash = None  # Windows 的 WSL bash 不算：可能缺 python3/grep，统一走 Python 兜底
    if bash:
        ok = _run_gate("3/3 规则检查", [bash, "tools/check_rules.sh"]) and ok
    else:
        print("\n===== 3/3 规则检查（无 bash：Python 兜底）=====")
        required = ["RULES.md", "INDEX.md", "specs/environment-setup.md",
                    "specs/migration-handoff.md", "specs/operator-profile-sop.md",
                    "specs/product-profile-sop.md", "specs/threshold-method.md",
                    "specs/domain-scale-sop.md", "specs/sequence-config.md"]
        missing = [f for f in required if not (ROOT / f).is_file()]
        if missing:
            print("❌ 缺失规则文件：" + "，".join(missing))
            ok = False
        else:
            print(f"✅ 规则文件齐全（{len(required)} 份）；登录校验需 bash/凭据，已跳过")
            print("提示：无 bash 时 bash 专属测试会自动跳过（测试内按 shutil.which 判定）")
    print("\n提示：INDEX 描述语义抽检可另跑 python tools/check_doc_links.py --sample-index 20")
    if ok:
        print("\n===== PREFLIGHT PASS（可以交付）=====")
        return 0
    print("\n===== PREFLIGHT FAIL（先修再交付）=====")
    return 1


if __name__ == "__main__":
    sys.exit(main())
