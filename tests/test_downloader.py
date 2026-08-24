import datetime
import pathlib
import smtplib
import subprocess
import sys
from typing import ClassVar

import pytest

import twitch_vod_downloader as downloader
from settings import Settings


def test_channel_list_normalizes_values() -> None:
    config = Settings(channels=" alpha, beta ,, ", _env_file=None)

    assert config.channel_list() == ["alpha", "beta"]


def test_parse_vod_id() -> None:
    assert downloader.parse_vod_id("twitch 12345") == "12345"
    assert downloader.parse_vod_id("12345") == "12345"


def test_read_archive_lines(tmp_path) -> None:
    archive = tmp_path / "archive.txt"
    archive.write_text("twitch 1\n\ntwitch 2\n", encoding="utf-8")

    assert downloader.read_archive_lines(archive) == {"twitch 1", "twitch 2"}
    assert downloader.read_archive_lines(tmp_path / "missing.txt") == set()


def test_find_vod_files_ignores_partial_files(tmp_path) -> None:
    (tmp_path / "2026-01-01_123_video.mp4").touch()
    (tmp_path / "2026-01-01_123_video.part").touch()

    assert downloader.find_vod_files(tmp_path, "123") == [
        (tmp_path / "2026-01-01_123_video.mp4").resolve()
    ]


def test_seconds_to_next_run(monkeypatch) -> None:
    class FixedDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 8, 14, 2, 30)

    monkeypatch.setattr(downloader.datetime, "datetime", FixedDateTime)

    assert downloader.seconds_to_next_run() == 1800


def test_seconds_to_next_run_rolls_over_to_next_day(monkeypatch) -> None:
    class FixedDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 8, 14, 4, 0)

    monkeypatch.setattr(downloader.datetime, "datetime", FixedDateTime)

    assert downloader.seconds_to_next_run() == 23 * 3600


def test_log_prints_timestamped_message(capsys) -> None:
    downloader.log("hello world")

    out = capsys.readouterr().out
    assert "hello world" in out
    assert out.startswith("[")


def test_get_channels_returns_configured_channels(monkeypatch) -> None:
    monkeypatch.setattr(downloader.settings, "channels", "alpha, beta")

    assert downloader.get_channels() == ["alpha", "beta"]


def test_get_channels_exits_when_unset(monkeypatch, capsys) -> None:
    monkeypatch.setattr(downloader.settings, "channels", "")

    with pytest.raises(SystemExit) as exc_info:
        downloader.get_channels()

    assert exc_info.value.code == 1
    assert "ERROR" in capsys.readouterr().out


def test_ensure_base_dir_creates_directory(tmp_path, monkeypatch) -> None:
    target = tmp_path / "nested" / "data"
    monkeypatch.setattr(downloader, "BASE_DIR", target)

    downloader.ensure_base_dir()

    assert target.is_dir()


def test_ensure_base_dir_exits_on_oserror(tmp_path, monkeypatch, capsys) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(downloader, "BASE_DIR", blocker / "data")

    with pytest.raises(SystemExit) as exc_info:
        downloader.ensure_base_dir()

    assert exc_info.value.code == 1
    assert "ERROR" in capsys.readouterr().out


def test_send_email_skips_when_not_configured(monkeypatch, capsys) -> None:
    monkeypatch.setattr(downloader.settings, "smtp_host", None)
    monkeypatch.setattr(downloader.settings, "smtp_username", None)
    monkeypatch.setattr(downloader.settings, "smtp_password", None)

    downloader.send_email("subject", "body")

    assert "skipping" in capsys.readouterr().out.lower()


class _FakeSMTP:
    instances: ClassVar[list["_FakeSMTP"]] = []

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.starttls_called = False
        self.login_args = None
        self.sendmail_args = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def starttls(self, context=None):
        self.starttls_called = True

    def login(self, username, password):
        self.login_args = (username, password)

    def sendmail(self, from_addr, to_addrs, msg):
        self.sendmail_args = (from_addr, to_addrs, msg)


