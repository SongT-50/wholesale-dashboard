"""GitHub Pages push 전 준비 스크립트
data/ 내 summary 파일을 최근 7일치만 git에 포함시키고 나머지는 untrack.
로컬 파일은 삭제하지 않음 (git rm --cached).

사용:
  python prepare_push.py              # 최근 7일 summary만 staging
  python prepare_push.py --days 14    # 최근 14일
  python prepare_push.py --dry-run    # 변경 없이 확인만
"""
import sys
import subprocess
import re
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DATA_DIR = Path(__file__).parent / "data"
SUMMARY_RE = re.compile(r"^summary_(\d{4}-\d{2}-\d{2})\.json$")


def get_summary_files():
    """data/ 내 일별 summary 파일 목록 반환 (날짜, 경로)"""
    results = []
    for f in DATA_DIR.glob("summary_*.json"):
        m = SUMMARY_RE.match(f.name)
        if m:
            results.append((m.group(1), f))
    results.sort(key=lambda x: x[0], reverse=True)
    return results


def get_tracked_summaries():
    """git이 추적 중인 data/summary_*.json 목록"""
    result = subprocess.run(
        ["git", "ls-files", "data/summary_*.json"],
        capture_output=True, text=True, encoding="utf-8"
    )
    return set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="GitHub Pages push 준비")
    parser.add_argument("--days", type=int, default=7, help="최근 며칠치 (기본: 7)")
    parser.add_argument("--dry-run", action="store_true", help="변경 없이 확인만")
    args = parser.parse_args()

    cutoff = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    all_files = get_summary_files()
    tracked = get_tracked_summaries()

    keep = []
    remove = []

    for date_str, path in all_files:
        rel = f"data/{path.name}"
        if date_str >= cutoff:
            keep.append(rel)
        else:
            if rel in tracked:
                remove.append(rel)

    # 기간별 summary (YYYY-MM-DD_YYYY-MM-DD) — 모두 untrack
    range_tracked = [t for t in tracked if "_" in t.replace("data/summary_", "").replace(".json", "")]
    remove.extend(range_tracked)

    print(f"기준일: {cutoff} (최근 {args.days}일)")
    print(f"전체 일별 summary: {len(all_files)}개")
    print(f"유지 (git add): {len(keep)}개")
    for f in keep:
        print(f"  + {f}")
    print(f"제거 (git rm --cached): {len(remove)}개")
    if remove:
        for f in remove[:10]:
            print(f"  - {f}")
        if len(remove) > 10:
            print(f"  ... 외 {len(remove) - 10}개")

    if args.dry_run:
        print("\n[Dry Run] 실제 변경 없음.")
        return

    # git rm --cached (로컬 파일 유지)
    if remove:
        subprocess.run(
            ["git", "rm", "--cached", "--quiet"] + remove,
            capture_output=True, text=True
        )
        print(f"\n✓ {len(remove)}개 파일 git에서 제거 (로컬 유지)")

    # git add 최근 파일
    if keep:
        subprocess.run(
            ["git", "add"] + keep,
            capture_output=True, text=True
        )
        print(f"✓ {len(keep)}개 파일 staging 완료")

    print("\n준비 완료. 이제 commit & push 가능.")


if __name__ == "__main__":
    main()
