from __future__ import annotations

import argparse
import os
import sys
import unittest
from unittest import mock

CODE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "litetune-skill", "code"))
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)

import lt


class LiteTuneCliParsingTests(unittest.TestCase):
    def parse(self, argv: list[str]):
        parser = lt.build_parser()
        args = parser.parse_args(argv)
        lt.validate_args(args)
        return args

    def test_param_set_assignment_syntax(self) -> None:
        self.assertEqual(
            lt.parse_assignments("gain=123,enabled=true,label=abc"),
            {"gain": 123, "enabled": True, "label": "abc"},
        )
        self.assertEqual(lt.parse_assignments("name=left=right"), {"name": "left=right"})
        self.assertEqual(lt.parse_assignments("gain=123, enabled=true"), {"gain": 123, "enabled": True})
        for assignments in ("gain", "=1", "gain=123,", ",enabled=true", "gain=123,=true", "gain=123,enabled"):
            with self.subTest(assignments=assignments):
                with self.assertRaises(lt.ArgsError):
                    lt.parse_assignments(assignments)

    def test_param_set_rejects_legacy_name_value_syntax(self) -> None:
        parser = lt.build_parser()
        with self.assertRaises(lt.ArgsError):
            parser.parse_args(["param", "set", "gain", "123"])

    def test_param_set_parser_and_handler_payload_assignment_syntax(self) -> None:
        args = self.parse(["--runtime", "/tmp/litetune-test", "param", "set", "gain=123,enabled=true", "--command-timeout", "1.5"])
        self.assertEqual(args.command, "param")
        self.assertEqual(args.param_command, "set")
        self.assertEqual(args.assignments, "gain=123,enabled=true")
        with mock.patch.object(lt, "daemon_request", return_value={"ok": True}) as request:
            self.assertEqual(lt.cmd_param_set(args), {"ok": True})
        request.assert_called_once_with(
            args.runtime,
            "param.set",
            {"values": {"gain": 123, "enabled": True}, "timeout_s": 1.5},
            timeout=args.timeout,
        )

    def test_validate_rejects_invalid_common_numbers(self) -> None:
        with self.assertRaises(lt.ArgsError):
            self.parse(["--timeout", "0", "param", "list"])
        with self.assertRaises(lt.ArgsError):
            self.parse(["log", "--num", "-1"])
        with self.assertRaises(lt.ArgsError):
            self.parse(["daemon", "start", "--port", "COM1", "--wait", "0"])

    def test_cmd_does_not_accept_payload_hex(self) -> None:
        parser = lt.build_parser()
        with self.assertRaises(lt.ArgsError):
            parser.parse_args(["cmd", "reboot", "--payload-hex", "0102"])

    def test_cmd_run_does_not_send_payload_hex(self) -> None:
        args = self.parse(["--runtime", "/tmp/litetune-test", "cmd", "reboot", "--command-timeout", "1.5"])
        with mock.patch.object(lt, "daemon_request", return_value={"ok": True}) as request:
            self.assertEqual(lt.cmd_run(args), {"ok": True})
        request.assert_called_once_with(
            args.runtime,
            "cmd.run",
            {"name": "reboot", "timeout_s": 1.5},
            timeout=args.timeout,
        )

    def test_removed_cli_aliases_are_rejected(self) -> None:
        parser = lt.build_parser()
        cases = (
            ["start", "--port", "COM1"],
            ["stop"],
            ["status"],
            ["restart", "--port", "COM1"],
            ["schema-refresh"],
            ["log", "tail"],
            ["log", "follow"],
            ["log", "filter", "--type", "X"],
            ["log", "path"],
        )
        for argv in cases:
            with self.subTest(argv=argv):
                with self.assertRaises(lt.ArgsError):
                    parser.parse_args(argv)

    def test_json_flag_is_not_supported(self) -> None:
        parser = lt.build_parser()
        cases = (
            ["--json", "param", "list"],
            ["param", "list", "--json"],
            ["cmd", "reboot", "--json", "{}"],
        )
        for argv in cases:
            with self.subTest(argv=argv):
                with self.assertRaises(lt.ArgsError):
                    parser.parse_args(argv)

    def status_args(self, port: str | None = None, baud: int | None = None):
        kwargs = {"runtime": "/tmp/litetune-test", "timeout": 1.0}
        if port is not None:
            kwargs["port"] = port
        if baud is not None:
            kwargs["baud"] = baud
        return argparse.Namespace(**kwargs)

    def test_daemon_status_rejects_requested_port_baud_mismatch(self) -> None:
        args = self.status_args(port="COM2", baud=57600)
        fake_status = {"ok": True, "daemon_id": "d1", "port": "COM1", "baud": 115200}
        with mock.patch.object(lt, "daemon_meta", return_value={"daemon_id": "d1", "port": "COM1", "baud": 115200}), \
             mock.patch.object(lt, "socket_path", return_value="/tmp/litetune.sock"), \
             mock.patch.object(lt, "daemon_request", return_value=fake_status):
            with self.assertRaises(lt.DaemonConfigMismatchError) as ctx:
                lt.daemon_status_payload(args, require_connect=False)
        self.assertEqual(ctx.exception.details["mismatches"]["daemon"]["port"]["requested"], "COM2")

    def test_daemon_start_does_not_already_running_on_mismatch(self) -> None:
        args = self.parse(["daemon", "start", "--port", "COM2", "--baud", "57600"])
        fake_status = {"ok": True, "daemon_id": "d1", "port": "COM1", "baud": 115200}
        with mock.patch.object(lt, "daemon_meta", return_value={"daemon_id": "d1", "port": "COM1", "baud": 115200}), \
             mock.patch.object(lt, "socket_path", return_value="/tmp/litetune.sock"), \
             mock.patch.object(lt, "daemon_request", return_value=fake_status), \
             mock.patch.object(lt.subprocess, "Popen") as popen:
            with self.assertRaises(lt.DaemonConfigMismatchError):
                lt.cmd_daemon_start(args)
        popen.assert_not_called()

    def test_daemon_stop_checks_requested_port_baud_before_stop(self) -> None:
        args = self.parse(["daemon", "stop", "--port", "COM2", "--baud", "57600"])
        fake_status = {"ok": True, "daemon_id": "d1", "port": "COM1", "baud": 115200}
        with mock.patch.object(lt, "daemon_meta", return_value={"daemon_id": "d1", "port": "COM1", "baud": 115200}), \
             mock.patch.object(lt, "socket_path", return_value="/tmp/litetune.sock"), \
             mock.patch.object(lt, "daemon_request", return_value=fake_status) as request:
            with self.assertRaises(lt.DaemonConfigMismatchError):
                lt.cmd_daemon_stop(args)
        request.assert_called_once_with(args.runtime, "daemon.status", timeout=args.timeout)

    def test_daemon_stop_force_rejects_nonconnectable_metadata_mismatch_without_kill(self) -> None:
        args = self.parse(["daemon", "stop", "--force", "--port", "COM2", "--baud", "57600"])
        connect_error = lt.DaemonConnectError("daemon is not connectable", {"socket_path": "/tmp/litetune.sock"})
        with mock.patch.object(lt, "daemon_meta", return_value={"daemon_id": "d1", "port": "COM1", "baud": 115200, "pid": 12345}), \
             mock.patch.object(lt, "socket_path", return_value="/tmp/litetune.sock"), \
             mock.patch.object(lt, "daemon_request", side_effect=connect_error), \
             mock.patch.object(lt.os, "kill", return_value=None) as kill:
            with self.assertRaises(lt.DaemonConfigMismatchError):
                lt.cmd_daemon_stop(args)
        kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
