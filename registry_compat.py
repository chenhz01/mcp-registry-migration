#!/usr/bin/env python3
"""mcp-registry-migration — governance sample for ecosystem manifest-to-registry migrations.

When an ecosystem moves its catalog from a hand-edited README/JSON manifest
to a queryable registry, downstream tooling and contributors break. This repo
provides (1) a registry query-interface spec and (2) a manifest compatibility
layer: map legacy manifests into registry-shaped records and diff the two
worlds so nothing is silently dropped.
Pure standard library. No network. No secrets. Data currency: 2026-10-11.
"""
from __future__ import annotations

import argparse
import json
import sys

AS_OF = "2026-10-11"

TRANSPORTS = {"stdio", "streamable-http", "sse"}
STATUSES = {"active", "archived", "deprecated"}
MANIFEST_KNOWN_FIELDS = {"name", "description", "source_url"}
RECORD_FIELDS = {"name", "version", "transport", "status", "package",
                 "description", "provenance"}


class InputError(ValueError):
    """Invalid input; CLI maps this to exit code 2."""


def validate_record(rec):
    """Validate a registry record. Returns (errors, warnings)."""
    errors, warnings = [], []
    if not isinstance(rec, dict):
        return ["record is not a JSON object"], []
    name = rec.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("missing or empty field: name")
    if rec.get("transport") not in TRANSPORTS:
        errors.append("transport must be one of %s" % sorted(TRANSPORTS))
    if rec.get("status") not in STATUSES:
        errors.append("status must be one of %s" % sorted(STATUSES))
    pkg = rec.get("package")
    if pkg is not None and (not isinstance(pkg, dict)
                            or not isinstance(pkg.get("name"), str)
                            or not pkg.get("name").strip()):
        errors.append("package must be an object with a non-empty name")
    if not isinstance(rec.get("version"), str) or not rec.get("version").strip():
        warnings.append("version missing; defaulting semantics undefined")
    for key in rec:
        if key not in RECORD_FIELDS:
            warnings.append("unknown field: %s" % key)
    return errors, warnings


