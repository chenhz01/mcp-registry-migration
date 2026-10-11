#!/usr/bin/env python3
"""Three-tier self test for mcp-registry-migration (registry_compat.py).

All fixtures are invented generic MCP-style records; no upstream repo
content is copied.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import registry_compat as rc  # noqa: E402

CLI = [sys.executable, os.path.join(HERE, "registry_compat.py")]


def run_cli(*args):
    return subprocess.run(CLI + list(args), capture_output=True, text=True)


def rec(name, status="active", transport="stdio"):
    return {"name": name, "version": "1.0", "transport": transport,
            "status": status, "description": "sample %s" % name}


def registry(*records):
    return {"servers": list(records)}


class TestFunctional(unittest.TestCase):
    def test_record_validation(self):
        errors, warnings = rc.validate_record(rec("github"))
        self.assertEqual((errors, warnings), ([], []))
        errors, _ = rc.validate_record({"name": "x", "transport": "carrier-pigeon",
                                        "status": "active"})
        self.assertTrue(any("transport" in e for e in errors))

    def test_query_filters(self):
        reg = registry(rec("github"), rec("gitlab"), rec("old-git", status="archived"))
        names = [r["name"] for r in rc.query_registry(reg, name_substr="git")]
        self.assertEqual(names, ["github", "gitlab", "old-git"])
        self.assertEqual([r["name"] for r in rc.query_registry(reg, status="archived")],
                         ["old-git"])
        self.assertEqual([r["name"] for r in rc.query_registry(reg, name_substr="git",
                                                               status="active")],
                         ["github", "gitlab"])

    def test_manifest_mapping(self):
        manifest = {"servers": [{"name": "slack", "description": "chat",
                                 "source_url": "https://example/slack"}]}
        records, warnings = rc.manifest_to_records(manifest)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "active")
        self.assertEqual(records[0]["transport"], "stdio")
        self.assertEqual(warnings, [])

    def test_diff_reports_all_classes(self):
        manifest = {"servers": [{"name": "a"}, {"name": "b"}, {"name": "d"}]}
        reg = registry(rec("a"), rec("b", status="archived"), rec("c"))
        d = rc.diff_manifest_registry(manifest, reg)
        self.assertEqual(d["only_in_manifest"], ["d"])
        self.assertEqual(d["only_in_registry"], ["c"])
        self.assertEqual(d["status_changed"], [{"name": "b", "registry_status": "archived"}])


class TestErrorPaths(unittest.TestCase):
    def test_unknown_filter_values(self):
        reg = registry(rec("a"))
        with self.assertRaises(rc.InputError):
            rc.query_registry(reg, transport="smoke-signal")
        with self.assertRaises(rc.InputError):
            rc.query_registry(reg, status="zombie")

    def test_bad_record_shapes(self):
        for bad in ({"transport": "stdio", "status": "active"},  # no name
                    {"name": "x", "transport": "stdio", "status": "maybe",
                     "package": "not-an-object"}):
            errors, _ = rc.validate_record(bad)
            self.assertTrue(errors)

    def test_cli_missing_file_exits_2(self):
        res = run_cli("query", "--registry", "Z:/no/there.json")
        self.assertEqual(res.returncode, 2)
        self.assertIn("error:", res.stderr)

    def test_registry_without_servers_list(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write('{"oops": true}')
        self.addCleanup(os.remove, path)
        res = run_cli("query", "--registry", path)
        self.assertEqual(res.returncode, 2)


class TestEdgeCases(unittest.TestCase):
    def _file(self, content):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        self.addCleanup(os.remove, path)
        return path

    def test_empty_registry(self):
        path = self._file('{"servers": []}')
        res = run_cli("query", "--registry", path)
        self.assertEqual(res.returncode, 0)
        self.assertIn('"count": 0', res.stdout)

    def test_corrupt_registry(self):
        path = self._file("{not json")
        res = run_cli("query", "--registry", path)
        self.assertEqual(res.returncode, 2)
        self.assertIn("not valid JSON", res.stderr)

    def test_empty_and_unnamed_manifest_entries(self):
        path = self._file('{"servers": [{}, {"name": ""}, {"name": "ok"}]}')
        res = run_cli("manifest-map", "--manifest", path)
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.count("WARN"), 3)

    def test_overlong_description(self):
        r = rec("big")
        r["description"] = "D" * 300_000
        errors, _ = rc.validate_record(r)
        self.assertEqual(errors, [])

    def test_duplicate_names_flagged(self):
        path = self._file(json.dumps(registry(rec("a"), rec("a"))))
        res = run_cli("validate", "--registry", path)
        self.assertEqual(res.returncode, 1)
        self.assertIn("duplicate names", res.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