def _configure_smtp(monkeypatch) -> None:
    monkeypatch.setattr(downloader.settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(downloader.settings, "smtp_port", 587)
    monkeypatch.setattr(downloader.settings, "smtp_username", "user")
    monkeypatch.setattr(downloader.settings, "smtp_password", "pass")
    monkeypatch.setattr(downloader.settings, "smtp_from", "user@example.com")
    monkeypatch.setattr(downloader.settings, "smtp_to", "dest@example.com")


def test_send_email_success(monkeypatch, capsys) -> None:
    _configure_smtp(monkeypatch)
    _FakeSMTP.instances = []
    monkeypatch.setattr(downloader.smtplib, "SMTP", _FakeSMTP)

    downloader.send_email("subject", "body")

    sent = _FakeSMTP.instances[0]
    assert sent.starttls_called
    assert sent.login_args == ("user", "pass")
    assert sent.sendmail_args[0] == "user@example.com"
    assert sent.sendmail_args[1] == ["dest@example.com"]
    assert "sent" in capsys.readouterr().out.lower()


def test_send_email_handles_smtp_exception(monkeypatch, capsys) -> None:
    _configure_smtp(monkeypatch)

    class RaisingSMTP(_FakeSMTP):
        def sendmail(self, from_addr, to_addrs, msg):
            raise smtplib.SMTPException("boom")

    monkeypatch.setattr(downloader.smtplib, "SMTP", RaisingSMTP)

    downloader.send_email("subject", "body")

    assert "ERROR" in capsys.readouterr().out


def test_send_email_handles_oserror(monkeypatch, capsys) -> None:
    _configure_smtp(monkeypatch)

    class BrokenSMTP:
        def __init__(self, host, port):
            raise OSError("connection refused")

    monkeypatch.setattr(downloader.smtplib, "SMTP", BrokenSMTP)

    downloader.send_email("subject", "body")

    assert "ERROR" in capsys.readouterr().out


def test_read_archive_lines_handles_oserror(tmp_path, capsys) -> None:
    archive_dir = tmp_path / "archive.txt"
    archive_dir.mkdir()

    assert downloader.read_archive_lines(archive_dir) == set()
    assert "WARNING" in capsys.readouterr().out


def test_read_archive_lines_handles_decode_error(tmp_path, capsys) -> None:
    archive = tmp_path / "archive.txt"
    archive.write_bytes(b"\xff\xfe bad bytes")

    assert downloader.read_archive_lines(archive) == set()
    assert "WARNING" in capsys.readouterr().out


def test_find_vod_files_missing_channel_dir(tmp_path) -> None:
    assert downloader.find_vod_files(tmp_path / "missing", "123") == []


def test_display_path_rewrites_configured_prefix(monkeypatch) -> None:
    monkeypatch.setattr(downloader, "VOD_REAL_PATH", "/mnt/real/")

    rendered = downloader.display_path(pathlib.Path("/data/chan/video.mp4"))

    assert rendered == "/mnt/real/chan/video.mp4"


def test_display_path_without_real_path_configured(monkeypatch) -> None:
    monkeypatch.setattr(downloader, "VOD_REAL_PATH", None)

    rendered = downloader.display_path(pathlib.Path("/data/chan/video.mp4"))

    assert rendered == "/data/chan/video.mp4"


def test_display_path_ignores_unrelated_prefix(monkeypatch) -> None:
    monkeypatch.setattr(downloader, "VOD_REAL_PATH", "/mnt/real")

    rendered = downloader.display_path(pathlib.Path("/other/chan/video.mp4"))

    assert rendered == "/other/chan/video.mp4"


def _make_fake_run(
    downloads: dict, returncodes: dict | None = None, errors: dict | None = None
):
    returncodes = returncodes or {}
    errors = errors or {}

    def fake_run(cmd, check=False):
        url = cmd[1]
        channel = url.split("twitch.tv/")[1].split("/")[0]

        if channel in errors:
            raise errors[channel]

        archive_path = pathlib.Path(cmd[cmd.index("--download-archive") + 1])
        for line, filename in downloads.get(channel, []):
            with archive_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            if filename:
                (archive_path.parent / filename).touch()

        return subprocess.CompletedProcess(cmd, returncodes.get(channel, 0))

    return fake_run


def test_run_once_downloads_new_vod_and_sends_email(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(downloader, "BASE_DIR", tmp_path)
    fake_run = _make_fake_run(
        {"chan1": [("twitch 111", "2026-01-01_111_video.mp4")], "chan2": []}
    )
    monkeypatch.setattr(downloader.subprocess, "run", fake_run)

    sent = []
    monkeypatch.setattr(
        downloader, "send_email", lambda subject, body: sent.append((subject, body))
    )

    result = downloader.run_once(["chan1", "chan2"])

    assert result == [("chan1", "111")]
    assert len(sent) == 1
    subject, body = sent[0]
    assert "New VODs" in subject
    assert "2026-01-01_111_video.mp4" in body


def test_run_once_no_new_vods_skips_email(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(downloader, "BASE_DIR", tmp_path)
    fake_run = _make_fake_run({}, returncodes={"chan1": 1})
    monkeypatch.setattr(downloader.subprocess, "run", fake_run)

    sent = []
    monkeypatch.setattr(
        downloader, "send_email", lambda subject, body: sent.append((subject, body))
    )

    result = downloader.run_once(["chan1"])

    assert result == []
    assert sent == []


def test_run_once_handles_subprocess_oserror(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(downloader, "BASE_DIR", tmp_path)
    fake_run = _make_fake_run({}, errors={"chan1": OSError("yt-dlp not found")})
    monkeypatch.setattr(downloader.subprocess, "run", fake_run)
    monkeypatch.setattr(downloader, "send_email", lambda subject, body: None)

    result = downloader.run_once(["chan1"])

    assert result == []
    assert "ERROR running yt-dlp" in capsys.readouterr().out


def test_run_once_warns_when_downloaded_file_missing(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(downloader, "BASE_DIR", tmp_path)
    fake_run = _make_fake_run({"chan1": [("twitch 222", None)]})
    monkeypatch.setattr(downloader.subprocess, "run", fake_run)

    sent = []
    monkeypatch.setattr(
        downloader, "send_email", lambda subject, body: sent.append((subject, body))
    )

    result = downloader.run_once(["chan1"])

    assert result == [("chan1", "222")]
    assert "Could not locate downloaded file" in capsys.readouterr().out
    assert "222" in sent[0][1]


def test_parse_args_defaults_to_daemon_mode() -> None:
    assert downloader.parse_args([]).once is False


def test_parse_args_once_flag() -> None:
    assert downloader.parse_args(["--once"]).once is True


def test_main_runs_initial_sync_then_scheduled_loop(monkeypatch) -> None:
    class StopLoop(Exception):
        pass

    run_once_calls = []
    sleep_calls = []

    monkeypatch.setattr(sys, "argv", ["twitch_vod_downloader"])
    monkeypatch.setattr(downloader, "get_channels", lambda: ["chan1"])
    monkeypatch.setattr(downloader, "ensure_base_dir", lambda: None)
    monkeypatch.setattr(
        downloader, "run_once", lambda channels: run_once_calls.append(channels)
    )
    monkeypatch.setattr(downloader, "seconds_to_next_run", lambda: 0)

    def fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise StopLoop()

    monkeypatch.setattr(downloader.time, "sleep", fake_sleep)

    with pytest.raises(StopLoop):
        downloader.main()

    assert run_once_calls == [["chan1"], ["chan1"]]
    assert sleep_calls == [0, 0]


def test_main_runs_once_and_exits_with_once_flag(monkeypatch) -> None:
    run_once_calls = []

    monkeypatch.setattr(sys, "argv", ["twitch_vod_downloader", "--once"])
    monkeypatch.setattr(downloader, "get_channels", lambda: ["chan1"])
    monkeypatch.setattr(downloader, "ensure_base_dir", lambda: None)
    monkeypatch.setattr(
        downloader, "run_once", lambda channels: run_once_calls.append(channels)
    )

    def fail_sleep(seconds):
        raise AssertionError("daemon loop should not run in --once mode")

    monkeypatch.setattr(downloader.time, "sleep", fail_sleep)

    downloader.main()

    assert run_once_calls == [["chan1"]]


def test_main_runs_once_and_exits_with_run_once_env_var(monkeypatch) -> None:
    run_once_calls = []

    monkeypatch.setattr(sys, "argv", ["twitch_vod_downloader"])
    monkeypatch.setenv("RUN_ONCE", "1")
    monkeypatch.setattr(downloader, "get_channels", lambda: ["chan1"])
    monkeypatch.setattr(downloader, "ensure_base_dir", lambda: None)
    monkeypatch.setattr(
        downloader, "run_once", lambda channels: run_once_calls.append(channels)
    )

    def fail_sleep(seconds):
        raise AssertionError("daemon loop should not run in RUN_ONCE mode")

    monkeypatch.setattr(downloader.time, "sleep", fail_sleep)

    downloader.main()

    assert run_once_calls == [["chan1"]]
