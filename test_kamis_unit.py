# -*- coding: utf-8 -*-
"""KAMIS 단위 판별 대조군.

무엇을 지키나 = `avg_price_kg` 에 '원/kg' 을 붙여도 되는 행만 붙는가.

대조군 출처 (내가 만든 숫자가 아니다)
  - PIPE 판정   = intelligence/RESULT-kamis-price-unit-verdict-2026-08-29.md
  - WI 23일 실측 = intelligence/RESULT-kamis-unit-23day-replication-2026-08-29.md (bus #12244)
  WI 가 코드를 안 건드리고 기대값만 넘겼다 = 생성자와 평가자가 다르다.

★ 반증자를 양쪽으로 건다
  - 미탐 쪽: `kg(그물망 3포기)` 46건이 통과하면 실패 (startswith 함정)
  - 과잉 쪽: `unit=kg / size=1` 713건이나 `g` 581건이 깎이면 실패
    ⇒ 이 둘이 없으면 「전부 무게 아님」으로 찍어도 통과하는 시험이 된다.
"""
import glob
import io
import json
import os
import sys
import unittest

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from preprocess import _is_by_weight  # 프로덕션 함수 그대로

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GLOB = os.path.join(ROOT, "daily-wholesale-analysis", "data", "price_change_2026-08*.json")

# WI #12244 기대값 (2026-08 23파일 5,335행)
EXP = {"rows": 5335, "files": 23, "by_weight": 4350, "unknown": 985,
       "kg_size1": 713, "g": 581, "trap": 46}


def load():
    rows = []
    for f in sorted(glob.glob(GLOB)):
        with io.open(f, encoding="utf-8") as fh:
            rows.extend(json.load(fh)["items"])
    return rows


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = sorted(glob.glob(GLOB))
        cls.rows = load()

    # --- 계측기부터 대조군에 태운다 ---
    def test_01_fixture_present(self):
        """표본이 비어 있으면 아래 시험이 전부 공허하게 통과한다."""
        self.assertEqual(len(self.files), EXP["files"])
        self.assertEqual(len(self.rows), EXP["rows"])

    def test_02_trap_row_exists(self):
        """`kg(그물망 3포기)` 가 실제로 있어야 미탐 시험이 성립한다."""
        n = sum(1 for r in self.rows if (r.get("unit") or "").strip() == "kg(그물망 3포기)")
        self.assertEqual(n, EXP["trap"])

    # --- 본 판정 ---
    def test_03_by_weight_count(self):
        n = sum(1 for r in self.rows if _is_by_weight(r.get("unit")))
        self.assertEqual(n, EXP["by_weight"])

    def test_04_unknown_count(self):
        n = sum(1 for r in self.rows if not _is_by_weight(r.get("unit")))
        self.assertEqual(n, EXP["unknown"])

    # --- 반증자: 미탐 쪽 ---
    def test_05_trap_is_rejected(self):
        """### startswith('kg') 로 쓰면 여기서 죽는다."""
        self.assertFalse(_is_by_weight("kg(그물망 3포기)"))

    # --- 반증자: 과잉 쪽 (이게 없으면 「전부 아님」도 통과한다) ---
    def test_06_kg_size1_not_dropped(self):
        """unit=kg size=1 인 713건은 원/kg 이 맞다. 0 이 되면 과잉이다."""
        n = sum(1 for r in self.rows
                if (r.get("unit") or "").strip() == "kg"
                and str(r.get("unit_size") or "").strip() == "1")
        self.assertEqual(n, EXP["kg_size1"])
        self.assertTrue(all(_is_by_weight(r.get("unit")) for r in self.rows
                            if (r.get("unit") or "").strip() == "kg"))

    def test_07_g_not_dropped(self):
        """g 581건은 100% 환산돼 있다. 깎이면 과잉이다."""
        n = sum(1 for r in self.rows if (r.get("unit") or "").strip() == "g")
        self.assertEqual(n, EXP["g"])
        self.assertTrue(_is_by_weight("g"))

    # --- 경계 ---
    def test_08_non_weight_units(self):
        for u in ("개", "마리", "포기", "속", "손"):
            self.assertFalse(_is_by_weight(u), u)

    def test_09_whitespace_and_unknown(self):
        self.assertTrue(_is_by_weight(" kg "))
        self.assertFalse(_is_by_weight("KG"))  # 원자료는 소문자다. 대문자가 오면 알아야 한다
        # ### 「모른다」는 None 이지 False 가 아니다
        self.assertIsNone(_is_by_weight(None))
        self.assertIsNone(_is_by_weight(""))
        self.assertIsNone(_is_by_weight("   "))

    def test_11_trend_is_unknown_not_false(self):
        """### 과잉 반증자 — 2026-08-29 에 실제로 걸린 형태.

        price_trend 원자료는 unit 칸이 있는데 전부 비어 있다.
        그걸 False 로 뭉개면 trends 342행이 **전부** 「단위주의」로 찍히고
        진짜 44건이 소음에 묻힌다. 여기서 죽어야 한다.
        """
        tg = os.path.join(ROOT, "daily-wholesale-analysis", "data", "price_trend_2026-08*.json")
        fs = sorted(glob.glob(tg))
        self.assertEqual(len(fs), 23, "표본이 없으면 이 시험은 공허하다")
        rows = []
        for f in fs:
            with io.open(f, encoding="utf-8") as fh:
                rows.extend(json.load(fh)["items"])
        self.assertEqual(len(rows), 6802)
        self.assertTrue(all((r.get("unit") or "").strip() == "" for r in rows),
                        "trend 에 unit 이 채워지기 시작했다 — 이 시험의 전제가 바뀌었다")
        self.assertTrue(all(_is_by_weight(r.get("unit")) is None for r in rows),
                        "### 모른다를 아니다로 뭉갰다")

    def test_12_screen_only_warns_on_explicit_false(self):
        """화면은 `=== false` 로만 경고해야 한다. falsy 로 쓰면 None 도 걸린다."""
        html = io.open(os.path.join(ROOT, "wholesale-dashboard", "index.html"),
                       encoding="utf-8").read()
        self.assertIn("k.by_weight === false", html)
        self.assertNotIn("!k.by_weight", html)

    def test_10_pipeline_passes_unit(self):
        """### 판별만 맞고 화면에 안 넘어가면 아무것도 안 고친 것이다."""
        import re
        src = io.open(os.path.join(ROOT, "wholesale-dashboard", "preprocess.py"),
                      encoding="utf-8").read()
        for key in ('"unit"', '"unit_size"', '"by_weight"'):
            self.assertGreaterEqual(src.count(key), 2, key + " 가 두 경로(change/trend)에 다 없다")
        html = io.open(os.path.join(ROOT, "wholesale-dashboard", "index.html"),
                       encoding="utf-8").read()
        self.assertIn("kamisPriceLabel", html)
        self.assertNotIn("k.price_kg.toLocaleString()+'원/kg'", html,
                         "화면이 아직 무조건 원/kg 을 붙인다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
