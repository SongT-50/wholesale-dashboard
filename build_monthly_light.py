"""월별 경량본 — 「전체」 버튼이 브라우저에서 실제로 도는 크기로

왜 필요한가 (2026-08-28 실측, 내 설계 오류의 수정):
  월별본을 만들고 「부하가 1년 버튼과 비슷하다」고 적었다. 틀렸다.
    1년  = 116개 x 5MB  = 580MB
    전체 = 104개 x 13MB = 1.39GB   <- 2.4배
  ★ 파일 개수만 보고 용량을 안 봤다. 개수를 세고 그것을 부하라고 불렀다.
  실제로 브라우저 렌더러가 얼었다(Chrome 최대 226MB 에서 멈춤).

무엇이 무거웠나 (분해 실측, summary_m_2026-07.json 13.9MB):
  corporations 7.55MB (54.5%) · 그중 product_origins 가 법인당 97.6KB 로 압도적
  거기에 json.dump(indent=2) 가 용량을 더 부풀린다.

무엇을 빼나 = 전체 기간에서 안 쓰는 것
  품목별 상세(products) · 산지별(origins, product_origins) · 가격맵(price_map)
  ⇒ 8년치 품목 상세를 브라우저에서 볼 이유가 없다. 그건 1일~1년 구간에서 본다.
남기는 것 = 법인 총량과 좌표 · 시장 · 물류 흐름 · 기간과 합계
  ⇒ 지도와 법인 순위와 총계는 그대로 나온다.

실측 = 13.85MB -> 0.09MB (0.7%) · 104개월 합계 약 9.4MB

★ 원본 월별본(1.39GB)은 안 지운다. 월 단위 상세 분석에 쓸 수 있고 재생성에 10분이 든다.

사용: python build_monthly_light.py
"""
import sys
import json
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DATA = Path(__file__).parent / "data"

# 화면이 이 키들을 참조한다. 빈 값으로라도 있어야 안 깨진다.
CORP_KEYS = ("corp", "market", "market_code", "lat", "lng",
             "trades", "total_qty", "total_amount")
TOP_KEYS = ("date", "date_start", "date_end", "days_count",
            "total_trades", "total_amount", "total_qty",
            "corp_count", "market_count")
FLOW_CAP = 300          # 지도가 상위 55개만 그린다. 여유를 둬도 300이면 넉넉하다.


def lighten(src: Path) -> dict:
    d = json.loads(src.read_text(encoding="utf-8"))
    out = {k: d[k] for k in TOP_KEYS if k in d}
    out["corporations"] = [
        {**{k: c[k] for k in CORP_KEYS if k in c},
         # 구조 유지 — 화면이 .products.find(...) 같은 접근을 한다
         "products": [], "origins": [], "product_origins": {}}
        for c in d.get("corporations", [])
    ]
    out["markets"] = d.get("markets", [])
    out["flows"] = d.get("flows", [])[:FLOW_CAP]
    out["price_map"] = {}
    return out


def main():
    srcs = sorted(DATA.glob("summary_m_????-??.json"))
    if not srcs:
        print("월별본이 없다. build_monthly.py 를 먼저 돌려라.")
        return
    t0 = time.time()
    tot_src = tot_out = 0
    for i, src in enumerate(srcs, 1):
        ym = src.stem.replace("summary_m_", "")
        dst = DATA / f"summary_ml_{ym}.json"
        light = lighten(src)
        # separators 로 공백을 없앤다. indent 는 쓰지 않는다.
        dst.write_text(json.dumps(light, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")
        tot_src += src.stat().st_size
        tot_out += dst.stat().st_size
        if i % 20 == 0 or i == len(srcs):
            print(f"  [{i}/{len(srcs)}] {ym}  누적 {tot_out/1e6:.1f}MB", flush=True)

    print()
    print(f"완료 {len(srcs)}개 · {time.time()-t0:.1f}초")
    print(f"원본 합계 {tot_src/1e9:.2f}GB  ->  경량 합계 {tot_out/1e6:.1f}MB "
          f"({tot_out/tot_src*100:.1f}%)")


if __name__ == "__main__":
    main()
