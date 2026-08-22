"""대시보드 스크린샷 캡처 — Playwright로 자동화"""
import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

OUT_DIR = Path(__file__).parent / "screenshots"
OUT_DIR.mkdir(exist_ok=True)

# ★ 2026-08-22 (WHOLESALE-T3) — 포트를 하드코딩하지 않는다.
#   8000 이 박혀 있어서 다른 포트로 띄운 서버에는 못 붙었다.
#   공모전 제출용 캡처를 뜨려는데 그것 때문에 막혔다.
URL = os.getenv("DASHBOARD_URL", "http://localhost:8000/index.html")


def capture(page, name, delay=2):
    time.sleep(delay)
    path = OUT_DIR / f"{name}.png"
    page.screenshot(path=str(path))
    print(f"  캡처: {path.name}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1,
        )
        page = ctx.new_page()
        page.goto(URL, wait_until="networkidle")
        print("대시보드 로드 완료")

        # 데이터 로드 대기
        time.sleep(5)

        # 1. 전국 전체뷰 (초기 화면)
        capture(page, "01_overview", delay=2)
        print("1) 전국 전체뷰")

        # 2. 대전중앙청과 선택
        page.evaluate("""() => {
            const corp = summaryData.corporations.find(c => c.corp.includes('\uB300\uC804\uC911\uC559\uCCAD\uACFC'));
            if (corp) selectCorp(corp);
        }""")
        capture(page, "02_djc_selected", delay=2)
        print("2) 대전중앙청과 선택")

        # 3. 대전중앙청과 + 딸기 선택
        page.evaluate("""() => {
            selectProduct('\uB538\uAE30');
        }""")
        capture(page, "03_djc_strawberry", delay=2)
        print("3) 대전중앙청과 + 딸기")

        # 4. 서울가락 서울청과
        page.evaluate("""() => {
            const corp = summaryData.corporations.find(c => c.corp.includes('\uC11C\uC6B8\uCCAD\uACFC'));
            if (corp) selectCorp(corp);
        }""")
        capture(page, "04_seoul_garak", delay=2)
        print("4) 서울가락 서울청과")

        # 5. 가격비교 탭
        page.evaluate("""() => {
            switchTab('price');
        }""")
        capture(page, "05_price_tab", delay=2)
        print("5) 가격비교 탭")

        # 6. 1주 기간 전체뷰
        page.evaluate("""() => {
            switchTab('corp');
            selectedCorp = null; selectedCorpData = null; selectedProduct = null;
            document.getElementById('detailPanel').classList.remove('open');
            setPeriod('1w');
        }""")
        capture(page, "06_week_view", delay=4)
        print("6) 1주 합산 뷰")

        # 7. 1달 기간 전체뷰
        page.evaluate("""() => {
            setPeriod('1m');
        }""")
        capture(page, "07_month_view", delay=4)
        print("7) 1달 합산 뷰")

        # 8. 1달 + 대전중앙청과 + 딸기
        page.evaluate("""() => {
            const corp = summaryData.corporations.find(c => c.corp.includes('\uB300\uC804\uC911\uC559\uCCAD\uACFC'));
            if (corp) selectCorp(corp);
        }""")
        time.sleep(1)
        page.evaluate("""() => {
            selectProduct('\uB538\uAE30');
        }""")
        capture(page, "08_month_djc_strawberry", delay=2)
        print("8) 1달 대전중앙청과 딸기")

        browser.close()
        print(f"\n완료! {OUT_DIR}에 8장 캡처됨")


if __name__ == "__main__":
    main()
