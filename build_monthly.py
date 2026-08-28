"""월별 요약본 생성 — 8년 8개월 전체를 화면에서 볼 수 있게

왜 월별인가 (2026-08-28 실측):
  원본 2,729일 76GB. 일별 요약본으로 다 만들면 13.6GB 인데
  C드라이브 여유가 43GB 뿐이고 브라우저가 2,729개 fetch 를 못 버틴다.
  월별로 합치면 12MB x 105개월 = 1.26GB. 브라우저 부하도 지금 1년 버튼(116개)과 비슷하다.

방식 (월 단위 파이프라인 — 피크 디스크를 한 달치로 묶는다):
  각 월마다  일별 생성 -> 월별 합산 -> 일별 정리
  ★ 2026-03-30 이후 일별은 절대 안 지운다. 화면이 그것을 읽는다.
  ★ 지우는 것은 이 스크립트가 방금 만든 중간 산출물뿐이고 원본에서 100% 재생성된다
    (실측: 24일치 33초).

사용:
  python build_monthly.py                 # 전체
  python build_monthly.py --from 2018-01 --to 2018-12
  python build_monthly.py --dry-run       # 계획만
"""
import sys
import os
import json
import time
import argparse
import subprocess
import calendar
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).parent
OUT_DIR = HERE / "data"
ARCHIVE_DIR = Path(os.environ.get(
    "AUCTION_ARCHIVE_DIR", str(HERE.parent.parent / "wholesale-data")))
DAILY_DIR = Path(os.environ.get(
    "AUCTION_DATA_DIR", str(HERE.parent / "daily-wholesale-analysis" / "data")))

# 이 날짜 이후 일별 요약본은 화면이 직접 읽는다. 건드리지 않는다.
KEEP_DAILY_FROM = "2026-03-30"


def list_months() -> list[str]:
    """원본이 있는 월 목록 (YYYY-MM)"""
    months = set()
    if ARCHIVE_DIR.exists():
        for d in ARCHIVE_DIR.iterdir():
            if d.is_dir() and len(d.name) == 7 and d.name[4] == "-":
                if any(d.glob("auction_*.json")):
                    months.add(d.name)
    if DAILY_DIR.exists():
        for f in DAILY_DIR.glob("auction_*.json"):
            months.add(f.stem.replace("auction_", "")[:7])
    return sorted(months)


def month_range(ym: str) -> tuple[str, str]:
    y, m = int(ym[:4]), int(ym[5:7])
    last = calendar.monthrange(y, m)[1]
    return f"{ym}-01", f"{ym}-{last:02d}"


def run(args: list[str]) -> tuple[int, str]:
    r = subprocess.run([sys.executable] + args, cwd=str(HERE),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def daily_files_in(ym: str) -> list[Path]:
    return sorted(OUT_DIR.glob(f"summary_{ym}-??.json"))


def build_month(ym: str, dry: bool) -> dict:
    start, end = month_range(ym)
    out = OUT_DIR / f"summary_m_{ym}.json"
    res = {"month": ym, "skipped": False, "made": 0, "cleaned": 0, "size_mb": 0.0}

    if out.exists():
        res["skipped"] = True
        res["size_mb"] = out.stat().st_size / 1e6
        return res
    if dry:
        return res

    before = {p.name for p in daily_files_in(ym)}

    rc, log = run(["preprocess.py", "--batch",
                   "--batch-start", start, "--batch-end", end])
    if rc != 0:
        res["error"] = f"batch rc={rc} :: {log.strip()[-300:]}"
        return res

    rc, log = run(["preprocess.py", "--range", start, end])
    if rc != 0:
        res["error"] = f"range rc={rc} :: {log.strip()[-300:]}"
        return res

    src = OUT_DIR / f"summary_{start}_{end}.json"
    if not src.exists():
        res["error"] = "월별 합산본이 안 생겼다"
        return res
    src.replace(out)
    res["size_mb"] = out.stat().st_size / 1e6

    # 이 실행이 새로 만든 일별만 정리한다. 원래 있던 것과 KEEP 이후는 남긴다.
    for p in daily_files_in(ym):
        date = p.stem.replace("summary_", "")
        if date >= KEEP_DAILY_FROM:
            continue
        if p.name in before:
            continue
        p.unlink()
        res["cleaned"] += 1
    res["made"] = 1
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm")
    ap.add_argument("--to", dest="to")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    months = list_months()
    if a.frm:
        months = [m for m in months if m >= a.frm]
    if a.to:
        months = [m for m in months if m <= a.to]

    print(f"대상 {len(months)}개월  ({months[0]} ~ {months[-1]})" if months else "대상 없음")
    if not months:
        return

    t0 = time.time()
    made = skipped = cleaned = 0
    total_mb = 0.0
    errors = []

    for i, ym in enumerate(months, 1):
        r = build_month(ym, a.dry_run)
        total_mb += r["size_mb"]
        if r.get("error"):
            errors.append((ym, r["error"]))
            print(f"[{i}/{len(months)}] {ym}  X  {r['error'][:120]}", flush=True)
            continue
        if r["skipped"]:
            skipped += 1
            print(f"[{i}/{len(months)}] {ym}  이미 있음 ({r['size_mb']:.1f}MB)", flush=True)
            continue
        made += 1
        cleaned += r["cleaned"]
        el = time.time() - t0
        eta = (len(months) - i) * (el / max(made, 1)) / 60
        print(f"[{i}/{len(months)}] {ym}  생성 {r['size_mb']:.1f}MB  "
              f"일별정리 {r['cleaned']}  경과 {el/60:.1f}분  남은 약 {eta:.0f}분", flush=True)

    print()
    print(f"완료: 생성 {made} · 이미있음 {skipped} · 실패 {len(errors)}")
    print(f"월별 합계 {total_mb/1000:.2f}GB · 정리한 일별 {cleaned}개 · {(time.time()-t0)/60:.1f}분")
    if errors:
        print("실패 목록:")
        for ym, e in errors:
            print(f"  {ym}: {e[:200]}")


if __name__ == "__main__":
    main()
