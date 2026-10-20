# Return Window

A small, offline Python 3.11+ command-line tool for tracking **return dates you enter yourself**. It does not infer dates or retailer rules, and it does not sync calendars, send reminders, or contact retailers.

The [dated research note](docs/2026-10-20-research.md) explains the evidence, existing alternatives and untested demand hypothesis. The [consumer-behavior history](docs/consumer-behavior-log.md) preserves prior observations about AI apps versus established notes, spreadsheets and calendars. This is an independently implemented portfolio prototype, not a retailer service or a validated business.

## Quick start

No installation or third-party packages are needed. From this directory:

```sh
python3 --version
python3 -m return_window list examples/purchases.csv --as-of 2026-10-20 --within 14
python3 -m return_window list examples/purchases.csv --as-of 2026-10-20 --within 14 --json
python3 -m return_window calendar examples/purchases.csv --as-of 2026-10-20 --within 14 > return-deadlines.ics
```

Open the generated `.ics` file in a calendar app if desired. The calendar command writes only to standard output; redirecting it to a file is your choice. The list reports overdue open entries separately and upcoming entries through the specified number of **calendar** days, inclusive. Weekends and holidays are not excluded. A deadline today has zero days remaining. Returned and kept entries are omitted. With no `--as-of`, the machine's local current date is used; specify it in scripts and tests for repeatability. `--within` must be a nonnegative integer (default 14).

## CSV format

The header must be exactly this sequence:

```csv
id,item,retailer,purchased_on,return_by,status
```

- `id`: unique, nonempty identifier (up to 128 characters).
- `item`: nonempty item description (up to 200 characters).
- `retailer`: nonempty retailer name (up to 120 characters).
- `purchased_on`: purchase date in strict `YYYY-MM-DD` format and a real calendar date.
- `return_by`: manually verified deadline, also a strict real `YYYY-MM-DD` date.
- `status`: exactly `open`, `returned`, or `kept`.

Use one CSV row per purchase; quote fields containing commas or line breaks according to standard CSV rules. The example file is synthetic and demonstrates the format only; it is not a policy recommendation. Fix validation errors in your CSV and rerun the command. The input file is read-only from this program's perspective; no database or other state is created.

The return deadline must not precede the purchase date. Calendar exports include the generation time in UTC (`DTSTAMP`), so re-exporting later changes that timestamp while keeping each event UID stable. UIDs depend on the purchase ID and deadline: changing the deadline changes the UID, and calendar importers may create a new event rather than update the old one. Actual calendar-app imports and duplicate handling still need user testing.

## Date and calendar behavior

Return Window uses the entered `return_by` date as a calendar date. For list filtering, open deadlines before `--as-of` are overdue; other entries qualify from `--as-of` through `--as-of + --within`, inclusive. The calendar export represents each deadline as an all-day event with `DTSTART` on the entered date and exclusive `DTEND` on the following date (the standard half-open interval for one all-day day). IDs and dates determine stable event UIDs. Calendar text is escaped against iCalendar field injection and lines are folded by UTF-8 octets. An event ending after year 9999 cannot be represented and is rejected cleanly.

## Privacy and limitations

All processing is local and offline. Purchase information stays in the CSV you provide; **local does not mean encrypted**. Protect the file and backups using your device's security practices. The tool does not fetch, synchronize, validate, or guarantee any retailer's policy, holidays, or eligibility. Manually verify the retailer's actual return terms. There are no autonomous reminders: the CLI only reports deadlines when you run it.

## Project structure and tests

- `return_window/__main__.py`: CLI parsing, presentation, and error reporting.
- `return_window/core.py`: CSV validation, calendar-day selection, and iCalendar generation.
- `examples/purchases.csv`: synthetic sample input.
- `tests/`: offline `unittest` regression suite.

Run tests with:

```sh
python3 -m unittest discover -s tests -v
```
