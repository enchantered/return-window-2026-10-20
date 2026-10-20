from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HEADERS = ("id", "item", "retailer", "purchased_on", "return_by", "status")
MAX_LENGTHS = {"id": 128, "item": 200, "retailer": 120}
STATUSES = {"open", "returned", "kept"}
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


class DataError(ValueError):
    """Invalid purchase data or calendar range."""


def _date(value: str, field: str, row: int) -> date:
    if not _DATE.fullmatch(value):
        raise DataError(f"row {row}: {field} must be a strict YYYY-MM-DD date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DataError(f"row {row}: {field} is not a valid calendar date") from exc


def load_purchases(path: str | Path) -> list[dict[str, str | date]]:
    """Read and validate the exact, six-column CSV format without modifying it."""
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            try:
                header = next(reader)
            except StopIteration as exc:
                raise DataError("CSV is empty; expected header: " + ",".join(HEADERS)) from exc
            if len(header) != len(set(header)):
                raise DataError("CSV header contains duplicate column names")
            if tuple(header) != HEADERS:
                raise DataError("CSV header must be exactly: " + ",".join(HEADERS))
            rows: list[dict[str, str | date]] = []
            ids: set[str] = set()
            for row_number, values in enumerate(reader, start=2):
                if len(values) != len(HEADERS):
                    raise DataError(f"row {row_number}: expected {len(HEADERS)} columns, found {len(values)}")
                raw = dict(zip(HEADERS, values))
                for key in HEADERS:
                    if not raw[key] or not raw[key].strip():
                        raise DataError(f"row {row_number}: {key} must not be empty")
                for key, limit in MAX_LENGTHS.items():
                    if len(raw[key]) > limit:
                        raise DataError(f"row {row_number}: {key} exceeds maximum length {limit}")
                if raw["id"] in ids:
                    raise DataError(f"row {row_number}: duplicate id {raw['id']!r}")
                ids.add(raw["id"])
                if raw["status"] not in STATUSES:
                    raise DataError(f"row {row_number}: unsupported status {raw['status']!r}; use open, returned, or kept")
                purchased = _date(raw["purchased_on"], "purchased_on", row_number)
                deadline = _date(raw["return_by"], "return_by", row_number)
                if deadline < purchased:
                    raise DataError(f"row {row_number}: return_by must not precede purchased_on")
                rows.append({**raw, "purchased_on": purchased, "return_by": deadline})
            return rows
    except (csv.Error, UnicodeError) as exc:
        raise DataError(f"invalid CSV: {exc}") from exc


def select_deadlines(purchases: list[dict[str, str | date]], as_of: date, within: int) -> list[dict[str, str | int]]:
    """Return open rows overdue or due in [as_of, as_of + within], sorted by deadline."""
    try:
        last_day = as_of + timedelta(days=within)
    except OverflowError:
        last_day = date.max
    selected = []
    for purchase in purchases:
        if purchase["status"] != "open":
            continue
        deadline = purchase["return_by"]
        assert isinstance(deadline, date)
        if deadline < as_of or deadline <= last_day:
            selected.append({
                "id": str(purchase["id"]), "item": str(purchase["item"]),
                "retailer": str(purchase["retailer"]), "return_by": deadline.isoformat(),
                "days_remaining": (deadline - as_of).days,
            })
    return sorted(selected, key=lambda e: (e["return_by"], e["id"]))


def _escape_ical(value: str) -> str:
    # RFC 5545 TEXT escaping; normalize all source newline spellings first.
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\\", "\\\\").replace("\n", "\\n")
    return value.replace(",", "\\,").replace(";", "\\;")


def _fold(line: str) -> str:
    """Fold content lines at 75 UTF-8 octets, continuation space included."""
    output: list[str] = []
    current = ""
    limit = 75
    for char in line:
        encoded_len = len(char.encode("utf-8"))
        if len(current.encode("utf-8")) + encoded_len > limit:
            output.append(current)
            current = " "
            limit = 75
        current += char
    output.append(current)
    return "\r\n".join(output)


def make_calendar(entries: list[dict[str, str | int]], *, generated_at: datetime | None = None) -> str:
    """Build RFC 5545 VCALENDAR with all-day events spanning the deadline date."""
    generated_at = generated_at or datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise DataError("calendar generation timestamp must include a timezone")
    utc = generated_at.astimezone(timezone.utc)
    stamp = f"{utc.year:04d}{utc.month:02d}{utc.day:02d}T{utc.hour:02d}{utc.minute:02d}{utc.second:02d}Z"

    def ical_date(value):
        return f"{value.year:04d}{value.month:02d}{value.day:02d}"

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Return Window//EN", "CALSCALE:GREGORIAN"]
    for entry in entries:
        deadline = date.fromisoformat(str(entry["return_by"]))
        try:
            next_day = deadline + timedelta(days=1)
        except OverflowError as exc:
            raise DataError(f"cannot create all-day event ending after {deadline.isoformat()} (year 9999 limit)") from exc
        item_id = str(entry["id"])
        uid = hashlib.sha256((item_id + "\0" + deadline.isoformat()).encode("utf-8")).hexdigest() + "@return-window"
        lines.extend((
            "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{ical_date(deadline)}",
            f"DTEND;VALUE=DATE:{ical_date(next_day)}", f"SUMMARY:{_escape_ical('Return by: ' + str(entry['item']))}",
            f"DESCRIPTION:{_escape_ical('Return deadline for ' + str(entry['item']) + ' at ' + str(entry['retailer']) + ' (id ' + item_id + '). Verify the retailer policy; dates are manually entered.')}",
            "END:VEVENT",
        ))
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
