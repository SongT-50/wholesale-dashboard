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

# ★ 2026-08-28 (WHOLESALE-T3) — 일부만 다시 찍기.
#   CAPTURE_ONLY="09_all_period" 처럼 주면 그 이름만 저장하고 나머지는 건너뛴다.
#   왜 필요한가: 제출 시각화 본문이 캡처 속 수치(2026-08-18 화면의 21,848톤·38,503건)를
#   글로 인용한다. 한 장을 더하려고 전부 다시 찍으면 오늘 데이터로 덮여
#   ### 글과 그림이 어긋난다. 그 어긋남은 PDF 를 눈으로 봐야만 보인다.
#   ⚠️ 화면 조작은 순서대로 그대로 돌린다. 저장만 건너뛴다(상태 의존을 안 깬다).
_ONLY = {s.strip() for s in os.getenv("CAPTURE_ONLY", "").split(",") if s.strip()}


def capture(page, name, delay=2):
    time.sleep(delay)
    if _ONLY and name not in _ONLY:
        print(f"  건너뜀(CAPTURE_ONLY): {name}")
        return
    # ★ 2026-08-22 (IN-T3 제안) — 찍기 전에 익명 모드가 실제로 켜졌는지 확인한다.
    #   왜: 켜진 화면과 안 켜진 화면은 눈으로 구별이 안 된다. 크레딧 줄 한 줄 차이라
    #   캡처 8장을 다 뜬 뒤에야 알게 된다(실제로 오늘 그랬다).
    #   ⇒ 안 켜졌으면 찍지 않고 멈춘다. 잘못 찍은 것을 제출하는 것보다 낫다.
    if "contest=1" in URL:
        ok = page.evaluate("""() => {
            const hasClass = document.body.classList.contains('contest-mode');
            const bar = document.querySelector('.credit-bar');
            const hidden = !bar || getComputedStyle(bar).display === 'none';
            return hasClass && hidden;
        }""")
        if not ok:
            raise SystemExit(
                f"★ 멈춤: {name} — contest 모드가 안 켜졌다.\n"
                "  URL 에 ?contest=1 이 있는데 body.contest-mode 가 없거나 크레딧 줄이 보인다.\n"
                "  이대로 찍으면 회사명·이름·이메일이 제출물에 들어간다."
            )
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

        # 3.5 천안농협(공) — 공모전이 천안시라 천안이 주인공이다
        #   ★ 2026-08-22: 태은이가 직접 찍어 주신 화면이 있었으나 거기엔 회사명·이름·이메일이
        #      찍혀 있었다. 익명 심사라 제출물에 들어가면 안 된다.
        #      ?contest=1 로 띄우면 그 줄이 사라지므로 우리가 다시 뜬다.
        page.evaluate("""() => {
            selectedProduct = null;
            const corp = summaryData.corporations.find(c => c.corp.includes('천안'));
            if (corp) selectCorp(corp);
        }""")
        # ★ 법인을 고르면 지도가 그 자리로 확대된다(zoom 11). 그러면 어디서 오는지가 잘린다.
        #   태은이 지시 = "지도는 전체 지도로 해야 물류 흐름을 제대로 볼 수 있다".
        #   선택은 그대로 두고 시야만 전국으로 되돌린다.
        page.evaluate("""() => {
            deckgl.setProps({ initialViewState: {
                longitude: 127.9, latitude: 36.4, zoom: 7.1,
                pitch: 18, bearing: 0, transitionDuration: 900 } });
        }""")
        capture(page, "035_cheonan", delay=3)
        print("3.5) 천안농협(공)")

        # 3.6 천안 + 복숭아 — 품목까지 좁힌 화면
        #   ★ IN-T3 가 capture_contest.py 에서 먼저 만든 화면이다(복숭아 산지 5곳 패널).
        #      다만 거기선 지도가 천안으로 확대돼 어디서 오는지가 잘렸다.
        #      품목 선택은 그쪽을 따르고 시야는 전국으로 되돌려 합친다.
        #   ⚠️ 8월이라 딸기가 아니라 복숭아다(천안 1위 품목 10.6톤).
        page.evaluate("""() => { selectProduct('복숭아'); }""")
        page.wait_for_timeout(600)
        # ⚠️ 여기만 zoom 8.6 이다. 전국(7.1)로 두면 미거래 산지 라벨 267개가 겹쳐
        #    화면을 덮는다(실측: 글자가 서로 위에 찍혀 못 읽는다).
        #    전국 물류 흐름은 01_overview 가 이미 보여준다. 이 장의 목적은 산지 구성이다.
        page.evaluate("""() => {
            deckgl.setProps({ initialViewState: {
                longitude: 127.6, latitude: 36.5, zoom: 8.6,
                pitch: 18, bearing: 0, transitionDuration: 900 } });
        }""")
        capture(page, "036_cheonan_peach", delay=3)
        print("3.6) 천안 + 복숭아")

        # 원래 상태로 되돌린다 — 안 되돌리면 뒤 캡처가 복숭아에 묶인다
        page.evaluate("""() => { selectedProduct = null; }""")

        # 4. 서울가락 서울청과
        page.evaluate("""() => {
            const corp = summaryData.corporations.find(c => c.corp.includes('\uC11C\uC6B8\uCCAD\uACFC'));
            if (corp) selectCorp(corp);
        }""")
        page.evaluate("""() => {
            deckgl.setProps({ initialViewState: {
                longitude: 127.9, latitude: 36.4, zoom: 7.1,
                pitch: 18, bearing: 0, transitionDuration: 900 } });
        }""")
        capture(page, "04_seoul_garak", delay=3)
        print("4) 서울가락 서울청과")

        # 5. 가격비교 탭
        #   ★ 2026-08-22 (IN-T3 지적) — 탭만 열면 표가 안 나온다. 품목을 골라야 값이 뜬다.
        #      전에는 본문이 "한 표에서 봅니다" 인데 그림엔 표가 없었다. 글과 그림이 어긋났다.
        #      그리고 산지 라벨 274곳이 지도를 덮으므로 끈다. 그래야 법인별 kg당 값이 읽힌다.
        page.evaluate("""() => {
            switchTab('price');
        }""")
        page.wait_for_timeout(800)
        # ⚠️ 이 탭은 selectProduct 가 아니라 selectPriceProduct 다(index.html:2101).
        #    처음에 selectProduct 를 불렀더니 조용히 아무 일도 안 일어났다.
        page.evaluate("""() => { selectPriceProduct('복숭아'); }""")
        page.wait_for_timeout(1000)
        page.evaluate("""() => {
            try { closeOriginPanel(); } catch (e) {}
        }""")
        capture(page, "05_price_tab", delay=3)
        print("5) 가격비교 탭 (복숭아)")

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

        # 9. 전체 기간(2018-01~) 전국뷰 — 천안 공모전 시각화용 (2026-08-28 WHOLESALE-T3)
        #   왜 여기 붙이나: KBS 판(kbs_11_all_period.png)은 회사명·성함이 화면에 있어
        #   공모전 제출본에 그대로 못 넣는다. 같은 화면을 contest 모드로 다시 찍는다.
        #   ⚠️ 104개월 경량본을 읽어서 로딩이 길다. 고정 sleep 으로 기다리지 않는다 —
        #     덜 불러온 화면을 찍으면 「1달치가 전체인 척」하는 판이 나오고,
        #     그 판은 정상 화면과 눈으로 구별이 안 된다.
        page.evaluate("""() => {
            switchTab('corp');
            selectedCorp = null; selectedCorpData = null; selectedProduct = null;
            document.getElementById('detailPanel').classList.remove('open');
            setPeriod('all');
        }""")
        # 양성 대조군: 실제로 전체 기간이 실린 뒤에만 찍는다.
        #   기준 = 합산 일수가 2,000일 넘음. 1일(1) · 1주(7) · 1달(31) · 1년(365) 어느 것도
        #   이 선을 못 넘으므로, 로딩이 덜 끝났으면 이 게이트가 반드시 걸린다.
        #   ⚠️ 화면 라벨이 쓰는 _dc 는 함수 안 지역 변수라 밖에서 못 읽는다(실측).
        #     그 원본인 전역 summaryData.days_count 를 본다.
        try:
            page.wait_for_function(
                "() => typeof summaryData !== 'undefined' && summaryData"
                " && summaryData.days_count > 2000",
                timeout=180000,
            )
        except Exception:
            got = page.evaluate(
                "() => (typeof summaryData === 'undefined' || !summaryData)"
                " ? null : summaryData.days_count"
            )
            raise SystemExit(
                "★ 멈춤: 09_all_period — 전체 기간이 "
                f"안 실렸다(합산 일수={got}).\n"
                "  덜 불러온 화면을 찍으면 눈으로 "
                "구별이 안 된다. 다시 돌려라."
            )
        days = page.evaluate("() => summaryData.days_count")
        # 시야를 전국으로 되돌린다.
        #   ★ 8번에서 법인을 고르면서 지도가 대전으로 확대(zoom 11)됐고,
        #     선택을 풀어도 시야는 안 돌아온다(2026-08-28 실측 — 1차 캡처가 대전 시내였다).
        #   ⚠️ 위 게이트는 「전체 기간이 실렸나」만 본다. 「지도가 전국인가」는 안 본다.
        #     그래서 게이트를 통과한 채로 못 쓸 화면이 나왔다. 눈으로 봐서 잡았다.
        #   ⇒ 게이트를 더 걸지 않고 원인을 없앤다. 시야를 강제로 지정한다.
        #     (capture_kbs.py 의 NATIONWIDE 와 같은 값)
        page.evaluate("""() => { deckgl.setProps({ initialViewState: {
            longitude: 127.9, latitude: 36.4, zoom: 7.1,
            pitch: 18, bearing: 0, transitionDuration: 900 } }); }""")
        capture(page, "09_all_period", delay=5)
        print(f"9) 전체 기간 합산 뷰 ({days:,}일)")

        browser.close()
        print(f"\n완료! {OUT_DIR}에 9장 캡처됨")


if __name__ == "__main__":
    main()
