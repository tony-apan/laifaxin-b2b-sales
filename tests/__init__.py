"""测试包：让测试进程与它启动的子进程都带一次性测试票据，避免误触生产开工门。"""

import os

from .gate_env import gate_test_env

os.environ.update(gate_test_env())
os.environ.setdefault("STEP_GATE_TEST_MODE", "1")
