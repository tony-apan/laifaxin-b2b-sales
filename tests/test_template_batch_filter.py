# -*- coding: utf-8 -*-
"""回归：批次选取只排除「分组容器」，组内/未分组模板必须计入（48 不能被算成 49，也不能被算成 0）。"""
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from template_batch import collect_batch, is_folder_container

PREFIX = "英语-烘焙-"
GROUP_ID = "6adef6ed12a520e418ee94ac"


def _tpl(i):
    return {"_id": f"id{i:02d}", "name": f"{PREFIX}R{i:02d}-方向-V01-GL", "folder": False, "foid": GROUP_ID}


class CollectBatchTest(unittest.TestCase):
    def test_group_container_named_prefix_is_excluded(self):
        container = {"_id": "groupid", "name": PREFIX, "folder": True, "foid": "0"}
        items = [container] + [_tpl(i) for i in range(1, 49)]
        got = collect_batch(items, PREFIX, 48)
        self.assertEqual(len(got), 48)
        self.assertNotIn("groupid", [x["id"] for x in got])

    def test_grouped_templates_are_counted(self):
        # 真机：组内模板 folder=False/foid=<组id>；离线 fixture 也可能是 folder=True
        grouped_false = {"_id": "g1", "name": PREFIX + "R01-方向-V01-GL", "folder": False, "foid": GROUP_ID}
        grouped_true = {"_id": "g2", "name": PREFIX + "R01-方向-V02-GL", "folder": True, "foid": GROUP_ID}
        ungrouped = {"_id": "g3", "name": PREFIX + "R01-方向-V03-GL", "folder": False, "foid": "0"}
        got = collect_batch([grouped_false, grouped_true, ungrouped], PREFIX, 48)
        self.assertEqual([x["id"] for x in got], ["g1", "g2", "g3"])

    def test_container_detection_requires_name_equal_prefix_and_no_foid(self):
        self.assertTrue(is_folder_container({"name": PREFIX, "folder": True, "foid": "0"}, PREFIX))
        self.assertTrue(is_folder_container({"name": PREFIX, "folder": True}, PREFIX))
        self.assertFalse(is_folder_container({"name": PREFIX, "folder": True, "foid": GROUP_ID}, PREFIX))
        self.assertFalse(is_folder_container({"name": PREFIX + "R01-x-V01-GL", "folder": True}, PREFIX))
        self.assertFalse(is_folder_container({"name": PREFIX, "folder": False, "foid": "0"}, PREFIX))

    def test_stops_at_limit_and_keeps_order(self):
        items = [_tpl(i) for i in range(1, 31)]
        got = collect_batch(items, PREFIX, 5)
        self.assertEqual([x["name"] for x in got],
                         [f"{PREFIX}R{i:02d}-方向-V01-GL" for i in range(1, 6)])

    def test_ignores_other_prefix_and_malformed(self):
        items = [{"_id": "x", "name": "英-皮筏艇-R01-破冰-V01-RT", "folder": False},
                 {"_id": "y", "folder": False},
                 "junk",
                 {"_id": "z", "name": PREFIX + "R01-方向-V01-GL", "folder": False}]
        got = collect_batch(items, PREFIX, 48)
        self.assertEqual([x["id"] for x in got], ["z"])

    def test_empty_inputs(self):
        self.assertEqual(collect_batch([], PREFIX, 48), [])
        self.assertEqual(collect_batch([_tpl(1)], "", 48), [])
        self.assertEqual(collect_batch([_tpl(1)], PREFIX, 0), [])


if __name__ == "__main__":
    unittest.main()
