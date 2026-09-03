import datetime as dt
import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "post_menu_to_discord.py"
spec = importlib.util.spec_from_file_location("post_menu_to_discord", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


SAMPLE_HTML = """
<html><body>
  <div class="centerBottomBlock">
    <h3 class="blockTitle">今日午餐資訊</h3>
    <div class="blockContent" style="clear:both;">
      <h3>臺南市東區復興國小2026-09-03午餐資訊</h3>
      <div><div><code>本校一律使用國產豬、牛肉食材</code></div></div>
      <div class="mx-auto">
        <div>
          <a data-caption="糙米飯 (主食)" href="#"><img alt="糙米飯"/></a>
        </div>
        <div>
          <a data-caption="家常滷肉 (主菜)" href="#"><img alt="家常滷肉"/></a>
        </div>
        <div>
          <a data-caption="紫菜蛋花湯 (湯品)" href="#"><img alt="紫菜蛋花湯"/></a>
        </div>
      </div>
    </div>
  </div>
</body></html>
"""


class ParseLunchMenuTests(unittest.TestCase):
    def test_parses_dishes_and_note(self):
        menu = module.parse_lunch_menu(SAMPLE_HTML, dt.date(2026, 9, 3))
        self.assertIsNotNone(menu)
        self.assertEqual(menu.note, "本校一律使用國產豬、牛肉食材")
        self.assertEqual(menu.dishes, [
            ("主食", "糙米飯"),
            ("主菜", "家常滷肉"),
            ("湯品", "紫菜蛋花湯"),
        ])

    def test_returns_none_when_no_lunch_block(self):
        menu = module.parse_lunch_menu("<html><body>無午餐資訊</body></html>", dt.date(2026, 9, 3))
        self.assertIsNone(menu)


class NextSchoolDayTests(unittest.TestCase):
    def test_weekday_advances_by_one(self):
        monday = dt.date(2026, 9, 7)  # Monday
        self.assertEqual(module.next_school_day(monday), dt.date(2026, 9, 8))  # Tuesday

    def test_friday_skips_weekend(self):
        friday = dt.date(2026, 9, 4)  # Friday
        self.assertEqual(module.next_school_day(friday), dt.date(2026, 9, 7))  # Monday

    def test_saturday_lands_on_monday(self):
        saturday = dt.date(2026, 9, 5)
        self.assertEqual(module.next_school_day(saturday), dt.date(2026, 9, 7))

    def test_sunday_lands_on_monday(self):
        sunday = dt.date(2026, 9, 6)
        self.assertEqual(module.next_school_day(sunday), dt.date(2026, 9, 7))


class FormatMenuMessageTests(unittest.TestCase):
    def test_format_contains_date_and_dishes(self):
        menu = module.LunchMenu(
            date=dt.date(2026, 9, 3),
            school_name="測試學校2026-09-03午餐資訊",
            note="使用國產食材",
            dishes=[("主食", "白飯"), ("主菜", "雞腿")],
        )
        msg = module.format_menu_message(menu)
        self.assertIn("2026-09-03", msg)
        self.assertIn("週四", msg)
        self.assertIn("白飯", msg)
        self.assertIn("雞腿", msg)
        self.assertIn("使用國產食材", msg)


if __name__ == "__main__":
    unittest.main()
