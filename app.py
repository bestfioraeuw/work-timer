#!/usr/bin/env python3
"""Local work clock. Run: python app.py"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import webbrowser
import zipfile
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "clock.db"
STATIC = ROOT / "static"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8765"))


def now_ts() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def today() -> str:
    return date.today().isoformat()


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def minutes_between(start: str, end: str) -> int:
    return max(0, int((parse_dt(end) - parse_dt(start)).total_seconds() // 60))


def fmt_hm(minutes: int) -> str:
    hours, mins = divmod(max(0, minutes), 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS days (
            date TEXT PRIMARY KEY,
            clock_in TEXT,
            clock_out TEXT,
            note TEXT NOT NULL DEFAULT ''
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS segments (
            id INTEGER PRIMARY KEY,
            date TEXT NOT NULL,
            task TEXT NOT NULL,
            start TEXT NOT NULL,
            end TEXT,
            kind TEXT NOT NULL DEFAULT 'work'
        )
        """
    )
    cols = {row[1] for row in con.execute("PRAGMA table_info(segments)")}
    if "kind" not in cols:
        con.execute(
            "ALTER TABLE segments ADD COLUMN kind TEXT NOT NULL DEFAULT 'work'"
        )
    return con


def ensure_day(con: sqlite3.Connection, day: str) -> None:
    con.execute("INSERT OR IGNORE INTO days(date) VALUES (?)", (day,))


def punch_minutes(clock_in: str | None, clock_out: str | None, until: str) -> int:
    if not clock_in:
        return 0
    return minutes_between(clock_in, clock_out or until)


def segment_minutes(start: str, end: str | None, until: str) -> int:
    return minutes_between(start, end or until)


def day_payload(con: sqlite3.Connection, day: str, until: str | None = None) -> dict:
    ensure_day(con, day)
    row = con.execute("SELECT * FROM days WHERE date = ?", (day,)).fetchone()
    segs = con.execute(
        "SELECT * FROM segments WHERE date = ? ORDER BY id", (day,)
    ).fetchall()
    until = until or now_ts()
    segments = []
    work_minutes = 0
    rest_minutes = 0
    for seg in segs:
        kind = seg["kind"] or "work"
        mins = segment_minutes(seg["start"], seg["end"], until)
        if kind == "rest":
            rest_minutes += mins
        else:
            work_minutes += mins
        segments.append(
            {
                "id": seg["id"],
                "task": seg["task"],
                "kind": kind,
                "start": seg["start"],
                "end": seg["end"],
                "minutes": mins,
                "running": seg["end"] is None,
            }
        )
    running = next((s for s in segments if s["running"]), None)
    return {
        "date": row["date"],
        "clock_in": row["clock_in"],
        "clock_out": row["clock_out"],
        "note": row["note"],
        "mode": running["kind"] if running else None,
        "punch_minutes": punch_minutes(row["clock_in"], row["clock_out"], until),
        "work_minutes": work_minutes,
        "rest_minutes": rest_minutes,
        "task_minutes": work_minutes,
        "segments": segments,
    }


def range_totals(
    con: sqlite3.Connection, start: str, end: str, until: str | None = None
) -> dict:
    until = until or now_ts()
    days = con.execute(
        "SELECT * FROM days WHERE date BETWEEN ? AND ?", (start, end)
    ).fetchall()
    segs = con.execute(
        "SELECT * FROM segments WHERE date BETWEEN ? AND ?", (start, end)
    ).fetchall()
    punch = sum(punch_minutes(d["clock_in"], d["clock_out"], until) for d in days)
    work = sum(
        segment_minutes(s["start"], s["end"], until)
        for s in segs
        if (s["kind"] or "work") != "rest"
    )
    rest = sum(
        segment_minutes(s["start"], s["end"], until)
        for s in segs
        if s["kind"] == "rest"
    )
    return {
        "punch_minutes": punch,
        "work_minutes": work,
        "rest_minutes": rest,
        "task_minutes": work,
    }


