#!/usr/bin/env python3
"""Unit tests for the read-only RK3588 edge status backend."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "rk3588_edge_status_server.py"
SPEC = importlib.util.spec_from_file_location("rk3588_edge_status_server", MODULE_PATH)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = server
SPEC.loader.exec_module(server)


class EdgeStatusServerTest(unittest.TestCase):
    def test_container_name_is_whitelisted(self) -> None:
        self.assertEqual(server.validate_container("rk3588_dev-1.0"), "rk3588_dev-1.0")

        with self.assertRaises(argparse.ArgumentTypeError):
            server.validate_container("rk3588_dev;rm -rf /")

    def test_parse_topic_info_counts_publishers_and_subscribers(self) -> None:
        text = """
Type: sensor_msgs/Image

Publishers:
 * /hikrobot_camera (http://elf2:12345/)

Subscribers:
 * /recorder (http://elf2:12346/)
 * /viewer (http://elf2:12347/)
"""
        publishers, subscribers = server.parse_topic_info(text)
        self.assertEqual(publishers, 1)
        self.assertEqual(subscribers, 2)

    def test_request_path_ignores_query_string(self) -> None:
        self.assertEqual(server.normalize_request_path("/api/status?rev=20260708"), "/api/status")
        self.assertEqual(server.normalize_request_path("/status?cacheBust=1"), "/status")


if __name__ == "__main__":
    unittest.main()
