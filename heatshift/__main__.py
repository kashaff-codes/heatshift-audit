"""CLI: python -m heatshift audit --lat .. --lon .. --date YYYY-MM-DD [...]"""

from __future__ import annotations

import argparse
import sys

from . import config
from .audit import AuditInputs, InputError, plan, run_audit, validate
from .cache import DiskCache, NullCache
from .client import FortyGuardClient, FortyGuardError
from .report import print_report, save


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="heatshift", description="Heat Shift Audit — hour-by-hour heat stress "
                                "for a US work site on a past date, built on FortyGuard.")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit", help="audit one site and date")
    a.add_argument("--lat", type=float, required=True)
    a.add_argument("--lon", type=float, required=True)
    a.add_argument("--date", required=True, help="YYYY-MM-DD (past date, >= %s)" % config.EARLIEST_DATE)
    a.add_argument("--start", default="06:00", help="local HH:MM (default 06:00)")
    a.add_argument("--end", default="18:00", help="local HH:MM, inclusive (default 18:00)")
    a.add_argument("--every", type=int, default=3, help="sample every N hours (default 3)")
    a.add_argument("--name", help="site name used in output file names")
    a.add_argument("--env-mode", choices=["range", "per-hour"], default="range",
                   help="range: 1 env_params call for the window (default, cheaper); per-hour: 1 call per hour")
    a.add_argument("--granularity", type=int, default=config.HEATMAP_GRANULARITY_M, choices=[60, 80, 100])
    a.add_argument("--aoi-side", type=float, default=config.AOI_SIDE_M, help="AOI square side in metres")
    a.add_argument("--wet-bulb-warn", type=float, default=config.WET_BULB_WARN_C,
                   help="illustrative wet-bulb warning threshold °C (default %(default)s)")
    a.add_argument("--concurrency", type=int, default=2, help="parallel API jobs (default 2)")
    a.add_argument("--out", default="runs", help="output directory (default runs/)")
    a.add_argument("--no-cache", action="store_true", help="ignore the disk cache (re-runs are charged again!)")
    a.add_argument("--dry-run", action="store_true", help="print planned calls and credits; make no paid calls")
    a.add_argument("--yes", "-y", action="store_true", help="skip the confirmation prompt")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    inp = AuditInputs(lat=args.lat, lon=args.lon, date=args.date, start=args.start, end=args.end,
                      every=args.every, name=args.name, env_mode=args.env_mode, granularity=args.granularity,
                      aoi_side_m=args.aoi_side, wet_bulb_warn_c=args.wet_bulb_warn, concurrency=args.concurrency)
    try:
        hours = validate(inp)
    except InputError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    cache = NullCache() if args.no_cache else DiskCache()
    try:
        client = FortyGuardClient.from_env(cache=cache)
    except FortyGuardError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    calls = plan(inp, hours, client)
    total = sum(c.credits for c in calls)
    print(f"Heat Shift Audit — {inp.site_name} — {inp.date}, sampled hours: {', '.join(hours)}")
    print(f"Planned FortyGuard calls ({inp.env_mode} env mode):")
    for c in calls:
        cost = "cached, 0 credits" if c.cached else f"{config.CREDIT_COST[c.endpoint]:,} credits"
        print(f"  POST {c.endpoint:<15} {c.label:<32} {cost}")
    print(f"Estimated total: {total:,} credits"
          + ("" if all(c.body for c in calls) else " (env_params cache status known only after heatmaps)"))

    if args.dry_run:
        print("Dry run: no paid calls made.")
        return 0
    if total > 0 and not args.yes:
        if not sys.stdin.isatty():
            print("Refusing to spend credits without confirmation (no TTY). Re-run with --yes.", file=sys.stderr)
            return 3
        if input("Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Cancelled; no paid calls made.")
            return 0

    client.log = lambda m: print(f"  · {m}", flush=True)
    try:
        res = run_audit(inp, client, hours)
    except FortyGuardError as exc:
        print(f"FortyGuard error: {exc}", file=sys.stderr)
        return 1
    print_report(res)
    jp, mp = save(res, args.out)
    print(f"\nSaved {jp} and {mp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