def load_registry(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise InputError("registry file is not valid JSON: %s" % exc)
    except OSError as exc:
        raise InputError("cannot read registry file: %s" % exc)
    if not isinstance(data, dict) or not isinstance(data.get("servers"), list):
        raise InputError("registry must be a JSON object with a 'servers' list")
    return data


def load_manifest(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise InputError("manifest file is not valid JSON: %s" % exc)
    except OSError as exc:
        raise InputError("cannot read manifest file: %s" % exc)
    if not isinstance(data, dict) or not isinstance(data.get("servers"), list):
        raise InputError("manifest must be a JSON object with a 'servers' list")
    return data


def query_registry(registry, name_substr=None, transport=None, status=None):
    """The canonical query interface (spec v0.1): filter by name substring,
    exact transport, exact status. Results sorted by name."""
    if transport is not None and transport not in TRANSPORTS:
        raise InputError("unknown transport filter: %r" % transport)
    if status is not None and status not in STATUSES:
        raise InputError("unknown status filter: %r" % status)
    out = []
    for rec in registry["servers"]:
        if not isinstance(rec, dict):
            continue
        name = rec.get("name", "")
        if name_substr and name_substr.lower() not in str(name).lower():
            continue
        if transport and rec.get("transport") != transport:
            continue
        if status and rec.get("status") != status:
            continue
        out.append(rec)
    return sorted(out, key=lambda r: str(r.get("name", "")))


def manifest_to_records(manifest):
    """Map a legacy manifest into registry-shaped records.

    Legacy entry: {"name", "description", "source_url", ...extra}.
    Mapping policy: status=active, transport=stdio (assumed, warned),
    provenance=manifest-migration. Extra fields become warnings, never errors.
    """
    records, warnings = [], []
    for entry in manifest["servers"]:
        if not isinstance(entry, dict):
            warnings.append("skipped non-object manifest entry: %r" % (entry,))
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            warnings.append("skipped entry without a name: %r" % (entry,))
            continue
        for key in entry:
            if key not in MANIFEST_KNOWN_FIELDS:
                warnings.append("entry %r: unmapped field %r dropped" % (name, key))
        if "source_url" not in entry:
            warnings.append("entry %r: no source_url; provenance is incomplete" % name)
        records.append({
            "name": name,
            "version": "0",
            "transport": "stdio",
            "status": "active",
            "description": entry.get("description", ""),
            "provenance": {"mapped_from": "manifest", "source_url": entry.get("source_url", ""),
                           "as_of": AS_OF},
        })
    return records, warnings


def diff_manifest_registry(manifest, registry):
    """Three-way comparison by server name."""
    m_names = {e.get("name") for e in manifest["servers"] if isinstance(e, dict)}
    r_recs = {r.get("name"): r for r in registry["servers"] if isinstance(r, dict)}
    only_manifest = sorted(m_names - set(r_recs) - {None})
    only_registry = sorted(set(r_recs) - m_names - {None})
    status_changed = sorted(
        {"name": n, "registry_status": r_recs[n].get("status")}
        for n in (m_names & set(r_recs))
        if r_recs[n].get("status") != "active"
    )
    return {"only_in_manifest": only_manifest,
            "only_in_registry": only_registry,
            "status_changed": status_changed}


def cmd_validate(ns):
    registry = load_registry(ns.registry)
    bad = 0
    for rec in registry["servers"]:
        errors, warnings = validate_record(rec)
        name = rec.get("name", "?") if isinstance(rec, dict) else "?"
        for e in errors:
            print("ERROR (%s): %s" % (name, e))
        for w in warnings:
            print("WARN  (%s): %s" % (name, w))
        bad += len(errors)
    names = [r.get("name") for r in registry["servers"] if isinstance(r, dict)]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        print("ERROR: duplicate names in registry: %s" % ", ".join(dupes))
        bad += len(dupes)
    print("registry validation finished: %d error(s)" % bad)
    return 1 if bad else 0


def cmd_query(ns):
    registry = load_registry(ns.registry)
    results = query_registry(registry, ns.name, ns.transport, ns.status)
    print(json.dumps({"query": {"name": ns.name, "transport": ns.transport,
                                "status": ns.status},
                      "count": len(results),
                      "results": results}, indent=2))
    return 0


def cmd_manifest_map(ns):
    manifest = load_manifest(ns.manifest)
    records, warnings = manifest_to_records(manifest)
    for w in warnings:
        print("WARN: %s" % w)
    print(json.dumps({"servers": records}, indent=2))
    print("mapped %d entr(y/ies), %d warning(s), as of %s"
          % (len(records), len(warnings), AS_OF))
    return 0


def cmd_diff(ns):
    manifest = load_manifest(ns.manifest)
    registry = load_registry(ns.registry)
    result = diff_manifest_registry(manifest, registry)
    print(json.dumps(result, indent=2))
    total = (len(result["only_in_manifest"]) + len(result["only_in_registry"])
             + len(result["status_changed"]))
    print("diff finished: %d divergence(s)" % total)
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="registry_compat", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="validate a registry file (spec v0.1)")
    v.add_argument("--registry", required=True)
    v.set_defaults(func=cmd_validate)

    q = sub.add_parser("query", help="query a registry file via the canonical interface")
    q.add_argument("--registry", required=True)
    q.add_argument("--name", default=None, help="case-insensitive name substring")
    q.add_argument("--transport", default=None)
    q.add_argument("--status", default=None)
    q.set_defaults(func=cmd_query)

    m = sub.add_parser("manifest-map", help="map a legacy manifest to registry records")
    m.add_argument("--manifest", required=True)
    m.set_defaults(func=cmd_manifest_map)

    d = sub.add_parser("diff", help="diff legacy manifest vs registry")
    d.add_argument("--manifest", required=True)
    d.add_argument("--registry", required=True)
    d.set_defaults(func=cmd_diff)
    return p


def main(argv=None):
    ns = build_parser().parse_args(argv)
    try:
        return ns.func(ns)
    except InputError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
