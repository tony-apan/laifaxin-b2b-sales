import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from profile_utils import validate_nickname


class NicknameHardeningTest(unittest.TestCase):
    def test_rejects_mixed_latin_and_cjk_suffixes(self):
        for value in (
            "Tony-包装厂",
            "Iris保温杯",
            "Leo贸易",
            "Amy宠物食品",
        ):
            with self.subTest(value=value):
                ok, reason = validate_nickname(value)
                self.assertFalse(ok)
                self.assertIn("混合英文与中文", reason)

    def test_rejects_pure_cjk_company_or_product_suffixes(self):
        for value in ("王-包装厂", "张伟食品包装", "李保温杯", "王建材", "老王物流"):
            with self.subTest(value=value):
                self.assertFalse(validate_nickname(value)[0])

    def test_keeps_normal_personal_names(self):
        for value in ("Tony", "Iris", "Jean-Pierre", "老王", "张伟", "欧阳娜娜"):
            with self.subTest(value=value):
                self.assertEqual(validate_nickname(value), (True, ""))


if __name__ == "__main__":
    unittest.main()
