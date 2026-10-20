import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from return_window.core import DataError, load_purchases, make_calendar, select_deadlines

HEADER = "id,item,retailer,purchased_on,return_by,status\n"


class ReturnWindowTests(unittest.TestCase):
    def load(self, body):
        temp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", delete=False)
        self.addCleanup(Path(temp.name).unlink, missing_ok=True)
        try:
            temp.write(body)
            temp.close()
            return load_purchases(temp.name), Path(temp.name)
        except Exception:
            Path(temp.name).unlink(missing_ok=True)
            raise

    def test_inclusive_boundaries_and_overdue(self):
        rows, _ = self.load(HEADER + "a,Due now,Shop,2026-10-01,2026-10-20,open\n"
                            "b,At edge,Shop,2026-10-01,2026-11-03,open\n"
                            "c,Past edge,Shop,2026-10-01,2026-11-04,open\n"
                            "d,Yesterday,Shop,2026-10-01,2026-10-19,open\n")
        found = select_deadlines(rows, date(2026, 10, 20), 14)
        self.assertEqual([(x["id"], x["days_remaining"]) for x in found],
                         [("d", -1), ("a", 0), ("b", 14)])

    def test_statuses_excluded_and_weekend_is_calendar_day(self):
        rows, _ = self.load(HEADER + "a,Weekend,Shop,2026-10-01,2026-10-24,open\n"
                            "b,Returned,Shop,2026-10-01,2026-10-21,returned\n"
                            "c,Kept,Shop,2026-10-01,2026-10-21,kept\n")
        self.assertEqual([x["id"] for x in select_deadlines(rows, date(2026, 10, 23), 1)], ["a"])

    def test_bad_headers_duplicates_status_dates_and_lengths(self):
        for content in ("", "id,id,retailer,purchased_on,return_by,status\n",
                        "id,item,retailer,purchased_on,return_by,status\nx,x,Shop,2026-02-30,2026-03-01,open\n",
                        HEADER + "x,x,Shop,2026-01-01,2026-01-02,OPEN\n",
                        HEADER + "x,x,Shop,2026-01-01,2026-01-02,open,extra\n",
                        HEADER + "x," + "z" * 201 + ",Shop,2026-01-01,2026-01-02,open\n"):
            with self.subTest(content=content[:60]), self.assertRaises(DataError):
                rows, path = self.load(content)
                path.unlink(missing_ok=True)
        with self.assertRaises(DataError):
            self.load(HEADER + "x,a,Shop,2026-01-01,2026-01-02,open\nx,b,Shop,2026-01-01,2026-01-03,open\n")

    def test_ics_escape_unicode_fold_and_stable_uid(self):
        entry = {"id": "id;\n", "item": "カメラ,\n\"X\"", "retailer": "店\\, Inc", "return_by": "2026-10-20", "days_remaining": 0}
        generated_at = datetime(2026, 10, 20, 3, 30, tzinfo=timezone.utc)
        first = make_calendar([entry], generated_at=generated_at)
        self.assertEqual(first, make_calendar([entry], generated_at=generated_at))
        self.assertIn("DTSTAMP:20261020T033000Z", first)
        self.assertIn("DTEND;VALUE=DATE:20261021", first)
        self.assertIn("\\,", first)
        self.assertIn("\\n", first)
        self.assertIn("\\\\", first)
        for line in first.rstrip("\r\n").split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75)

    def test_overflow_is_clean_error(self):
        with self.assertRaises(DataError):
            make_calendar([{"id": "x", "item": "x", "retailer": "x", "return_by": "9999-12-31", "days_remaining": 0}])

    def test_calendar_dates_are_padded_for_early_years(self):
        entry = {"id": "x", "item": "x", "retailer": "x", "return_by": "0001-01-01"}
        calendar = make_calendar([entry])
        self.assertIn("DTSTART;VALUE=DATE:00010101", calendar)
        self.assertIn("DTEND;VALUE=DATE:00010102", calendar)
        with self.assertRaises(DataError):
            make_calendar([entry], generated_at=datetime(2026, 10, 20))

    def test_deadline_cannot_precede_purchase(self):
        with self.assertRaisesRegex(DataError, "precede"):
            self.load(HEADER + "x,item,shop,2026-10-20,2026-10-19,open\n")

    def test_reader_does_not_modify_source(self):
        rows, path = self.load(HEADER + "x,item,shop,2026-01-01,2026-01-02,open\n")
        before = path.read_bytes()
        load_purchases(path)
        self.assertEqual(path.read_bytes(), before)
        path.unlink()


if __name__ == "__main__":
    unittest.main()
