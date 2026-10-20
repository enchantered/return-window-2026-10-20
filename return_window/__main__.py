from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .core import DataError, load_purchases, make_calendar, select_deadlines


def _iso_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use a valid ISO date (YYYY-MM-DD)") from exc
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError("use a valid ISO date (YYYY-MM-DD)")
    return parsed


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m return_window", description="Track manually entered return deadlines.")
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("list", "calendar"):
        cmd = sub.add_parser(name, help="show actionable deadlines" if name == "list" else "export deadlines as an iCalendar file")
        cmd.add_argument("csv_file", type=Path, help="purchase CSV file")
        cmd.add_argument("--as-of", type=_iso_date, default=date.today(), help="reference date YYYY-MM-DD (default: local today)")
        cmd.add_argument("--within", type=int, default=14, help="include open deadlines due within this many calendar days (default: 14)")
        if name == "list":
            cmd.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.within < 0:
        print("error: --within must be zero or greater", file=sys.stderr)
        return 2
    try:
        purchases = load_purchases(args.csv_file)
        entries = select_deadlines(purchases, args.as_of, args.within)
        if args.command == "calendar":
            sys.stdout.write(make_calendar(entries))
        elif args.json:
            print(json.dumps(entries, ensure_ascii=False, indent=2))
        else:
            overdue = [e for e in entries if e["days_remaining"] < 0]
            upcoming = [e for e in entries if e["days_remaining"] >= 0]
            print("OVERDUE — contact the retailer promptly; return eligibility is not guaranteed.")
            if overdue:
                for e in overdue:
                    print(f"  {e['id']}  {e['item']} ({e['retailer']}) — return-by {e['return_by']} ({-e['days_remaining']} days overdue)")
            else:
                print("  None")
            print(f"OPEN RETURN DEADLINES — due within {args.within} calendar days (inclusive)")
            if upcoming:
                for e in upcoming:
                    remaining = e["days_remaining"]
                    urgency = "due today" if remaining == 0 else f"{remaining} calendar days left"
                    print(f"  {e['id']}  {e['item']} ({e['retailer']}) — return by {e['return_by']} ({urgency})")
            else:
                print("  None")
            print("Dates are manually supplied; verify policy with the retailer. No calendars or retailer policies are synced.")
    except (DataError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
