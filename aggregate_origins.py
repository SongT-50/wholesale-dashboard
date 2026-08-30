# -*- coding: utf-8 -*-
"""경매 원본 -> 산지 분석 탭 데이터 (origins.json / origins_v2.json / sigungu_coords.json)

### 왜 이 파일이 2026-08-30 에 «새로» 생겼나
index.html 이 이 셋을 읽는데 **셋 다 저장소에 없었다.** 그래서 산지 분석 탭이
`데이터 없음 (origins.json HTTP 404)` 를 띄우고, 지역을 누르면
`v2 데이터 필요 (재집계 진행 중)` 이 나온다. ### 그 «진행 중» 은 2026-04-17 것이고 죽었다.
에러 문구는 `python wholesale-dashboard/aggregate_origins.py` 를 안내하는데
### 그 스크립트 자체가 없었다. 이 파일이 그것이다.

무엇을 읽나
  daily-wholesale-analysis/data/auction_YYYY-MM-DD.json (하루 약 27MB)
  레코드에 origin("강원특별자치도 평창군") · product · corp_name · total_qty 가 다 있다.

왜 조각내나
  라이브가 쓰는 구간이 150일 = 3.8GB. 한 번에 읽으면 앞단 제한에 걸린다.
  ⇒ --from/--to 로 조각내어 «상태 파일» 에 누적하고, 마지막에 --finalize.

사용
  python aggregate_origins.py --from 2026-03-30 --to 2026-05-10
  python aggregate_origins.py --from 2026-05-11 --to 2026-06-20
  ...
  python aggregate_origins.py --finalize

네트워크 0 · 과금 0.
"""
import argparse
import io
import json
import os
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "daily-wholesale-analysis", "data")
OUT = os.path.join(HERE, "data")
STATE = os.path.join(HERE, "_agg_origins_state.json")

# ### 자르는 곳을 여기 모아둔다 — 조용히 자르지 않는다(산출물 meta 에 그대로 실린다).
CAP_RAW_ORIGINS = 200      # 시도·연도당 원본 산지 문자열
CAP_PRODUCT_L2CORP = 300   # 품목당 (시군구 x 법인) 조합
CAP_PRODUCTS = 400         # v2 에 담을 품목 수 (물량 상위)


def _dd():
    return defaultdict(float)


def new_state():
    return {
        "days": [],
        # regions[l1][year] = {kg, count, corps{}, products{}, raw_origins{}, l2{}}
        "regions": defaultdict(lambda: defaultdict(
            lambda: {"kg": 0.0, "count": 0,
                     "corps": _dd(), "products": _dd(),
                     "raw_origins": _dd(), "l2": _dd()})),
        # prod[product] = {total, years{}, by_l1{}, by_corp{}, by_l2{}, by_l2_corp{}}
        "prod": defaultdict(lambda: {"total": 0.0, "years": _dd(), "by_l1": _dd(),
                                     "by_corp": _dd(), "by_l2": _dd(),
                                     "by_l2_corp": _dd()}),
    }


def split_origin(s):
    """'강원특별자치도 평창군' -> ('강원특별자치도', '평창군').

    ### 시군구가 없는 산지(수입·미상)도 있다. 그때 L2 는 None 이고 그렇게 센다.
    """
    if not s:
        return None, None
    parts = str(s).split()
    if not parts:
        return None, None
    l1 = parts[0]
    l2 = parts[1] if len(parts) > 1 else None
    return l1, l2


def ingest(state, date):
    f = os.path.join(SRC, "auction_%s.json" % date)
    if not os.path.exists(f):
        return 0, 0
    with io.open(f, encoding="utf-8") as fh:
        d = json.load(fh)
    year = date[:4]
    n = kept = 0
    for mk in (d.get("markets") or {}).values():
        for r in (mk.get("items") or []):
            n += 1
            qty = r.get("total_qty")
            if not qty:
                continue
            try:
                qty = float(qty)
            except (TypeError, ValueError):
                continue
            if qty <= 0:
                continue
            raw = r.get("origin") or ""
            l1, l2 = split_origin(raw)
            if not l1:
                continue
            corp = r.get("corp_name") or "미상"
            prod = r.get("product") or "미상"
            kept += 1

            b = state["regions"][l1][year]
            b["kg"] += qty
            b["count"] += 1
            b["corps"][corp] += qty
            b["products"][prod] += qty
            b["raw_origins"][raw] += qty
            if l2:
                b["l2"][l2] += qty

            p = state["prod"][prod]
            p["total"] += qty
            p["years"][year] += qty
            p["by_l1"][l1] += qty
            p["by_corp"][corp] += qty
            if l2:
                p["by_l2"]["%s\t%s" % (l1, l2)] += qty
                p["by_l2_corp"]["%s\t%s\t%s" % (l1, l2, corp)] += qty
    return n, kept


