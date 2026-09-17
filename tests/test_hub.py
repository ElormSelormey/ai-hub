#!/usr/bin/env python3
"""Automated Unit & Integration Tests for YO AI (ai-hub)"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import hub


class TestHubUtils(unittest.TestCase):
    def test_visible_len(self):
        text = hub.paint("Hello", hub.CYAN, bold=True)
        self.assertEqual(hub.visible_len(text), 5)
        self.assertEqual(hub.visible_len("Plain text"), 10)

    def test_pad(self):
        padded_left = hub.pad("abc", 10, "left")
        self.assertEqual(padded_left, "abc       ")
        padded_right = hub.pad("abc", 10, "right")
        self.assertEqual(padded_right, "       abc")
        padded_center = hub.pad("abc", 9, "center")
        self.assertEqual(padded_center, "   abc   ")

    def test_clip(self):
        self.assertEqual(hub.clip("short", 10), "short")
        self.assertEqual(hub.clip("this is too long", 8), "this is…")

    def test_short_version(self):
        self.assertEqual(hub.short_version(""), "—")
        self.assertEqual(hub.short_version("1.2.34 (abcd) [stable]"), "1.2.34")
        self.assertEqual(hub.short_version("v0.5.0"), "0.5.0")

    def test_valid_project_name(self):
        self.assertTrue(hub.valid_project_name("my-project"))
        self.assertTrue(hub.valid_project_name("proj_1.0"))
        self.assertFalse(hub.valid_project_name("../bad_path"))
        self.assertFalse(hub.valid_project_name("$invalid"))


class TestHubConfigAndCommands(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.orig_hub_home = hub.HUB_HOME
        self.orig_config_path = hub.CONFIG_PATH
        self.orig_hub_log = hub.HUB_LOG
        self.orig_cache_path = hub.CACHE_PATH

        hub.HUB_HOME = self.temp_path
        hub.CONFIG_PATH = self.temp_path / "config.json"
        hub.HUB_LOG = self.temp_path / "logs" / "hub.jsonl"
        hub.CACHE_PATH = self.temp_path / "logs" / "which-cache.json"
        (self.temp_path / "logs").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        hub.HUB_HOME = self.orig_hub_home
        hub.CONFIG_PATH = self.orig_config_path
        hub.HUB_LOG = self.orig_hub_log
        hub.CACHE_PATH = self.orig_cache_path
        shutil.rmtree(self.temp_dir)

    def test_load_and_save_config(self):
        cfg = hub.load_config()
        self.assertIn("tools", cfg)
        self.assertEqual(len(cfg["tools"]), 6)

        cfg["brand"] = "Custom AI"
        hub.save_config(cfg)
        loaded = hub.load_config()
        self.assertEqual(loaded["brand"], "Custom AI")

    @patch("hub.probe_version", return_value="1.0.0")
    def test_cmd_add_and_rm(self, mock_probe):
        cfg = hub.load_config()
        tools = hub.discover(cfg)

        # Add a custom tool
        ret = hub.cmd_add(["testtool", "--name", "Test Tool", "--vendor", "Acme"], tools)
        self.assertEqual(ret, 0)

        cfg = hub.load_config()
        tool_ids = [t["id"] for t in cfg["tools"]]
        self.assertIn("testtool", tool_ids)

        # Update tools list
        tools = hub.discover(cfg)
        self.assertTrue((hub.HUB_HOME / "testtool" / "projects").is_dir())

        # Remove the custom tool
        ret_rm = hub.cmd_rm(["testtool"], tools)
        self.assertEqual(ret_rm, 0)

        cfg = hub.load_config()
        tool_ids = [t["id"] for t in cfg["tools"]]
        self.assertNotIn("testtool", tool_ids)

    @patch("hub.probe_version", return_value="1.0.0")
    def test_cmd_new(self, mock_probe):
        cfg = hub.load_config()
        tools = hub.discover(cfg)
        tool = tools[0]  # grok

        ret = hub.cmd_new([tool.id, "my_new_app", "--no-launch"], tools)
        self.assertEqual(ret, 0)
        self.assertTrue((tool.projects_dir / "my_new_app").is_dir())

    @patch("hub.probe_version", return_value="1.0.0")
    def test_render_menu_no_type_error(self, mock_probe):
        cfg = hub.load_config()
        tools = hub.discover(cfg)
        # Verify render_menu executes cleanly without TypeError
        menu_output = hub.render_menu(tools, 0, 80, 24)
        self.assertIn("YO AI", menu_output)
        self.assertIn("Grok Build", menu_output)

    @patch("hub.probe_version", return_value="1.0.0")
    def test_render_workspace(self, mock_probe):
        cfg = hub.load_config()
        tools = hub.discover(cfg)
        opts = hub.workspace_options(tools[0], Path.cwd())
        output = hub.render_workspace(tools[0], opts, 0, 80)
        self.assertIn("where should Grok Build work?", output)

    @patch("hub.probe_version", return_value="1.0.0")
    def test_launch_logging(self, mock_probe):
        cfg = hub.load_config()
        tools = hub.discover(cfg)
        tool = tools[0]
        tool.path = shutil.which("echo")
        ret = hub.launch(tool, ["hello"], self.temp_path)
        self.assertEqual(ret, 0)
        logs = hub.read_log_rows(tool.id)
        self.assertTrue(len(logs) > 0)
        self.assertIn("pid", logs[-1])
        self.assertTrue(logs[-1]["pid"] > 0)


if __name__ == "__main__":
    unittest.main()
