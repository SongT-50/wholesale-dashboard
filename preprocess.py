"""경매 원본 데이터 → 대시보드용 요약 JSON 생성
법인 기준 집계 (38개 법인 × 품목별 거래량/가격/산지)

사용: python preprocess.py --date 2026-03-09
"""
import sys
import json
import argparse
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# 데이터 경로
DATA_DIR = Path(__file__).parent.parent / "daily-wholesale-analysis" / "data"
ARCHIVE_DIR = Path(__file__).parent.parent.parent / "wholesale-data"
CORP_FILE = Path(__file__).parent / "corporations.json"
REGION_FILE = Path(__file__).parent / "region_coords.json"
OUT_DIR = Path(__file__).parent / "data"


def load_auction(date: str) -> dict | None:
    f = DATA_DIR / f"auction_{date}.json"
    if f.exists():
        with open(f, "r", encoding="utf-8") as fp:
            return json.load(fp)
    month = date[:7]
    f = ARCHIVE_DIR / month / f"auction_{date}.json"
    if f.exists():
        with open(f, "r", encoding="utf-8") as fp:
            return json.load(fp)
    return None


def load_corps() -> list[dict]:
    with open(CORP_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_region_coords() -> dict:
    with open(REGION_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_origin_coords(origin: str, region_coords: dict) -> tuple[float, float]:
    """산지 텍스트 → (lat, lng) 매칭. 못 찾으면 (0, 0)"""
    if not origin or origin == "-":
        return (0, 0)

    # 정확히 일치
    if origin in region_coords:
        c = region_coords[origin]
        return (c["lat"], c["lng"])

    # 공백 분리: "경상남도 진주시" → "진주시" 매칭
    parts = origin.split()
    if len(parts) >= 2:
        # 시/군/구 우선
        for part in reversed(parts):
            if part in region_coords:
                c = region_coords[part]
                return (c["lat"], c["lng"])

    # 단일 단어로 시도 (약칭 등)
    for part in parts:
        if part in region_coords:
            c = region_coords[part]
            return (c["lat"], c["lng"])

    return (0, 0)


def preprocess(date: str):
    data = load_auction(date)
    if not data:
        print(f"{date} 데이터 없음")
        return

    corps_master = load_corps()
    region_coords = load_region_coords()

    corp_coords = {}
    for c in corps_master:
        corp_coords[c["corp"]] = {
            "market": c["market"],
            "market_code": c["market_code"],
            "lat": c["lat"],
            "lng": c["lng"],
        }

    # 법인별 집계
    corp_stats = defaultdict(lambda: {
        "trades": 0,
        "total_qty": 0,
        "total_amount": 0,
        "products": defaultdict(lambda: {"trades": 0, "qty": 0, "amount": 0, "prices": []}),
        "origins": defaultdict(lambda: {"trades": 0, "qty": 0, "amount": 0}),
        "product_origins": defaultdict(lambda: defaultdict(lambda: {"trades": 0, "qty": 0, "amount": 0})),
    })

    # 시장별 집계
    market_stats = defaultdict(lambda: {"trades": 0, "total_qty": 0, "total_amount": 0, "corp_count": 0})

    # price_map: 품목 → 시장 → prices[]
    price_map_raw = defaultdict(lambda: defaultdict(list))

    total_trades = 0
    total_amount = 0
    total_qty = 0

    for m in data["markets"].values():
        for item in m["items"]:
            corp = item.get("corp_name", "")
            if not corp:
                continue

            product = item.get("product", "")
            origin = item.get("origin", "") or "-"
            price = item.get("price", 0)
            unit_wt = item.get("unit_weight", 0)
            qty = item.get("quantity", 0)
            if not isinstance(qty, (int, float)):
                qty = 0
            amount = price * qty
            kg = unit_wt * qty  # 정산 API: unit_weight=총물량(kg), quantity=1
            per_kg = amount / kg if kg > 0 else 0

            s = corp_stats[corp]
            s["trades"] += 1
            s["total_qty"] += kg
            s["total_amount"] += amount

            p = s["products"][product]
            p["trades"] += 1
            p["qty"] += kg
            p["amount"] += amount
            if 0 < per_kg <= 100_000:
                p["prices"].append(per_kg)

            o = s["origins"][origin]
            o["trades"] += 1
            o["qty"] += kg
            o["amount"] += amount

            # 품목별 산지 매핑
            if origin != "-" and product:
                po = s["product_origins"][product][origin]
                po["trades"] += 1
                po["qty"] += kg
                po["amount"] += amount

            # 시장별 집계
            info = corp_coords.get(corp, {})
            market_name = info.get("market", "")
            if market_name:
                ms = market_stats[market_name]
                ms["trades"] += 1
                ms["total_qty"] += kg
                ms["total_amount"] += amount

            # price_map
            if market_name and product and 0 < per_kg <= 100_000:
                price_map_raw[product][market_name].append(per_kg)

            total_trades += 1
            total_amount += amount
            total_qty += kg

    # 시장별 법인 수 집계
    market_corps = defaultdict(set)
    for corp_name, info in corp_coords.items():
        if corp_name in corp_stats:
            market_corps[info["market"]].add(corp_name)
    for market_name, corps_set in market_corps.items():
        market_stats[market_name]["corp_count"] = len(corps_set)

    # 요약 JSON 생성
    corps_summary = []
    for corp, s in sorted(corp_stats.items(), key=lambda x: -x[1]["trades"]):
        info = corp_coords.get(corp, {})

        # 전체 품목 (거래건수순)
        all_products = sorted(s["products"].items(), key=lambda x: -x[1]["trades"])
        products = []
        for pname, ps in all_products:
            avg_price = sum(ps["prices"]) / len(ps["prices"]) if ps["prices"] else 0
            products.append({
                "name": pname,
                "trades": ps["trades"],
                "qty": ps["qty"],
                "amount": ps["amount"],
                "avg_price_kg": round(avg_price),
            })

        # 전체 산지 (거래건수순)
        all_origins = sorted(s["origins"].items(), key=lambda x: -x[1]["trades"])
        origins = []
        for oname, os_ in all_origins:
            origins.append({
                "name": oname,
                "trades": os_["trades"],
                "qty": os_["qty"],
                "amount": os_["amount"],
            })

        # 품목별 산지 (GPS 포함, 상위 20개 산지만)
        prod_origins = {}
        for pname, origins_map in s["product_origins"].items():
            sorted_origins = sorted(origins_map.items(), key=lambda x: -x[1]["trades"])[:20]
            po_list = []
            for oname, os2 in sorted_origins:
                olat, olng = resolve_origin_coords(oname, region_coords)
                is_foreign = olat != 0 and (olat < 33 or olng < 124 or olng > 132)
                po_list.append({
                    "name": oname,
                    "trades": os2["trades"],
                    "qty": os2["qty"],
                    "lat": olat,
                    "lng": olng,
                    "foreign": is_foreign,
                })
            prod_origins[pname] = po_list

        corps_summary.append({
            "corp": corp,
            "market": info.get("market", ""),
            "market_code": info.get("market_code", ""),
            "lat": info.get("lat", 0),
            "lng": info.get("lng", 0),
            "trades": s["trades"],
            "total_qty": s["total_qty"],
            "total_amount": s["total_amount"],
            "products": products,
            "origins": origins,
            "product_origins": prod_origins,
        })

    # 시장 집계 리스트
    markets_summary = []
    for market_name, ms in sorted(market_stats.items(), key=lambda x: -x[1]["trades"]):
        markets_summary.append({
            "market": market_name,
            "trades": ms["trades"],
            "total_qty": ms["total_qty"],
            "total_amount": ms["total_amount"],
            "corp_count": ms["corp_count"],
        })

    # 산지 → 시장 흐름 (상위 200개 + GPS 좌표)
    flows = defaultdict(lambda: {"trades": 0, "qty": 0, "amount": 0})
    for m in data["markets"].values():
        for item in m["items"]:
            origin = item.get("origin", "") or "-"
            corp = item.get("corp_name", "")
            if not corp or origin == "-":
                continue
            key = (origin, corp)
            qty = item.get("quantity", 0)
            if not isinstance(qty, (int, float)):
                qty = 0
            unit_wt = item.get("unit_weight", 0)
            kg = unit_wt * qty
            flows[key]["trades"] += 1
            flows[key]["qty"] += kg
            flows[key]["amount"] += item.get("price", 0) * qty

    top_flows = sorted(flows.items(), key=lambda x: -x[1]["trades"])[:200]
    flows_list = []
    origin_matched = 0
    for (origin, corp), fs in top_flows:
        info = corp_coords.get(corp, {})
        olat, olng = resolve_origin_coords(origin, region_coords)
        if olat != 0:
            origin_matched += 1
        is_foreign = olat != 0 and (olat < 33 or olng < 124 or olng > 132)
        flows_list.append({
            "origin": origin,
            "origin_lat": olat,
            "origin_lng": olng,
            "dest_corp": corp,
            "dest_market": info.get("market", ""),
            "dest_lat": info.get("lat", 0),
            "dest_lng": info.get("lng", 0),
            "trades": fs["trades"],
            "qty": fs["qty"],
            "amount": fs["amount"],
            "foreign": is_foreign,
        })

    # price_map: 상위 30개 품목 × 시장별 평균가
    price_map = {}
    top_products_by_trades = sorted(price_map_raw.keys(),
                                     key=lambda p: sum(len(v) for v in price_map_raw[p].values()),
                                     reverse=True)[:30]
    for product in top_products_by_trades:
        market_prices = {}
        for market_name, prices in price_map_raw[product].items():
            market_prices[market_name] = round(sum(prices) / len(prices))
        price_map[product] = market_prices

    result = {
        "date": date,
        "total_trades": total_trades,
        "total_amount": total_amount,
        "total_qty": total_qty,
        "corp_count": len(corps_summary),
        "market_count": len(markets_summary),
        "corporations": corps_summary,
        "markets": markets_summary,
        "flows": flows_list,
        "price_map": price_map,
    }

    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"summary_{date}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    size_kb = out.stat().st_size / 1024
    print(f"요약 생성: {out} ({size_kb:.0f}KB)")
    print(f"  법인: {len(corps_summary)}개, 거래: {total_trades:,}건, 금액: {total_amount:,.0f}원")
    print(f"  시장: {len(markets_summary)}개")
    print(f"  물류흐름: {len(flows_list)}개 (산지GPS매칭: {origin_matched}/{len(flows_list)})")
    print(f"  가격맵: {len(price_map)}개 품목")


def merge_summaries(start: str, end: str):
    """기존 하루치 summary JSON들을 합산해서 기간 요약 생성"""
    from datetime import datetime, timedelta

    OUT_DIR.mkdir(exist_ok=True)
    d = datetime.strptime(start, "%Y-%m-%d")
    end_d = datetime.strptime(end, "%Y-%m-%d")

    # 하루치 summary들 수집
    daily_files = []
    while d <= end_d:
        ds = d.strftime("%Y-%m-%d")
        f = OUT_DIR / f"summary_{ds}.json"
        if f.exists():
            daily_files.append(f)
        d += timedelta(days=1)

    if not daily_files:
        print(f"기간 {start}~{end}: 요약 파일 없음")
        return

    print(f"머지 대상: {len(daily_files)}개 파일")

    # 법인별 합산
    corp_agg = {}      # corp -> merged data
    market_agg = {}    # market -> merged data
    flow_agg = {}      # (origin, dest_corp) -> merged data
    price_agg = {}     # product -> market -> prices[]
    total_trades = 0
    total_amount = 0
    total_qty = 0
    dates_loaded = []

    for f in daily_files:
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        dates_loaded.append(data["date"])
        total_trades += data["total_trades"]
        total_amount += data["total_amount"]
        total_qty += data.get("total_qty", 0)

        # 법인 합산
        for c in data["corporations"]:
            key = c["corp"]
            if key not in corp_agg:
                corp_agg[key] = {
                    "corp": c["corp"], "market": c["market"],
                    "market_code": c.get("market_code", ""),
                    "lat": c["lat"], "lng": c["lng"],
                    "trades": 0, "total_qty": 0, "total_amount": 0,
                    "products": {}, "origins": {}, "product_origins": {},
                }
            ca = corp_agg[key]
            ca["trades"] += c["trades"]
            ca["total_qty"] += c["total_qty"]
            ca["total_amount"] += c["total_amount"]

            # 품목 합산
            for p in c.get("products", []):
                if p["name"] not in ca["products"]:
                    ca["products"][p["name"]] = {"name": p["name"], "trades": 0, "qty": 0, "amount": 0, "prices": []}
                cp = ca["products"][p["name"]]
                cp["trades"] += p["trades"]
                cp["qty"] += p["qty"]
                cp["amount"] += p["amount"]
                if p.get("avg_price_kg", 0) > 0:
                    cp["prices"].append(p["avg_price_kg"])

            # 산지 합산
            for o in c.get("origins", []):
                if o["name"] not in ca["origins"]:
                    ca["origins"][o["name"]] = {"name": o["name"], "trades": 0, "qty": 0, "amount": 0}
                co = ca["origins"][o["name"]]
                co["trades"] += o["trades"]
                co["qty"] += o["qty"]
                co["amount"] += o["amount"]

            # 품목별 산지 합산
            for pname, po_list in c.get("product_origins", {}).items():
                if pname not in ca["product_origins"]:
                    ca["product_origins"][pname] = {}
                for o in po_list:
                    if o["name"] not in ca["product_origins"][pname]:
                        ca["product_origins"][pname][o["name"]] = {
                            "name": o["name"], "trades": 0, "qty": 0,
                            "lat": o["lat"], "lng": o["lng"], "foreign": o.get("foreign", False),
                        }
                    po = ca["product_origins"][pname][o["name"]]
                    po["trades"] += o["trades"]
                    po["qty"] += o["qty"]

        # 시장 합산
        for m in data.get("markets", []):
            key = m["market"]
            if key not in market_agg:
                market_agg[key] = {"market": key, "trades": 0, "total_qty": 0, "total_amount": 0, "corp_count": m.get("corp_count", 0)}
            market_agg[key]["trades"] += m["trades"]
            market_agg[key]["total_qty"] += m["total_qty"]
            market_agg[key]["total_amount"] += m["total_amount"]

        # 흐름 합산
        for fl in data.get("flows", []):
            key = (fl["origin"], fl["dest_corp"])
            if key not in flow_agg:
                flow_agg[key] = dict(fl)
                flow_agg[key]["trades"] = 0
                flow_agg[key]["qty"] = 0
                flow_agg[key]["amount"] = 0
            flow_agg[key]["trades"] += fl["trades"]
            flow_agg[key]["qty"] += fl["qty"]
            flow_agg[key]["amount"] += fl.get("amount", 0)

        # 가격맵 합산
        for product, markets in data.get("price_map", {}).items():
            if product not in price_agg:
                price_agg[product] = {}
            for market, price in markets.items():
                if market not in price_agg[product]:
                    price_agg[product][market] = []
                price_agg[product][market].append(price)

    # 최종 형태로 변환
    corps_summary = []
    for ca in sorted(corp_agg.values(), key=lambda x: -x["trades"]):
        products = sorted(ca["products"].values(), key=lambda x: -x["trades"])
        for p in products:
            p["avg_price_kg"] = round(sum(p["prices"]) / len(p["prices"])) if p["prices"] else 0
            del p["prices"]

        origins = sorted(ca["origins"].values(), key=lambda x: -x["trades"])

        prod_origins = {}
        for pname, po_map in ca["product_origins"].items():
            po_list = sorted(po_map.values(), key=lambda x: -x["trades"])[:20]
            prod_origins[pname] = po_list

        corps_summary.append({
            "corp": ca["corp"], "market": ca["market"], "market_code": ca["market_code"],
            "lat": ca["lat"], "lng": ca["lng"],
            "trades": ca["trades"], "total_qty": ca["total_qty"], "total_amount": ca["total_amount"],
            "products": products, "origins": origins, "product_origins": prod_origins,
        })

    markets_summary = sorted(market_agg.values(), key=lambda x: -x["trades"])

    top_flows = sorted(flow_agg.values(), key=lambda x: -x["trades"])[:300]

    price_map = {}
    for product in sorted(price_agg.keys(), key=lambda p: sum(len(v) for v in price_agg[p].values()), reverse=True)[:30]:
        market_prices = {}
        for market, prices in price_agg[product].items():
            market_prices[market] = round(sum(prices) / len(prices))
        price_map[product] = market_prices

    result = {
        "date": f"{start} ~ {end}",
        "date_start": start,
        "date_end": end,
        "days_count": len(dates_loaded),
        "total_trades": total_trades,
        "total_amount": total_amount,
        "total_qty": total_qty,
        "corp_count": len(corps_summary),
        "market_count": len(markets_summary),
        "corporations": corps_summary,
        "markets": markets_summary,
        "flows": top_flows,
        "price_map": price_map,
    }

    out = OUT_DIR / f"summary_{start}_{end}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    size_kb = out.stat().st_size / 1024
    print(f"기간 요약 생성: {out} ({size_kb:.0f}KB)")
    print(f"  기간: {start} ~ {end} ({len(dates_loaded)}일)")
    print(f"  법인: {len(corps_summary)}개, 거래: {total_trades:,}건, 금액: {total_amount:,.0f}원")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    parser.add_argument("--range", nargs=2, metavar=("START", "END"),
                        help="기간 합산: --range 2026-02-09 2026-03-09")
    args = parser.parse_args()

    if args.range:
        merge_summaries(args.range[0], args.range[1])
    elif args.date:
        preprocess(args.date)
    else:
        parser.error("--date 또는 --range 필수")


if __name__ == "__main__":
    main()