def to_plain(state):
    return {
        "days": state["days"],
        "regions": {l1: {y: {"kg": b["kg"], "count": b["count"],
                             "corps": dict(b["corps"]), "products": dict(b["products"]),
                             "raw_origins": dict(b["raw_origins"]), "l2": dict(b["l2"])}
                         for y, b in ys.items()}
                    for l1, ys in state["regions"].items()},
        "prod": {k: {"total": v["total"], "years": dict(v["years"]),
                     "by_l1": dict(v["by_l1"]), "by_corp": dict(v["by_corp"]),
                     "by_l2": dict(v["by_l2"]), "by_l2_corp": dict(v["by_l2_corp"])}
                 for k, v in state["prod"].items()},
    }


def from_plain(p):
    s = new_state()
    s["days"] = p.get("days", [])
    for l1, ys in (p.get("regions") or {}).items():
        for y, b in ys.items():
            t = s["regions"][l1][y]
            t["kg"] = b["kg"]
            t["count"] = b["count"]
            for k in ("corps", "products", "raw_origins", "l2"):
                for name, v in (b.get(k) or {}).items():
                    t[k][name] += v
    for name, v in (p.get("prod") or {}).items():
        t = s["prod"][name]
        t["total"] = v["total"]
        for k in ("years", "by_l1", "by_corp", "by_l2", "by_l2_corp"):
            for kk, vv in (v.get(k) or {}).items():
                t[k][kk] += vv
    return s


def load_state():
    if os.path.exists(STATE):
        with io.open(STATE, encoding="utf-8") as fh:
            return from_plain(json.load(fh))
    return new_state()


def save_state(state):
    with io.open(STATE, "w", encoding="utf-8") as fh:
        json.dump(to_plain(state), fh, ensure_ascii=False)


def top(dic, cap=None):
    items = sorted(dic.items(), key=lambda x: -x[1])
    return items if cap is None else items[:cap]


def finalize(state):
    days = sorted(set(state["days"]))
    years = sorted({d[:4] for d in days})
    if not days:
        print("### 상태가 비었다. 먼저 --from/--to 로 조각을 돌려라.")
        return

    regions = {}
    for l1, ys in state["regions"].items():
        regions[l1] = {}
        for y, b in ys.items():
            regions[l1][y] = {
                "kg": round(b["kg"], 1),
                "count": b["count"],
                "corps": [{"name": n, "kg": round(v, 1)} for n, v in top(b["corps"])],
                "products": [{"name": n, "kg": round(v, 1)} for n, v in top(b["products"])],
                "raw_origins": [{"name": n, "kg": round(v, 1)}
                                for n, v in top(b["raw_origins"], CAP_RAW_ORIGINS)],
                "l2": [{"name": n, "kg": round(v, 1)} for n, v in top(b["l2"])],
            }
    o1 = {
        "years": years,
        "regions": regions,
        "meta": {"days": len(days), "from": days[0], "to": days[-1],
                 "generated_by": "aggregate_origins.py",
                 "caps": {"raw_origins_per_region_year": CAP_RAW_ORIGINS}},
    }
    with io.open(os.path.join(OUT, "origins.json"), "w", encoding="utf-8") as fh:
        json.dump(o1, fh, ensure_ascii=False)

    prods = sorted(state["prod"].items(), key=lambda x: -x[1]["total"])[:CAP_PRODUCTS]
    products = {}
    for name, v in prods:
        by_l2 = [{"l1": k.split("\t")[0], "l2": k.split("\t")[1], "kg": round(kg, 1)}
                 for k, kg in top(v["by_l2"])]
        by_l2_corp = [{"l1": k.split("\t")[0], "l2": k.split("\t")[1],
                       "corp": k.split("\t")[2], "kg": round(kg, 1)}
                      for k, kg in top(v["by_l2_corp"], CAP_PRODUCT_L2CORP)]
        products[name] = {
            "total_kg": round(v["total"], 1),
            "years": {y: round(kg, 1) for y, kg in sorted(v["years"].items())},
            "by_l1": [{"l1": n, "kg": round(kg, 1)} for n, kg in top(v["by_l1"])],
            "by_corp": [{"corp": n, "kg": round(kg, 1)} for n, kg in top(v["by_corp"])],
            "by_l2": by_l2,
            "by_l2_corp": by_l2_corp,
        }
    v2regions = {l1: {y: {"l2": regions[l1][y]["l2"]} for y in regions[l1]}
                 for l1 in regions}
    o2 = {
        "products": products,
        "regions": v2regions,
        "meta": {"days": len(days), "from": days[0], "to": days[-1],
                 "generated_by": "aggregate_origins.py",
                 "caps": {"products": CAP_PRODUCTS,
                          "by_l2_corp_per_product": CAP_PRODUCT_L2CORP},
                 "note": "### 자른 곳은 caps 그대로다. 조용히 자르지 않는다."},
    }
    with io.open(os.path.join(OUT, "origins_v2.json"), "w", encoding="utf-8") as fh:
        json.dump(o2, fh, ensure_ascii=False)

    l2keys = set()
    for l1, ys in regions.items():
        for y, b in ys.items():
            for x in b["l2"]:
                l2keys.add("%s %s" % (l1, x["name"]))
    print("origins.json      시도 %d · 연도 %s · 일수 %d (%s ~ %s)"
          % (len(regions), ",".join(years), len(days), days[0], days[-1]))
    print("origins_v2.json   품목 %d (전체 %d 중 상위) · 시군구키 %d"
          % (len(products), len(state["prod"]), len(l2keys)))
    print("### 시군구 좌표(sigungu_coords.json)는 이 스크립트가 «안» 만든다 — 좌표 소스가 따로 필요하다.")
    print("    없으면 L2 «목록» 은 뜨고 지도 «점·Arc» 만 안 뜬다.")


