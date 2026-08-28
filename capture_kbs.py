"""KBS 참고자료용 캡처 (2026-08-28, WHOLESALE-T3)

PIPE #11326 #11332 / intelligence/kbs-reference-package-plan-2026-08-28.md

천안 공모전판(capture_contest.py)과 다른 점:
  ★ 천안은 익명 심사라 ?contest=1 로 회사명까지 감췄다.
    KBS 는 대전중앙청과가 주인공이라 회사명은 나와야 한다.
    ⇒ contest 모드를 안 쓰고, 대신 크레딧 줄에서 개인 성함만 가린다.
    (index.html 555·815 행은 태은이 결재 대기분이라 파일을 안 고친다. 화면에서만 가린다.)

줌 함정 (PIPE 실측 + 035_cheonan 선례):
  법인을 클릭하면 지도가 그 법인으로 확대(zoom 11)돼 산지에서 오는 흐름이 화면 밖으로 나간다.
  ⇒ 선택은 그대로 두고 시야만 전국(7.1)으로 되돌린다.

태은이 수정 지시 (2026-08-28, PIPE #11332):
  ★ 뭐든지 선택한 것은 좀 눈에 띄는 것이면 좋겠구  -> 4 5 6 전부에 걸린다
  ★ 6쪽 품목은 복숭아. 어디서 오는지 화살표가 들어가게

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
PRODUCT = "복숭아"          # 태은이 지시 (PIPE #11332)

NATIONWIDE = ("() => { deckgl.setProps({ initialViewState: { longitude: 127.9, "
              "latitude: 36.4, zoom: 7.1, pitch: 18, bearing: 0, "
              "transitionDuration: 900 } }); }")


def mask_personal(page):
    """개인 성함만 가린다. 회사명·도메인은 남긴다(KBS 자료는 우리가 주인공이다)."""
    return page.evaluate("""() => {
        let n = 0;
        document.querySelectorAll('*').forEach(el => {
            if (el.children.length === 0 && el.textContent.includes('송태은')) {
                el.textContent = el.textContent.replace(/\\s*송태은/g, '');
                n++;
            }
        });
        return n;
    }""")


def shot(page, name, delay=2.5):
    time.sleep(delay)
    mask_personal(page)
    if page.evaluate("() => document.body.innerText.includes('송태은')"):
        print(f"  [중단] {name}: 화면에 개인 성함이 남아 있다. 안 찍는다.")
        return False
    path = OUT_DIR / f"{name}.png"
    page.screenshot(path=str(path))
    print(f"  저장 {path.name} ({path.stat().st_size/1024:.0f}KB)")
    return True


def select_corp(page, keyword):
    return page.evaluate(f"""() => {{
        const c = summaryData.corporations.find(x => x.corp.includes('{keyword}'));
        if (!c) return null;
        selectCorp(c);
        return c.corp;
    }}""")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080},
                                  device_scale_factor=2)
        page = ctx.new_page()
        page.goto(URL, wait_until="networkidle")
        time.sleep(6)

        base = page.evaluate("""() => ({
            date: summaryData.date, corps: summaryData.corp_count,
            trades: summaryData.total_trades })""")
        print(f"로드 완료 · 기본 화면 {base}")

        # --- 양성 대조군: 가리기 전에 성함이 실제로 화면에 있었나 ---
        before = page.evaluate("() => document.body.innerText.includes('송태은')")
        masked = mask_personal(page)
        after = page.evaluate("() => document.body.innerText.includes('송태은')")
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
        got = select_corp(page, "대전중앙청과")
        page.wait_for_timeout(900)
        page.evaluate(NATIONWIDE)     # 줌 11 로 들어간 것을 전국으로 되돌린다
        shot(page, "kbs_04b_djc_nationwide", delay=3)
        print(f"4쪽 나) {got} + 전국 시야")

        # === 5쪽 대전중앙청과의 하루 (선택 상태가 도드라지게) ===
        # 🔴 4b 는 전국 시야다. 여기서 시야를 안 바꾸면 4b 와 똑같은 그림이 나온다.
        #    실제로 처음에 그랬다(파일 크기까지 같았다). 5쪽은 우리 회사 클로즈업이 목적이라
        #    대전노은으로 줌인한다. 4쪽=전국 · 5쪽=우리 회사 로 두 장이 갈린다.
        page.evaluate("""() => { deckgl.setProps({ initialViewState: {
            longitude: 127.3203, latitude: 36.3743, zoom: 9.4,
            pitch: 18, bearing: 0, transitionDuration: 900 } }); }""")
        djc = page.evaluate("""() => {
            const c = summaryData.corporations.find(x => x.corp.includes('대전중앙청과'));
            return c ? {corp: c.corp, qty: Math.round(c.total_qty/1000),
                        trades: c.trades, products: (c.products||[]).length} : null;
        }""")
        shot(page, "kbs_05_djc_day", delay=3)
        print(f"5쪽) 대전중앙청과의 하루 {djc}")

        # === 6쪽 복숭아까지 좁힌 화면 (태은이 지시) ===
        has = page.evaluate(f"""() => {{
            const c = summaryData.corporations.find(x => x.corp.includes('대전중앙청과'));
            return !!(c && (c.products||[]).find(p => p.name === '{PRODUCT}'));
        }}""")
        if not has:
            print(f"6쪽) [건너뜀] 이 날 대전중앙청과에 {PRODUCT} 가 없다")
        else:
            page.evaluate(f"""() => {{ selectProduct('{PRODUCT}'); }}""")
            page.wait_for_timeout(900)
            # 🔴 여기만 zoom 8.6 이다. capture_screenshots.py 가 이미 적어둔 함정이고
            #    내가 그것을 읽고도 처음엔 전국(7.1)을 넣어 실제로 당했다(2026-08-28).
            #    전국으로 두면 미거래 산지 라벨 310개가 겹쳐 글자를 못 읽는다.
            #    ⇒ 미거래 산지를 끄고(우리 7곳만 남긴다) 시야도 좁힌다.
            # closeOriginPanel 로는 안 됐다(실측). 그건 가격탭의 떠 있는 패널을 닫는 함수다.
            # 여기 라벨은 경쟁 산지(보라)이고 enabledOrigins 가 만든다.
            # ⇒ 우리 산지만 남긴다. 태은이 요구가 「어디서 오는지 화살표」라 그게 주인공이다.
            # 런타임에서 레이어를 세어 범인을 찾았다(2026-08-28):
            #   other-origin-labels 307개 = 다른 법인이 쓰는 산지 이름표. 이게 화면을 덮는다.
            #   origin-labels 7 · product-flows 7 = 우리 산지와 화살표. 이건 남긴다.
            # ★ enabledOrigins 를 비우는 방법은 안 먹었다. 그 변수는 이 레이어를 안 만든다.
            #   closeOriginPanel 도 아니었다(그건 가격탭 패널을 닫는 함수다).
            page.wait_for_timeout(700)
            layers = page.evaluate("""() => {
                const keep = deckgl.props.layers.filter(l => l && l.id !== 'other-origin-labels');
                deckgl.setProps({ layers: keep });
                return keep.map(l => l.id + ':' + ((l.props.data||[]).length));
            }""")
            print(f"    라벨 정리 후 레이어: {layers}")
            page.wait_for_timeout(700)
            page.evaluate("""() => { deckgl.setProps({ initialViewState: {
                longitude: 127.6, latitude: 36.5, zoom: 8.6,
                pitch: 18, bearing: 0, transitionDuration: 900 } }); }""")
            info = page.evaluate(f"""() => {{
                const c = summaryData.corporations.find(x => x.corp.includes('대전중앙청과'));
                const p = (c.products||[]).find(p => p.name === '{PRODUCT}');
                const po = (c.product_origins||{{}})['{PRODUCT}'] || [];
                return {{qty: Math.round(p.qty/1000*10)/10, price: p.avg_price_kg, origins: po.length}};
            }}""")
            shot(page, "kbs_06_djc_peach", delay=3)
            print(f"6쪽) 대전중앙청과 + {PRODUCT} {info}")

        # === 8쪽 법인별 가격비교 ===
        page.evaluate("""() => { switchTab('price'); }""")
        page.wait_for_timeout(600)
        ok = page.evaluate(f"""() => {{
            if (typeof selectPriceProduct === 'function') {{ selectPriceProduct('{PRODUCT}'); return 'fn'; }}
            const el = [...document.querySelectorAll('#priceProductList *')]
                .find(e => e.textContent.trim().startsWith('{PRODUCT}'));
            if (el) {{ el.click(); return 'click'; }}
            return null;
        }}""")
        page.wait_for_timeout(1500)
        # 🔴 가격탭은 「복숭아 전체 산지(321개)」 패널을 띄우고 지도를 라벨로 덮는다.
        #    여기서는 closeOriginPanel 이 맞는 함수다(6쪽에서 안 먹은 이유 = 거긴 다른 패널이었다).
        #    그리고 남는 라벨 레이어도 지운다. 이 장의 주인공은 좌측 법인별 가격 목록이다.
        page.evaluate("""() => { if (typeof closeOriginPanel === 'function') closeOriginPanel(); }""")
        page.wait_for_timeout(600)
        left = page.evaluate("""() => {
            const drop = ['other-origin-labels','origin-labels','all-origin-labels'];
            const keep = deckgl.props.layers.filter(l => l && !drop.includes(l.id));
            deckgl.setProps({ layers: keep });
            return keep.map(l => l.id + ':' + ((l.props.data||[]).length));
        }""")
        print(f"    가격탭 라벨 정리 후: {left}")
        page.wait_for_timeout(700)
        rows = page.evaluate("() => document.querySelectorAll('.price-market-row').length")
        if not rows:
            print(f"8쪽) [건너뜀] 가격비교에 {PRODUCT} 행이 없다 (경로={ok})")
        else:
            shot(page, "kbs_08_price_compare", delay=2)
            print(f"8쪽) 법인별 가격비교 {PRODUCT} · {rows}개 법인")

        # === 7쪽 83곳이 같은 날 정산한 것 ===
        page.evaluate("""() => { switchTab('corp'); closeDetail(); }""")
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
        got = page.evaluate("""() => ({
            date: summaryData.date, corps: summaryData.corp_count,
            markets: summaryData.market_count, trades: summaryData.total_trades })""")
        print(f"7쪽 화면 실측: {got}")
        if got["date"] != ALL83_DATE or got["corps"] < 83:
            print("[중단] 의도한 날이 아니거나 83곳이 아니다. 안 찍는다.")
        else:
            shot(page, "kbs_07_all83", delay=3)
            print(f"7쪽) {got['date']} · {got['corps']}곳 · {got['trades']:,}건")

        browser.close()


if __name__ == "__main__":
    main()
