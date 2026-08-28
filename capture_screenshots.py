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

# ★ 2026-08-28 (WHOLESALE-T3) — 천안 공모전 모드 (PIPE #11540 승인)
#   기본은 꺼져 있다. 평소 캡처는 종전 그대로 돌아간다.
#   CHEONAN_MODE=1 로 켜면 셋을 한다.
#     ① 날짜 고정 (CAPTURE_DATE) — 쪽마다 다른 날이면 심사위원이 어느 날 이야기인지 모른다.
#        그리고 제출 시각화 본문이 그 날 화면의 수치를 글로 인용한다.
#     ② 범례 문구를 천안용으로 — 익명 제출물인데 화면이 「우리 산지」라고 한다.
#        심사위원은 「우리」가 누구인지 모른다.
#        ⚠️ KBS 문구(「다른 법인이 받은 산지」)를 복사하지 않는다. 거기는 주인공이 법인이고
#          여기는 시장이다. 주어가 다르다 (PIPE #11540).
#     ③ KAMIS 박스에서 비질량 단위 행만 뺀다 — 박스를 통째로 빼지 않는다.
#        도매 시세와 우리 정산값은 둘 다 도매라 나란히 놓을 수 있다.
#        문제는 단위가 다른 값이 같은 축에 섞인 것이다.
CHEONAN = os.getenv("CHEONAN_MODE") == "1"
CAPTURE_DATE = os.getenv("CAPTURE_DATE", "2026-08-18")
# 천안 캡처가 다루는 품목 (5쪽 가격비교)
CHEONAN_PRODUCT = "복숭아"

LEGEND_FIX = {
    "우리 산지": "천안이 받은 산지",
    "경쟁 산지": "다른 시장이 받은 산지",
}


def nonmass_kamis_rows(date):
    """그 날짜 KAMIS 원자료에서 「질량 단위가 아닌 행」을 뽑는다.

    왜 원자료를 읽나:
      화면 데이터(summaryData.kamis.changes)에는 unit 이 없다.
      preprocess.load_kamis_data 가 avg_price_kg 만 가져오고 unit·unit_size·avg_price 를 버린다.
      ⇒ 화면만 보고는 도매인지 소매인지 가를 수가 없다. 실제로 라벨이 글자 그대로 같다
        (2026-08-18 복숭아 = 「백도 상품」이 도매 5,550 과 소매 18,371 둘 다).

    무엇이 거짓인가 (WI #11552 실측 · IN #11547 확정):
      avg_price_kg 는 질량 단위 행에서만 참이고, unit 이 개·마리·손·포기인 행에서는
      환산이 원리적으로 불가능한데 원값을 그대로 담고 있다.
      실측 = 그 날 238행 중 42행(17.6%)이 비질량이고 그 42행 전부가 그렇다. 예외 0건.
    """
    import json
    f = (Path(__file__).parent.parent / "daily-wholesale-analysis" / "data"
         / f"price_change_{date}.json")
    if not f.exists():
        return None
    data = json.loads(f.read_text(encoding="utf-8"))
    out = []
    for it in data.get("items", []):
        unit = str(it.get("unit", "")).strip()
        if unit in ("kg", "g"):
            continue
        out.append({
            "item": it.get("item_name", ""),
            "variety": it.get("variety_name", ""),
            "grade": it.get("grade_name", ""),
            "price_kg": it.get("avg_price_kg", 0),
            "unit": unit,
            "unit_size": it.get("unit_size", ""),
        })
    return out