def stats_payload(con: sqlite3.Connection, day: str, until: str | None = None) -> dict:
    until = until or now_ts()
    d = date.fromisoformat(day)
    week_start = d - timedelta(days=d.weekday())
    week_end = week_start + timedelta(days=6)
    month_start = d.replace(day=1)
    if d.month == 12:
        month_end = d.replace(year=d.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = d.replace(month=d.month + 1, day=1) - timedelta(days=1)
    year_start = d.replace(month=1, day=1)
    year_end = d.replace(month=12, day=31)
    today_row = day_payload(con, day, until)
    week = range_totals(con, week_start.isoformat(), week_end.isoformat(), until)
    month = range_totals(con, month_start.isoformat(), month_end.isoformat(), until)
    year = range_totals(con, year_start.isoformat(), year_end.isoformat(), until)
    return {
        "today": {
            "punch_minutes": today_row["punch_minutes"],
            "work_minutes": today_row["work_minutes"],
            "rest_minutes": today_row["rest_minutes"],
            "task_minutes": today_row["work_minutes"],
        },
        "week": week,
        "month": month,
        "year": year,
    }


def clock_in(con: sqlite3.Connection, day: str, ts: str | None = None) -> dict:
    ensure_day(con, day)
    row = con.execute("SELECT clock_in FROM days WHERE date = ?", (day,)).fetchone()
    if not row["clock_in"]:
        con.execute(
            "UPDATE days SET clock_in = ? WHERE date = ?", (ts or now_ts(), day)
        )
        con.commit()
    return day_payload(con, day)


def compose_ts(day: str, hm: str) -> str:
    raw = (hm or "").strip()
    if len(raw) >= 5 and raw[2] == ":":
        hour, minute = raw[:2], raw[3:5]
        if hour.isdigit() and minute.isdigit():
            h, m = int(hour), int(minute)
            if 0 <= h <= 23 and 0 <= m <= 59:
                return f"{day} {h:02d}:{m:02d}:00"
    raise ValueError("时间格式为 HH:MM")


def reset_clock_out(con: sqlite3.Connection, day: str) -> dict:
    ensure_day(con, day)
    row = con.execute("SELECT clock_out FROM days WHERE date = ?", (day,)).fetchone()
    old = row["clock_out"]
    if not old:
        return day_payload(con, day)
    con.execute("UPDATE days SET clock_out = NULL WHERE date = ?", (day,))
    con.execute(
        "UPDATE segments SET end = NULL WHERE date = ? AND end = ?", (day, old)
    )
    con.commit()
    return day_payload(con, day)


def calibrate(
    con: sqlite3.Connection,
    day: str,
    clock_in_hm: str,
    clock_out_hm: str | None,
) -> dict:
    ensure_day(con, day)
    stamp_in = compose_ts(day, clock_in_hm)
    stamp_out = compose_ts(day, clock_out_hm) if (clock_out_hm or "").strip() else None
    if stamp_out and stamp_out < stamp_in:
        raise ValueError("下班不能早于上班")
    old = con.execute("SELECT clock_out FROM days WHERE date = ?", (day,)).fetchone()[
        "clock_out"
    ]
    con.execute(
        "UPDATE days SET clock_in = ?, clock_out = ? WHERE date = ?",
        (stamp_in, stamp_out, day),
    )
    if stamp_out:
        con.execute(
            "UPDATE segments SET end = ? WHERE date = ? AND end IS NULL",
            (stamp_out, day),
        )
    elif old:
        con.execute(
            "UPDATE segments SET end = NULL WHERE date = ? AND end = ?", (day, old)
        )
    con.commit()
    return day_payload(con, day)


def clock_out(con: sqlite3.Connection, day: str, ts: str | None = None) -> dict:
    ensure_day(con, day)
    row = con.execute("SELECT clock_in FROM days WHERE date = ?", (day,)).fetchone()
    if not row["clock_in"]:
        raise ValueError("请先上班打卡")
    stamp = ts or now_ts()
    con.execute("UPDATE days SET clock_out = ? WHERE date = ?", (stamp, day))
    con.execute(
        "UPDATE segments SET end = ? WHERE date = ? AND end IS NULL", (stamp, day)
    )
    con.commit()
    return day_payload(con, day)


def start_segment(
    con: sqlite3.Connection,
    day: str,
    task: str,
    ts: str | None = None,
    kind: str = "work",
) -> dict:
    kind = "rest" if kind == "rest" else "work"
    task = (task or "").strip()
    if kind == "rest":
        task = task or "休息"
    elif not task:
        last = con.execute(
            """
            SELECT task FROM segments
            WHERE date = ? AND kind = 'work'
            ORDER BY id DESC LIMIT 1
            """,
            (day,),
        ).fetchone()
        task = last["task"] if last else "工作"
    ensure_day(con, day)
    row = con.execute(
        "SELECT clock_in, clock_out FROM days WHERE date = ?", (day,)
    ).fetchone()
    if row["clock_out"]:
        raise ValueError("今日已下班")
    stamp = ts or now_ts()
    if not row["clock_in"]:
        con.execute(
            "UPDATE days SET clock_in = ? WHERE date = ?", (stamp, day)
        )
    con.execute(
        "UPDATE segments SET end = ? WHERE date = ? AND end IS NULL", (stamp, day)
    )
    con.execute(
        "INSERT INTO segments(date, task, start, kind) VALUES (?, ?, ?, ?)",
        (day, task, stamp, kind),
    )
    con.commit()
    return day_payload(con, day)


def stop_segment(con: sqlite3.Connection, day: str, ts: str | None = None) -> dict:
    stamp = ts or now_ts()
    con.execute(
        "UPDATE segments SET end = ? WHERE date = ? AND end IS NULL", (stamp, day)
    )
    con.commit()
    return day_payload(con, day)


def save_note(con: sqlite3.Connection, day: str, note: str) -> dict:
    ensure_day(con, day)
    con.execute("UPDATE days SET note = ? WHERE date = ?", (note, day))
    con.commit()
    return day_payload(con, day)


EXPORT_HEADERS = ("日期", "类型", "事项", "开始", "结束", "时长分钟", "上班", "下班", "日报")


def hhmm(ts: str | None) -> str:
    return ts[11:16] if ts else ""


def recorded_days(con: sqlite3.Connection, year: int):
    start, end = f"{year}-01-01", f"{year}-12-31"
    days = con.execute(
        """
        SELECT * FROM days
        WHERE date BETWEEN ? AND ?
          AND (
            clock_in IS NOT NULL
            OR note != ''
            OR EXISTS(SELECT 1 FROM segments s WHERE s.date = days.date)
          )
        ORDER BY date
        """,
        (start, end),
    ).fetchall()
    return start, end, days


def punched_dates(con: sqlite3.Connection, year: int) -> list[str]:
    start, end = f"{year}-01-01", f"{year}-12-31"
    return [
        row["date"]
        for row in con.execute(
            """
            SELECT date FROM days
            WHERE date BETWEEN ? AND ?
              AND clock_in IS NOT NULL
            ORDER BY date
            """,
            (start, end),
        )
    ]


def export_rows(
    con: sqlite3.Connection, year: int, until: str | None = None
) -> list[tuple]:
    until = until or now_ts()
    _, _, days = recorded_days(con, year)
    rows: list[tuple] = []
    for row in days:
        segs = con.execute(
            "SELECT * FROM segments WHERE date = ? ORDER BY id", (row["date"],)
        ).fetchall()
        note = (row["note"] or "").strip()
        punch_in, punch_out = hhmm(row["clock_in"]), hhmm(row["clock_out"])
        if not segs:
            rows.append(
                (
                    row["date"],
                    "日报" if note else "打卡",
                    "",
                    "",
                    "",
                    0,
                    punch_in,
                    punch_out,
                    note,
                )
            )
            continue
        for seg in segs:
            rest = seg["kind"] == "rest"
            rows.append(
                (
                    row["date"],
                    "休息" if rest else "工作",
                    "休息" if rest else (seg["task"] or ""),
                    hhmm(seg["start"]),
                    hhmm(seg["end"]) if seg["end"] else "进行中",
                    segment_minutes(seg["start"], seg["end"], until),
                    punch_in,
                    punch_out,
                    note,
                )
            )
    return rows


def _xlsx_text(value: object) -> str:
    raw = "".join(
        ch
        for ch in str(value)
        if ch in "\t\n\r" or ord(ch) >= 32
    )
    return escape(raw, {'"': "&quot;"})


def _xlsx_col(index: int) -> str:
    name = ""
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def render_xlsx(headers: tuple[str, ...], rows: list[tuple]) -> bytes:
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        '<cols>',
        '<col min="1" max="1" width="12"/>',
        '<col min="2" max="2" width="8"/>',
        '<col min="3" max="3" width="20"/>',
        '<col min="4" max="5" width="8"/>',
        '<col min="6" max="6" width="10"/>',
        '<col min="7" max="8" width="8"/>',
        '<col min="9" max="9" width="40"/>',
        "</cols>",
        "<sheetData>",
    ]
    for r, values in enumerate((headers, *rows), start=1):
        cells = []
        for c, value in enumerate(values, start=1):
            ref = f"{_xlsx_col(c)}{r}"
            if isinstance(value, int):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(
                    f'<c r="{ref}" t="inlineStr"><is>'
                    f'<t xml:space="preserve">{_xlsx_text(value)}</t>'
                    f"</is></c>"
                )
        lines.append(f'<row r="{r}">{"".join(cells)}</row>')
    lines += ["</sheetData>", "</worksheet>"]
    sheet = "".join(lines)
    parts = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="工作记录" sheetId="1" r:id="rId1"/></sheets>'
            "</workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        ),
        "xl/worksheets/sheet1.xml": sheet,
    }
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in parts.items():
            zf.writestr(name, content.encode("utf-8"))
    return buf.getvalue()


