"""Build an independently installable HK ALS regional pack from saved sources."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("schema", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--source-date", required=True)
    parser.add_argument("--pack-version", required=True)
    parser.add_argument('--quarantine-invalid', action='store_true',
                        help='Explicitly exclude invalid features and mark partial source coverage; retain every locator')
    args = parser.parse_args()
    from world_address_engine.data.hk_als_builder import build_als_pack
    def progress(event):
        print(json.dumps(event), flush=True)
    try:
        manifest = build_als_pack(args.archive, args.schema, args.output_dir,
                                  source_date=args.source_date, pack_version=args.pack_version,
                                  on_progress=progress, quarantine_invalid=args.quarantine_invalid)
    except Exception as exc:
        print(f"Build failed ({type(exc).__name__}); inspect aggregate audit.json if created.", file=sys.stderr)
        return 1
    print(json.dumps(manifest, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
