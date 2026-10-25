"""测试包：让测试进程与它启动的子进程都带测试标记，避免误触生产开工门。"""

import os

os.environ.setdefault("LFX_GATE_TEST_MODE", "1")
os.environ.setdefault("STEP_GATE_TEST_MODE", "1")
