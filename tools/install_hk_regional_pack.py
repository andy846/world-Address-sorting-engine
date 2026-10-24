"""Verify and install an extracted Hong Kong regional pack, entirely offline."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True,
                        help='Extracted folder containing pack.db and manifest.json')
    parser.add_argument('--active-root', type=Path, required=True)
    args = parser.parse_args()
    from world_address_engine.data.hk_regional import install_hk_pack, hk_pack_metadata
    try:
        installed = install_hk_pack(args.source_dir, args.active_root)
        print(json.dumps(hk_pack_metadata(installed), ensure_ascii=True, indent=2))
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
