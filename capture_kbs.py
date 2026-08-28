"""KBS 참고자료용 캡처 (2026-08-28, WHOLESALE-T3)

PIPE #11326 / intelligence/kbs-reference-package-plan-2026-08-28.md 의 4쪽·7쪽.

천안 공모전판(capture_contest.py)과 다른 점:
  ★ 천안은 익명 심사라 ?contest=1 로 회사명까지 감췄다.
    KBS 는 대전중앙청과가 주인공이라 회사명은 나와야 한다.
    ⇒ contest 모드를 안 쓰고, 대신 크레딧 줄에서 개인 성함만 가린다.
    (index.html 555·815 행은 태은이 결재 대기분이라 파일을 안 고친다. 화면에서만 가린다.)

줌 함정 (PIPE 실측 + 035_cheonan 선례):
  법인을 클릭하면 지도가 그 법인으로 확대(zoom 11)돼 산지에서 오는 흐름이 화면 밖으로 나간다.
  ⇒ 선택은 그대로 두고 시야만 전국(7.1)으로 되돌린다. 이미 쓰던 기법이다.

전제: 로컬 서버. DASHBOARD_URL 로 포트를 준다.
실행: DASHBOARD_URL=http://127.0.0.1:8093/index.html python capture_kbs.py
출력: screenshots/kbs_*.png
"""
import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

OUT_DIR = Path(__file__).parent / "screenshots"
OUT_DIR.mkdir(exist_ok=True)
URL = os.getenv("DASHBOARD_URL", "http://127.0.0.1:8093/index.html")

# 83곳 전부가 정산한 날 (2026-08-28 실측: 그런 날이 15일 있다. 그중 거래가 가장 많다)
ALL83_DATE = "2026-07-22"

NATIONWIDE = ("() => { deckgl.setProps({ initialViewState: { longitude: 127.9, "
              "latitude: 36.4, zoom: 7.1, pitch: 18, bearing: 0, "
              "transitionDuration: 900 } }); }")


def mask_personal(page):
    """개인 성함만 가린다. 회사명·도메인은 남긴다(KBS 자료는 우리가 주인공이다)."""
    n = page.evaluate("""() => {
        let n = 0;
        document.querySelectorAll('.credit-bar, .credit-name').forEach(el => {
            if (el.textContent.includes('송태은')) {
                el.textContent = el.textContent.replace(/\\s*송태은/g, '');
                n++;
            }
        });
        document.querySelectorAll('*').forEach(el => {
            if (el.children.length === 0 && el.textContent.includes('송태은')) {
                el.textContent = el.textContent.replace(/\\s*송태은/g, '');
                n++;
            }
        });
        return n;
    }""")
    return n


def shot(page, name, delay=2.5):
    time.sleep(delay)
    left = page.evaluate(
        "() => document.body.innerText.includes('송태은')")
    if left:
        print(f"  [중단] {name}: 화면에 개인 성함이 남아 있다. 안 찍는다.")
        return False
    path = OUT_DIR / f"{name}.png"
    page.screenshot(path=str(path))
    print(f"  저장 {path.name} ({path.stat().st_size/1024:.0f}KB)")
    return True


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080},
                                  device_scale_factor=2)
        page = ctx.new_page()
        page.goto(URL, wait_until="networkidle")
        time.sleep(6)
        print("로드 완료")

        # --- 양성 대조군: 가리기 전에 성함이 실제로 화면에 있었나 ---
        before = page.evaluate(
            "() => document.body.innerText.includes('송태은')")
        masked = mask_personal(page)
        after = page.evaluate(
            "() => document.body.innerText.includes('송태은')")
        print(f"성함 노출 전={before} · 가린 요소 {masked}개 · 후={after}")
        if not before:
            print("[경고] 가리기 전에도 성함이 없다. 대조군이 실패할 수 없는 상태다.")
        if after:
            print("[중단] 가렸는데도 남아 있다.")
            browser.close()
            return

        # === 4쪽 (가) 선택 없는 전국 전체 흐름 ===
        page.evaluate(NATIONWIDE)
        shot(page, "kbs_04a_nationwide_all")
        print("4쪽 가) 전국 전체 흐름 (법인 선택 없음)")

        # === 4쪽 (나) 대전중앙청과로 들어오는 흐름 · 시야는 전국 ===
        page.evaluate("""() => {
            const c = summaryData.corporations.find(
                x => x.corp.includes('대전중앙청과'));
            if (c) selectCorp(c);
        }""")
        page.wait_for_timeout(800)
        page.evaluate(NATIONWIDE)     # 줌 11 로 들어간 것을 전국으로 되돌린다
        mask_personal(page)
        shot(page, "kbs_04b_djc_nationwide", delay=3)
        print("4쪽 나) 대전중앙청과 + 전국 시야")

        # === 7쪽 83곳이 같은 날 정산한 것 ===
        page.evaluate("""() => { closeDetail(); }""")
        page.evaluate(f"""() => {{
            currentDate = '{ALL83_DATE}';
            currentPeriod = '1d';
            document.querySelectorAll('.period-btn').forEach(b =>
                b.classList.toggle('active',
                    b.getAttribute('onclick') === "setPeriod('1d')"));
            return loadForPeriod();
        }}""")
        page.wait_for_timeout(6000)
        page.evaluate(NATIONWIDE)
        mask_personal(page)

        got = page.evaluate("""() => ({
            date: summaryData.date,
            corps: summaryData.corp_count,
            markets: summaryData.market_count,
            trades: summaryData.total_trades
        })""")
        print(f"7쪽 화면 실측: {got}")
        if got["date"] != ALL83_DATE or got["corps"] < 83:
            print(f"[중단] 의도한 날이 아니거나 83곳이 아니다. 안 찍는다.")
        else:
            shot(page, "kbs_07_all83", delay=3)
            print(f"7쪽) {got['date']} · {got['corps']}곳 · {got['trades']:,}건")

        browser.close()


if __name__ == "__main__":
    main()
