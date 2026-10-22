"""Prepare a GeoNames offline pack from files downloaded separately by an operator."""
import argparse
from pathlib import Path
from world_address_engine.data.geonames_builder import build_geonames_pack


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local English/Chinese GeoNames SQLite index")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", choices=["COMPACT_GLOBAL", "EXTENDED_GLOBAL"], default="COMPACT_GLOBAL")
    args = parser.parse_args()
    print(build_geonames_pack(args.source_dir, args.output, args.profile))


if __name__ == "__main__":
    main()
