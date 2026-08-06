from __future__ import annotations

import argparse

from ootp_opt.storage.import_preview import (
    preview_existing_state,
    render_import_preview,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview legacy preset and build-history import without writing."
    )
    parser.add_argument("--config", default="config.toml")
    parser.add_argument(
        "--history", default="outputs/roster_build_registry.json"
    )
    parser.add_argument(
        "--details", action="store_true", help="List every preset and build record."
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    preview = preview_existing_state(args.config, args.history)
    print(render_import_preview(preview, details=args.details))
    return 1 if preview.error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