def build_sigungu_coords():
    """### 시군구 좌표는 «외부 소스가 필요하다» 고 생각했는데 우리 안에 있었다.

    summary_*.json 의 flows 가 origin 문자열과 함께 origin_lat/lng 를 담는다.
    그리고 그 좌표는 **시도 대표값이 아니라 시군구별로 다르다**(경북 11종·강원 8종 실측).
    ⇒ 추가 데이터 소스 없이 만든다.

    ⚠️ 못 하는 말 = flows 는 **하루 상위 200개** 다. 물량이 적은 시군구는 안 잡힌다.
       그래서 산출물에 covered/total 을 함께 적는다. 조용히 빠뜨리지 않는다.
    """
    acc = {}
    files = sorted(f for f in os.listdir(OUT)
                   if f.startswith("summary_") and f.endswith(".json"))
    for fn in files:
        try:
            with io.open(os.path.join(OUT, fn), encoding="utf-8") as fh:
                d = json.load(fh)
        except (ValueError, OSError):
            continue
        for fl in (d.get("flows") or []):
            o = fl.get("origin") or ""
            l1, l2 = split_origin(o)
            if not (l1 and l2):
                continue
            lat, lng = fl.get("origin_lat"), fl.get("origin_lng")
            if lat is None or lng is None:
                continue
            key = "%s %s" % (l1, l2)
            acc.setdefault(key, {"lat": round(float(lat), 6),
                                 "lng": round(float(lng), 6)})
    return acc, len(files)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d_from")
    ap.add_argument("--to", dest="d_to")
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--coords", action="store_true")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()

    if a.reset and os.path.exists(STATE):
        os.remove(STATE)
        print("상태 초기화")

    state = load_state()

    if a.d_from and a.d_to:
        dates = sorted(f[8:18] for f in os.listdir(SRC)
                       if f.startswith("auction_") and f.endswith(".json"))
        win = [d for d in dates if a.d_from <= d <= a.d_to]
        done = set(state["days"])
        todo = [d for d in win if d not in done]
        print("조각 %s ~ %s = %d일 (이미 %d일 · 이번 %d일)"
              % (a.d_from, a.d_to, len(win), len(win) - len(todo), len(todo)), flush=True)
        tot = kept = 0
        for d in todo:
            n, k = ingest(state, d)
            if n:
                state["days"].append(d)
                tot += n
                kept += k
        save_state(state)
        print("  레코드 %d · 집계 %d · 누적일수 %d" % (tot, kept, len(set(state["days"]))))

    if a.coords:
        coords, nfiles = build_sigungu_coords()
        with io.open(os.path.join(OUT, "sigungu_coords.json"), "w", encoding="utf-8") as fh:
            json.dump(coords, fh, ensure_ascii=False)
        need = set()
        for l1, ys in state["regions"].items():
            for y, b in ys.items():
                for n in b["l2"]:
                    need.add("%s %s" % (l1, n))
        hit = len(need & set(coords))
        print("sigungu_coords.json  좌표 %d개 (요약본 %d개에서)" % (len(coords), nfiles))
        print("  집계에 나온 시군구 %d개 중 좌표 있음 %d (%.1f%%) · ### 없음 %d"
              % (len(need), hit, 100.0 * hit / max(len(need), 1), len(need) - hit))
        print("  ### 없는 것은 지도 «점·Arc» 에만 안 뜬다. 목록에는 뜬다.")

    if a.finalize:
        finalize(state)


if __name__ == "__main__":
    main()
