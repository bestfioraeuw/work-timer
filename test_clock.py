import json
from http.server import ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.request import Request, urlopen
from zipfile import ZipFile

import app


def test_minutes_and_export() -> None:
    assert app.minutes_between("2026-09-08 09:00:00", "2026-09-08 10:30:00") == 90
    assert app.fmt_hm(90) == "1h 30m"
    assert app.punch_minutes(None, None, "2026-09-08 18:00:00") == 0
    assert app.punch_minutes("2026-09-08 09:00:00", None, "2026-09-08 10:00:00") == 60

    with TemporaryDirectory() as tmp:
        con = app.connect(Path(tmp) / "t.db")
        app.clock_in(con, "2026-09-08", "2026-09-08 09:00:00")
        app.start_segment(con, "2026-09-08", "写需求", "2026-09-08 09:10:00")
        app.start_segment(con, "2026-09-08", "开发", "2026-09-08 10:10:00")
        app.stop_segment(con, "2026-09-08", "2026-09-08 12:10:00")
        app.save_note(con, "2026-09-08", "做完登录页")
        app.clock_out(con, "2026-09-08", "2026-09-08 18:00:00")
        day = app.day_payload(con, "2026-09-08")
        assert day["punch_minutes"] == 540
        assert day["task_minutes"] == 180
        assert [s["task"] for s in day["segments"]] == ["写需求", "开发"]
        assert day["segments"][0]["end"] == "2026-09-08 10:10:00"

        text = app.render_export(con, 2026, "2026-09-08 18:00:00")
        assert "# 2026 工作记录" in text
        assert "做完登录页" in text
        assert "写需求 09:10–10:10" in text
        assert "打卡合计：9h" in text
        assert "工作合计：3h" in text

        rows = app.export_rows(con, 2026, "2026-09-08 18:00:00")
        assert [row[2] for row in rows] == ["写需求", "开发"]
        assert rows[0][1] == "工作"
        assert rows[0][5] == 60
        assert rows[1][8] == "做完登录页"
        xlsx = app.render_xlsx(app.EXPORT_HEADERS, rows)
        assert xlsx.startswith(b"PK")
        sheet = ZipFile(BytesIO(xlsx)).read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "写需求" in sheet
        assert "做完登录页" in sheet
        assert app.punched_dates(con, 2026) == ["2026-09-08"]
        con.close()


def test_reset_and_calibrate() -> None:
    with TemporaryDirectory() as tmp:
        con = app.connect(Path(tmp) / "tune.db")
        app.clock_in(con, "2026-09-08", "2026-09-08 09:00:00")
        app.start_segment(con, "2026-09-08", "开发", "2026-09-08 09:10:00")
        app.clock_out(con, "2026-09-08", "2026-09-08 18:00:00")
        assert app.day_payload(con, "2026-09-08")["segments"][0]["end"] == "2026-09-08 18:00:00"

        reset = app.reset_clock_out(con, "2026-09-08")
        assert reset["clock_out"] is None
        assert reset["segments"][0]["end"] is None
        assert app.punched_dates(con, 2026) == ["2026-09-08"]

        tuned = app.calibrate(con, "2026-09-08", "09:15", "18:30")
        assert tuned["clock_in"] == "2026-09-08 09:15:00"
        assert tuned["clock_out"] == "2026-09-08 18:30:00"
        assert tuned["punch_minutes"] == 555
        try:
            app.calibrate(con, "2026-09-08", "19:00", "18:00")
            raise AssertionError("expected order error")
        except ValueError:
            pass
        con.close()


