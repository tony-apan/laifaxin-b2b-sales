import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class RecoveryContract(unittest.TestCase):
    def text(self, name):
        return (ROOT / name).read_text(encoding="utf-8")

    def test_install_is_bounded(self):
        for name in ("specs/environment-setup.md", "output-templates/S0-install-report.md", "RULES.md"):
            text = self.text(name)
            for term in ("白名单", "非交互", "复查失败", "唯一下一步"):
                self.assertIn(term, text, name)
        self.assertNotIn("需要 sudo 时正常使用 sudo", self.text("specs/environment-setup.md"))
        card = self.text("output-templates/S0-install-report.md")
        self.assertNotIn("我来处理，您什么都不用做", card)
        self.assertIn("我会先确认能否安全处理", card)

    def test_beginner_flow_install_failure_is_bounded(self):
        flow = self.text("specs/beginner-flow.md")
        section = flow.split("安装没通过还没到本屏", 1)[1].split("#### 第 0 屏分流图", 1)[0]
        graph = flow.split("#### 第 0 屏分流图", 1)[1].split("```", 2)[1]
        for text in (section, graph):
            self.assertIn("确认能否安全处理", text)
            for old in ("我来处理，您什么都不用做", "先自己重试一次", "您不用回复，等我消息"):
                self.assertNotIn(old, text)
        for phrase in ("白名单", "非交互", "补装一次并复查", "立即停", "唯一下一步"):
            self.assertIn(phrase, section)

    def test_onboard_failure_copy_matches_card(self):
        card = self.text("output-templates/S0-install-report.md")
        source = self.text("tools/onboard_check.py")
        for phrase in ("有个东西没装好，不是您的问题", "我会先确认能否安全处理"):
            self.assertIn(phrase, card)
            self.assertIn(phrase, source)
        self.assertNotIn("我来处理，您什么都不用做", source)
        self.assertIn("失败立即停并给唯一下一步", source)

    def test_login_fail_closed(self):
        for name in ("RULES.md", "output-templates/S0-connect-failed.md"):
            text = self.text(name)
            for clause in (
                "14 不自动清锁，先核查已有窗口",
                "15/27 停下",
                "未确认不自动继续",
                "26 的安装建议不证明连接",
                "10 可恢复取参",
                "12/23/未知冲突立即停并核查原因",
                "浏览器存在不等于自动连接或连接成功",
            ):
                self.assertIn(clause, text, name)
        for name in ("RULES.md", "output-templates/S0-connect-failed.md"):
            text = self.text(name)
            for field in ("`child_tool`", "`code`", "`stage`", "诊断"):
                self.assertIn(field, text, name)
            self.assertRegex(text, r"15/27 停下[^；。]*确认目标账号[^；。]*空间[^；。]*[；，][^。]*未确认不自动继续")
            self.assertRegex(text, r"10 可恢复取参[^；;。]*[；;，,][^。]*实际校验登录(?:及|和)工作空间")
        text = self.text("tools/browser_login.py")
        self.assertNotIn("三步手动兜底", text)
        self.assertIn("确认目标工作空间", text)

    def test_four_steps_and_registration_separate(self):
        text = self.text("output-templates/T-token-guide.md")
        self.assertIn("可选注册", text)
        steps = re.findall(r"(?m)^([1-4])\. (.*)$", text)
        self.assertEqual(["1", "2", "3", "4"], [number for number, _ in steps])
        for (_, step), terms in zip(steps, (("打开", "web.laifaxin.com", "登录"), ("确认", "工作空间"), ("控制台",), ("粘贴", "回车"))):
            for term in terms:
                self.assertIn(term, step)
        self.assertIn('localStorage.getItem("accesstoken")', text)
        self.assertIn('localStorage.getItem("orgId")', text)

if __name__ == "__main__":
    unittest.main()
