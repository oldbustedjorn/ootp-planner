from __future__ import annotations

import csv
import sys
from pathlib import Path


def read_header(path: Path) -> list[str]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        return next(reader)


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python compare_headers.py <old_csv> <new_csv>")
        sys.exit(1)

    old_path = Path(sys.argv[1])
    new_path = Path(sys.argv[2])

    old_header = read_header(old_path)
    new_header = read_header(new_path)

    old_set = set(old_header)
    new_set = set(new_header)

    only_in_old = [c for c in old_header if c not in new_set]
    only_in_new = [c for c in new_header if c not in old_set]
    in_both = [c for c in old_header if c in new_set]

    print("=" * 80)
    print("HEADER COMPARISON")
    print("=" * 80)
    print(f"Old file: {old_path}")
    print(f"New file: {new_path}")
    print()

    print(f"Old column count: {len(old_header)}")
    print(f"New column count: {len(new_header)}")
    print(f"Columns in both:  {len(in_both)}")
    print()

    print("-" * 80)
    print("ONLY IN OLD")
    print("-" * 80)
    if only_in_old:
        for col in only_in_old:
            print(col)
    else:
        print("(none)")
    print()

    print("-" * 80)
    print("ONLY IN NEW")
    print("-" * 80)
    if only_in_new:
        for col in only_in_new:
            print(col)
    else:
        print("(none)")
    print()

    print("-" * 80)
    print("ORDER DIFFERENCES (shared columns in different positions)")
    print("-" * 80)
    order_diffs = []
    for col in in_both:
        old_idx = old_header.index(col)
        new_idx = new_header.index(col)
        if old_idx != new_idx:
            order_diffs.append((col, old_idx, new_idx))

    if order_diffs:
        for col, old_idx, new_idx in order_diffs:
            print(f"{col}: old={old_idx}, new={new_idx}")
    else:
        print("(none)")
    print()

    print("-" * 80)
    print("FULL NEW HEADER")
    print("-" * 80)
    print(",".join(new_header))


if __name__ == "__main__":
    main()