def cheonan_fixes(page, nonmass):
    """천안 모드 화면 손질 — 범례 문구 + KAMIS 비질량 행 제거. 게이트 포함."""
    # ① 범례 문구
    legend = page.evaluate("""(fix) => {
        let n = 0;
        const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        const hits = [];
        while (w.nextNode()) {
            for (const k of Object.keys(fix)) {
                if (w.currentNode.nodeValue.includes(k)) { hits.push(w.currentNode); break; }
            }
        }
        for (const t of hits) {
            for (const [k, v] of Object.entries(fix)) {
                if (t.nodeValue.includes(k)) { t.nodeValue = t.nodeValue.split(k).join(v); n++; }
            }
        }
        return n;
    }""", LEGEND_FIX)
    # 게이트 = 옛 문구가 화면에 남아 있으면 안 찍는다
    left = page.evaluate("""(keys) => {
        const t = document.body.innerText;
        return keys.filter(k => t.includes(k));
    }""", list(LEGEND_FIX.keys()))
    if left:
        raise SystemExit(f"★ 멈춤: 옛 범례 문구가 남아 있다 -> {left}. 익명 제출물에 못 쓴다.")

    # ② KAMIS 비질량 행 제거
    killed = 0
    if nonmass:
        targets = [{"label": (r["variety"] + " " + r["grade"]).strip(),
                    "price": r["price_kg"]} for r in nonmass if r["price_kg"]]
        killed = page.evaluate("""(targets) => {
            let n = 0;
            document.querySelectorAll('.kamis-row').forEach(row => {
                const lab = (row.querySelector('.kamis-label') || {}).textContent || '';
                const pri = (row.querySelector('.kamis-price') || {}).textContent || '';
                const num = parseFloat(pri.replace(/[^0-9.]/g, ''));
                for (const t of targets) {
                    if (lab.trim() === t.label && Math.abs(num - t.price) < 0.5) {
                        row.remove(); n++; break;
                    }
                }
            });
            return n;
        }""", targets)
    # 게이트 = 남은 행이 하나도 없으면 빈 박스가 된다. 그것도 안 찍는다.
    state = page.evaluate("""() => {
        const sec = document.querySelector('.kamis-section');
        if (!sec) return {box: false, rows: 0};
        return {box: true, rows: sec.querySelectorAll('.kamis-row').length};
    }""")
    if state["box"] and state["rows"] == 0:
        raise SystemExit("★ 멈춤: KAMIS 박스가 비었다. 다 지웠으면 박스째 빼는 게 낫다.")

    # ③ 헤더를 도매로 못박는다 — 본문도 「도매 시세」라 쓴다. 둘이 같은 말을 해야 한다.
    hdr = page.evaluate("""() => {
        let n = 0;
        document.querySelectorAll('.kamis-header').forEach(el => {
            if (!el.textContent.includes('도매')) {
                el.textContent = el.textContent.replace('전국 시세', '전국 도매 시세'); n++;
            }
        });
        return n;
    }""")
    return {"legend": legend, "kamis_killed": killed,
            "kamis_left": state["rows"], "header": hdr}