def render_export(con: sqlite3.Connection, year: int, until: str | None = None) -> str:
    until = until or now_ts()
    start, end, days = recorded_days(con, year)
    totals = range_totals(con, start, end, until)
    lines = [
        f"# {year} 工作记录",
        "",
        f"- 打卡合计：{fmt_hm(totals['punch_minutes'])}（含休息）",
        f"- 工作合计：{fmt_hm(totals['work_minutes'])}",
        f"- 休息合计：{fmt_hm(totals['rest_minutes'])}",
        f"- 有记录天数：{len(days)}",
        "",
    ]
    for row in days:
        segs = con.execute(
            "SELECT * FROM segments WHERE date = ? ORDER BY id", (row["date"],)
        ).fetchall()
        punch = punch_minutes(row["clock_in"], row["clock_out"], until)
        work_mins = sum(
            segment_minutes(s["start"], s["end"], until)
            for s in segs
            if (s["kind"] or "work") != "rest"
        )
        rest_mins = sum(
            segment_minutes(s["start"], s["end"], until)
            for s in segs
            if s["kind"] == "rest"
        )
        clock = "未打卡"
        if row["clock_in"]:
            clock = f"{hhmm(row['clock_in'])} – {hhmm(row['clock_out']) or '进行中'}"
        lines += [
            f"## {row['date']}",
            "",
            f"- 打卡：{clock}（{fmt_hm(punch)}，含休息）",
            f"- 工作：{fmt_hm(work_mins)}",
            f"- 休息：{fmt_hm(rest_mins)}",
        ]
        if segs:
            lines.append("- 分段：")
            for seg in segs:
                end_s = seg["end"][11:16] if seg["end"] else "进行中"
                mins = segment_minutes(seg["start"], seg["end"], until)
                label = "休息" if seg["kind"] == "rest" else seg["task"]
                lines.append(
                    f"  - {label} {seg['start'][11:16]}–{end_s}（{fmt_hm(mins)}）"
                )
        note = (row["note"] or "").strip()
        lines.append("- 日报：")
        lines.append("")
        lines.append(note if note else "（无）")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} {fmt % args}")

    def _send(self, code: int, body: bytes, content_type: str, headers=None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload) -> None:
        self._send(
            code,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw or b"{}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if parsed.path in ("/", "/index.html"):
            html = (STATIC / "index.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/img/"):
            name = Path(parsed.path).name
            file = (STATIC / "img" / name).resolve()
            root = (STATIC / "img").resolve()
            if file.is_file() and file.parent == root:
                suffix = file.suffix.lower()
                ctype = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".webp": "image/webp",
                }.get(suffix, "application/octet-stream")
                self._send(200, file.read_bytes(), ctype)
                return
        con = connect()
        try:
            if parsed.path == "/api/day":
                self._json(200, day_payload(con, qs.get("date", [today()])[0]))
                return
            if parsed.path == "/api/stats":
                self._json(200, stats_payload(con, qs.get("date", [today()])[0]))
                return
            if parsed.path == "/api/punched":
                year = int(qs.get("year", [str(date.today().year)])[0])
                self._json(200, {"dates": punched_dates(con, year)})
                return
            if parsed.path == "/api/export":
                year = int(qs.get("year", [str(date.today().year)])[0])
                fmt = (qs.get("format", ["md"])[0] or "md").lower()
                if fmt in ("xlsx", "excel"):
                    body = render_xlsx(EXPORT_HEADERS, export_rows(con, year))
                    name = f"work-{year}.xlsx"
                    ctype = (
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    )
                elif fmt in ("md", "markdown"):
                    body = render_export(con, year).encode("utf-8")
                    name = f"work-{year}.md"
                    ctype = "text/markdown; charset=utf-8"
                else:
                    raise ValueError("导出格式为 md 或 xlsx")
                self._send(
                    200,
                    body,
                    ctype,
                    {"Content-Disposition": f'attachment; filename="{name}"'},
                )
                return
        except (ValueError, KeyError) as exc:
            self._json(400, {"error": str(exc)})
            return
        finally:
            con.close()
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            body = self._read_json()
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid json"})
            return
        day = body.get("date") or today()
        con = connect()
        try:
            if parsed.path == "/api/clock-in":
                self._json(200, clock_in(con, day))
                return
            if parsed.path == "/api/clock-out":
                self._json(200, clock_out(con, day))
                return
            if parsed.path == "/api/reset-out":
                self._json(200, reset_clock_out(con, day))
                return
            if parsed.path == "/api/calibrate":
                self._json(
                    200,
                    calibrate(
                        con,
                        day,
                        body.get("clock_in", ""),
                        body.get("clock_out"),
                    ),
                )
                return
            if parsed.path == "/api/segment/start":
                self._json(
                    200,
                    start_segment(
                        con,
                        day,
                        body.get("task", ""),
                        kind=body.get("kind", "work"),
                    ),
                )
                return
            if parsed.path == "/api/segment/stop":
                self._json(200, stop_segment(con, day))
                return
            if parsed.path == "/api/note":
                self._json(200, save_note(con, day, body.get("note", "")))
                return
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return
        finally:
            con.close()
        self._json(404, {"error": "not found"})


def listening() -> bool:
    probe = "127.0.0.1" if HOST in ("0.0.0.0", "::") else HOST
    try:
        with socket.create_connection((probe, PORT), 0.3):
            return True
    except OSError:
        return False


def page_url() -> str:
    host = "127.0.0.1" if HOST in ("0.0.0.0", "::") else HOST
    return f"http://{host}:{PORT}/"


def open_page(url: str) -> None:
    if sys.platform == "darwin":
        try:
            subprocess.Popen(["open", url])
            return
        except OSError:
            pass
    webbrowser.open(url)


def main() -> None:
    url = page_url()
    want_open = "--open" in sys.argv
    if listening():
        if want_open:
            open_page(url)
        return
    connect().close()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    if want_open:
        open_page(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
