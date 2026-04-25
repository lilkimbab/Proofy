from __future__ import annotations

from app.db.content_repository import DATA_CONTENT_ROOT, sync_seed_bundles_to_data


def main() -> None:
    written = sync_seed_bundles_to_data(overwrite=True)
    print(f"[content-sync] target={DATA_CONTENT_ROOT}")
    for path in written:
        print(f"[content-sync] wrote {path.name}")


if __name__ == "__main__":
    main()