_NONMASS = nonmass_kamis_rows(CAPTURE_DATE) if CHEONAN else None


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
    if CHEONAN:
        # 🔴 게이트 = 지도가 한국을 보고 있나.
        #   법인을 고르면 확대되는 것은 정상이라 「확대됐나」로는 못 가른다.
        #   ⇒ 중심이 한반도 범위 밖으로 나갔는지만 본다. 그건 어느 장면에서도 정상이 아니다.
        #   ⚠️ 이 게이트는 정상 화면에서 조용하다(01~09 전부 한국 안이다).
        view = page.evaluate("""() => {
            try {
                const vp = deckgl.viewManager.getViewports()[0];
                if (!vp) return null;
                return {lng: vp.longitude, lat: vp.latitude, zoom: vp.zoom};
            } catch (e) { return null; }
        }""")
        if view is None:
            raise SystemExit(f"★ 멈춤: {name} — 지도 시야를 못 읽었다. "
                             "무엇을 찍는지 모르는 채로 찍지 않는다.")
        if not (124.0 <= view["lng"] <= 132.0 and 33.0 <= view["lat"] <= 39.0):
            raise SystemExit(
                f"★ 멈춤: {name} — 지도가 한국 밖을 보고 있다 "
                f"(경도 {view['lng']:.2f} · 위도 {view['lat']:.2f}).\n"
                "  이대로 찍으면 빈 지도가 나가고, 그것은 파일 크기로만 티가 난다."
            )
        # 매 캡처 직전에 다시 건다. 화면이 다시 그려지면 원복되기 때문이다.
        got = cheonan_fixes(page, _NONMASS)
        bits = [f"범례 {got['legend']}건"]
        if got["kamis_killed"] or got["kamis_left"]:
            bits.append(f"KAMIS 비질량 {got['kamis_killed']}행 제거 "
                        f"· {got['kamis_left']}행 남김")
        if got["header"]:
            bits.append("헤더 도매 명시")
        print("    [천안] " + " · ".join(bits))
    path = OUT_DIR / f"{name}.png"
    page.screenshot(path=str(path))
    print(f"  캡처: {path.name}")
    # ★ 화면이 보여주는 KPI 를 글자 그대로 남긴다 (2026-08-28 WHOLESALE-T3).
    #   왜: 제출 본문이 이 화면의 수치를 글로 인용한다. 그 대조를 캡처 이미지를 눈으로
    #   읽어서 하면 틀린다 — 실제로 오늘 1010.7 을 1818.7 로, 117.0 을 117.8 로 잘못 읽었다.
    #   ⇒ 화면 텍스트를 그대로 찍어 두면 본문과 기계로 맞댈 수 있다.
    try:
        kpi = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('.summary-card').forEach(el => {
                const t = el.innerText.replace(/\\s+/g, ' ').trim();
                if (t) out.push(t);
            });
            const d = document.getElementById('detailPanel');
            if (d && d.classList.contains('open')) {
                const h = (d.querySelector('.detail-title') || {}).textContent || '';
                const nums = [...d.querySelectorAll('.num, .detail-stat .v')]
                    .map(e => e.textContent.trim()).filter(Boolean).slice(0, 4);
                if (nums.length) out.push('상세[' + h.trim() + '] ' + nums.join(' / '));
            }
            return out.slice(0, 8);
        }""")
        if kpi:
            print(f"    [화면값] {' | '.join(kpi)}")
    except Exception as e:
        print(f"    [화면값] 못 읽음: {e}")


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

        if CHEONAN:
            # 날짜를 못박는다. 쪽마다 다른 날이면 어느 날 이야기인지 알 수 없고,
            # 제출 본문이 이 화면의 수치를 글로 인용한다.
            page.evaluate("""(d) => {
                currentDate = d;
                currentPeriod = '1d';
                document.querySelectorAll('.period-btn').forEach(b =>
                    b.classList.toggle('active',
                        b.getAttribute('onclick') === "setPeriod('1d')"));
                return loadForPeriod();
            }""", CAPTURE_DATE)
            page.wait_for_timeout(6000)
            got = page.evaluate("() => ({date: summaryData.date, "
                                "corps: summaryData.corp_count, "
                                "trades: summaryData.total_trades})")
            if got["date"] != CAPTURE_DATE:
                raise SystemExit(
                    f"★ 멈춤: 날짜 고정 실패. 원한 {CAPTURE_DATE} · 실제 {got['date']}\n"
                    "  다른 날 화면을 찍으면 본문 수치와 어긋나고 눈으로만 보인다."
                )
            print(f"[천안] 날짜 고정 {got['date']} · {got['corps']}곳 "
                  f"· {got['trades']:,}건")
            # 🔴 날짜를 옮기면 지도 시야가 틀어진다 (2026-08-28 실측).
            #   1차 재촬영에서 한반도가 화면 왼쪽 끝으로 밀리고 물류 흐름 선이 통째로 사라졌다.
            #   ★ 알아챈 것은 화면이 아니라 파일 크기였다 — 559KB 가 179KB 로 줄었다.
            #     빈 지도는 단색이라 압축이 잘 된다. 크기를 안 봤으면 그대로 냈다.
            #   ⇒ 시야를 전국으로 되돌린다. 그리고 아래 capture() 에 게이트를 건다.
            page.evaluate("""() => { deckgl.setProps({ initialViewState: {
                longitude: 127.9, latitude: 36.4, zoom: 7.1,
                pitch: 18, bearing: 0, transitionDuration: 600 } }); }""")
            page.wait_for_timeout(2500)
            if _NONMASS is None:
                raise SystemExit(
                    f"★ 멈춤: KAMIS 원자료가 없다 "
                    f"(price_change_{CAPTURE_DATE}.json).\n"
                    "  비질량 행을 못 가른다. 그 상태로 찍으면 단위가 섞인 화면이 나간다."
                )
            print(f"[천안] KAMIS 비질량 행 {len(_NONMASS)}개 확인 "
                  f"(이 목록으로 화면에서 지운다)")

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
        # 🔴 앞 장면들이 currentDate 를 과거로 옮겨 놨다(천안 모드는 2026-08-18 로 못박는다).
        #   getMonthKeys 가 그 날짜를 기준으로 월 목록을 만들어서, 그대로 두면 마지막 달이 빠진다.
        #   KBS 판이 실측으로 겪었다 = 2,731일이어야 하는데 2,704일이 찍혔다.
        #   ⚠️ 그런데 그 판의 게이트는 「2,000일 미만이면 중단」이라 2,704 를 통과시킨다.
        #     즉 그 함정은 주석으로만 막혀 있었다. 아래에서 실제로 걸리는 게이트를 건다.
        page.evaluate("""() => {
            const d = new Date();
            d.setDate(d.getDate() - 4);
            currentDate = d.toISOString().slice(0, 10);
        }""")
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
        # 🔴 두 번째 게이트 = 마지막 달이 실렸나.
        #   일수만 보면 안 걸린다. 한 달이 통째로 빠져도 2,704일이라 2,000을 넘는다.
        #   ⇒ 화면 배지의 「끝 날짜」가 지금 보고 있는 날 이후인지 본다.
        #     달이 빠지면 끝 날짜가 그만큼 과거로 밀리므로 이 시험은 그때 반드시 걸린다.
        span = page.evaluate("""() => {
            const m = document.body.innerText.match(
                /(\\d{4}-\\d{2}-\\d{2})\\s*~\\s*(\\d{4}-\\d{2}-\\d{2})/);
            return m ? {start: m[1], end: m[2], cur: currentDate} : null;
        }""")
        if not span:
            raise SystemExit("★ 멈춤: 09_all_period — 화면에서 기간 표시를 못 찾았다. "
                             "게이트가 무엇을 재는지 모르는 채로 찍지 않는다.")
        if span["end"] < span["cur"]:
            raise SystemExit(
                f"★ 멈춤: 09_all_period — 마지막 달이 빠졌다.\n"
                f"  기간 {span['start']} ~ {span['end']} 인데 지금 날짜는 {span['cur']} 다.\n"
                "  앞 장면이 옮겨 놓은 currentDate 를 안 되돌린 것이다. "
                "일수만 보는 게이트로는 안 걸린다."
            )
        print(f"    [게이트] 기간 {span['start']} ~ {span['end']} · {days:,}일")
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