def test_work_and_rest_modes() -> None:
    with TemporaryDirectory() as tmp:
        con = app.connect(Path(tmp) / "mode.db")
        first = app.start_segment(
            con, "2026-09-08", "开发", "2026-09-08 09:00:00", kind="work"
        )
        assert first["clock_in"] == "2026-09-08 09:00:00"
        assert first["mode"] == "work"
        snap = app.day_payload(con, "2026-09-08", "2026-09-08 09:30:00")
        assert snap["work_minutes"] == 30
        assert snap["punch_minutes"] == 30

        app.start_segment(con, "2026-09-08", "", "2026-09-08 10:00:00", kind="rest")
        app.start_segment(con, "2026-09-08", "", "2026-09-08 10:20:00", kind="work")
        app.start_segment(con, "2026-09-08", "", "2026-09-08 12:00:00", kind="rest")
        app.clock_out(con, "2026-09-08", "2026-09-08 12:15:00")
        day = app.day_payload(con, "2026-09-08")
        assert day["mode"] is None
        assert day["punch_minutes"] == 195
        assert day["work_minutes"] == 160
        assert day["rest_minutes"] == 35
        rests = [s for s in day["segments"] if s["kind"] == "rest"]
        works = [s for s in day["segments"] if s["kind"] == "work"]
        assert [s["minutes"] for s in rests] == [20, 15]
        assert [s["task"] for s in works] == ["开发", "开发"]
        text = app.render_export(con, 2026, "2026-09-08 12:15:00")
        assert "休息合计：35m" in text
        assert "休息 10:00–10:20" in text
        assert "休息 12:00–12:15" in text
        con.close()


def test_http_roundtrip() -> None:
    with TemporaryDirectory() as tmp:
        app.DB = Path(tmp) / "http.db"
        server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            home = urlopen(base + "/").read().decode("utf-8")
            assert "工作钟" in home
            assert "上班打卡" in home
            assert "还没走？" in home or "早上好" in home
            assert 'data-format="md"' in home
            assert 'data-format="xlsx"' in home
            assert 'id="dayChart"' in home
            assert 'id="calDays"' in home
            assert 'id="calToggle"' in home
            photo = urlopen(base + "/img/period-night.jpg")
            assert photo.headers.get_content_type() == "image/jpeg"
            assert photo.read()[:2] == b"\xff\xd8"
            req = Request(
                base + "/api/clock-in",
                data=b'{"date":"2026-09-08"}',
                headers={"Content-Type": "application/json"},
            )
            body = urlopen(req).read().decode("utf-8")
            assert "clock_in" in body
            md = urlopen(base + "/api/export?year=2026&format=md")
            assert md.headers.get_content_type() == "text/markdown"
            assert "工作记录" in md.read().decode("utf-8")
            xlsx = urlopen(base + "/api/export?year=2026&format=xlsx")
            assert "spreadsheetml" in (xlsx.headers.get_content_type() or "")
            assert xlsx.read()[:2] == b"PK"
            punched = json.loads(urlopen(base + "/api/punched?year=2026").read().decode())
            assert punched["dates"] == ["2026-09-08"]
            urlopen(Request(
                base + "/api/clock-out",
                data=b'{"date":"2026-09-08"}',
                headers={"Content-Type": "application/json"},
            ))
            punched = json.loads(urlopen(base + "/api/punched?year=2026").read().decode())
            assert punched["dates"] == ["2026-09-08"]
        finally:
            server.shutdown()


def test_page_url_and_launcher() -> None:
    old = app.HOST
    try:
        app.HOST = "0.0.0.0"
        assert app.page_url() == f"http://127.0.0.1:{app.PORT}/"
        app.HOST = "127.0.0.1"
        assert app.page_url() == f"http://127.0.0.1:{app.PORT}/"
    finally:
        app.HOST = old
    script = Path(__file__).resolve().parent / "start.command"
    raw = script.read_bytes()
    assert raw.startswith(b"#!/bin/sh\n")
    assert b"\r" not in raw
    assert b"app.py --open" in raw


if __name__ == "__main__":
    test_minutes_and_export()
    test_reset_and_calibrate()
    test_work_and_rest_modes()
    test_http_roundtrip()
    test_page_url_and_launcher()
    print("ok")
