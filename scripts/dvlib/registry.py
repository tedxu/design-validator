"""Validator manifests, project config and depth selection."""
from __future__ import annotations

import hashlib
import os
import posixpath

from . import yamlish

PLUGIN_ROOT = os.environ.get("DV_PLUGIN_ROOT") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESERVED = "extract"
KINDS = ("agent", "command")
SCOPES = ("assumption", "design")
TIERS = ("T1", "T2", "T3")
SEVERITIES = ("MINOR", "MAJOR", "BLOCKER")
COSTS = ("low", "medium", "high")
BLOCKER_EVIDENCE = ("T1", "authoritative-docs", "ANY")
ASSUMPTION_KINDS = ("current-fact", "inference", "compatibility", "invariant", "performance",
                    "design-choice")
DEPTH_COSTS = {"quick": {"low"}, "standard": {"low", "medium"}, "deep": {"low", "medium", "high"}}
MANIFEST_FIELDS = ("name", "version", "kind", "stage", "scope", "targets", "truth_tiers",
                   "can_block", "max_severity", "blocker_evidence", "cost", "entry")
OVERRIDABLE = {"stage", "cost"}
CONFIG_KEYS = {"docs", "priors", "validators", "history", "eval"}


class RegistryError(ValueError):
    pass


def load_manifest(directory, origin):
    path = os.path.join(directory, "validator.yaml")
    try:
        data = yamlish.load_file(path)
    except (OSError, yamlish.YamlError) as e:
        raise RegistryError(f"{path}: {e}") from e
    if not isinstance(data, dict):
        raise RegistryError(f"{path}: expected a mapping")
    unknown = set(data) - set(MANIFEST_FIELDS)
    if unknown:
        raise RegistryError(f"{path}: unknown fields {sorted(unknown)}")
    m = {key: data.get(key) for key in MANIFEST_FIELDS}
    m["version"] = data.get("version", 1)
    m["targets"] = data.get("targets") or []
    m["can_block"] = data.get("can_block", False)
    m["blocker_evidence"] = data.get("blocker_evidence") or ["T1"]
    if m["max_severity"] is None:
        m["max_severity"] = "BLOCKER" if m["can_block"] is True else "MAJOR"
    m["origin"] = origin
    m["dir"] = os.path.abspath(directory)
    _check_manifest(path, m)
    return m


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _check_manifest(where, m):
    def fail(msg):
        raise RegistryError(f"{where}: {msg}")

    if not isinstance(m["name"], str) or not m["name"]:
        fail("name is required")
    if m["name"] != os.path.basename(m["dir"]):
        fail(f"name '{m['name']}' must match its directory name")
    if not _is_int(m["version"]):
        fail("version must be an integer")
    if m["kind"] not in KINDS:
        fail(f"kind must be one of {list(KINDS)}")
    if not _is_int(m["stage"]) or m["stage"] < 0:
        fail("stage must be a non-negative integer")
    if (m["stage"] == 0) != (m["name"] == RESERVED):
        fail("stage 0 is reserved for 'extract', and 'extract' must be stage 0")
    if m["scope"] not in SCOPES:
        fail(f"scope must be one of {list(SCOPES)}")
    if not isinstance(m["targets"], list) or any(t not in ASSUMPTION_KINDS for t in m["targets"]):
        fail(f"targets must list assumption kinds {list(ASSUMPTION_KINDS)}")
    if m["scope"] == "assumption" and not m["targets"]:
        fail("scope 'assumption' requires targets")
    if (not isinstance(m["truth_tiers"], list) or not m["truth_tiers"]
            or any(t not in TIERS for t in m["truth_tiers"])):
        fail("truth_tiers must be a non-empty list of T1/T2/T3")
    if not isinstance(m["can_block"], bool):
        fail("can_block must be true or false")
    if m["max_severity"] not in SEVERITIES:
        fail(f"max_severity must be one of {list(SEVERITIES)}")
    if m["max_severity"] == "BLOCKER" and not m["can_block"]:
        fail("max_severity BLOCKER requires can_block: true")
    if (not isinstance(m["blocker_evidence"], list) or not m["blocker_evidence"]
            or any(b not in BLOCKER_EVIDENCE for b in m["blocker_evidence"])):
        fail(f"blocker_evidence must list values from {list(BLOCKER_EVIDENCE)}")
    if m["cost"] not in COSTS:
        fail(f"cost must be one of {list(COSTS)}")
    if not isinstance(m["entry"], str) or not os.path.isfile(os.path.join(m["dir"], m["entry"])):
        fail(f"entry '{m['entry']}' not found")


def _scan(root, origin):
    found = {}
    if not os.path.isdir(root):
        return found
    for name in sorted(os.listdir(root)):
        directory = os.path.join(root, name)
        if os.path.isfile(os.path.join(directory, "validator.yaml")):
            found[name] = load_manifest(directory, origin)
    return found


def _repo_relative(p, fail):
    if not isinstance(p, str) or not p:
        fail("paths must be non-empty strings")
    norm = posixpath.normpath(p.replace("\\", "/"))
    if p.startswith("/") or os.path.isabs(p) or norm == ".." or norm.startswith("../"):
        fail(f"path must stay inside the repository: {p}")
    return norm


def load_config(repo_root):
    path = os.path.join(repo_root, ".dv", "config.yaml")
    data = {}
    if os.path.isfile(path):
        try:
            data = yamlish.load_file(path) or {}
        except yamlish.YamlError as e:
            raise RegistryError(f"{path}: {e}") from e

    def fail(msg):
        raise RegistryError(f"{path}: {msg}")

    if not isinstance(data, dict):
        fail("expected a mapping")
    unknown = set(data) - CONFIG_KEYS
    if unknown:
        fail(f"unknown keys {sorted(unknown)}")

    docs = []
    for d in data.get("docs") or []:
        if not isinstance(d, dict) or "path" not in d or set(d) - {"path", "authority"}:
            fail("docs entries need 'path' and an optional 'authority'")
        authority = d.get("authority", "informative")
        if authority not in ("authoritative", "informative"):
            fail(f"authority must be authoritative or informative, got {authority!r}")
        docs.append({"path": _repo_relative(d["path"], fail), "authority": authority})

    priors = [_repo_relative(p, fail) for p in data.get("priors") or []]

    validators = data.get("validators") or {}
    if not isinstance(validators, dict) or set(validators) - {"disable", "override"}:
        fail("validators accepts only 'disable' and 'override'")
    disable = validators.get("disable") or []
    override = validators.get("override") or {}
    if not isinstance(disable, list) or not all(isinstance(x, str) for x in disable):
        fail("validators.disable must be a list of names")
    if not isinstance(override, dict) or not all(isinstance(v, dict) for v in override.values()):
        fail("validators.override must map names to field mappings")

    history = data.get("history") or {}
    if not isinstance(history, dict) or set(history) - {"pr_comments"}:
        fail("history accepts only 'pr_comments'")
    pr_comments = history.get("pr_comments", False)
    if not isinstance(pr_comments, bool):
        fail("history.pr_comments must be true or false")

    ev = data.get("eval") or {}
    if not isinstance(ev, dict) or set(ev) - {"design_globs"}:
        fail("eval accepts only 'design_globs'")
    globs = ev.get("design_globs") or []
    if not isinstance(globs, list) or not all(isinstance(g, str) for g in globs):
        fail("eval.design_globs must be a list of strings")

    return {"docs": docs, "priors": priors, "disable": disable, "override": override,
            "pr_comments": pr_comments, "design_globs": globs}


def load_registry(repo_root, config, plugin_root=PLUGIN_ROOT):
    reg = _scan(os.path.join(plugin_root, "validators"), "builtin")
    reg.update(_scan(os.path.join(repo_root, ".dv", "validators"), "project"))
    if RESERVED not in reg:
        raise RegistryError("the built-in 'extract' validator is missing")
    for name in config["disable"]:
        if name == RESERVED:
            raise RegistryError("'extract' cannot be disabled")
        if name not in reg:
            raise RegistryError(f"cannot disable unknown validator '{name}'")
        del reg[name]
    for name, fields in config["override"].items():
        if name not in reg:
            raise RegistryError(f"cannot override unknown validator '{name}'")
        if name == RESERVED:
            raise RegistryError("'extract' cannot be overridden")
        bad = set(fields) - OVERRIDABLE
        if bad:
            raise RegistryError(f"override of '{name}' may only set {sorted(OVERRIDABLE)}, got {sorted(bad)}")
        reg[name] = {**reg[name], **fields}
        _check_manifest(f"override of '{name}'", reg[name])
    return reg


def select(reg, depth):
    if depth not in DEPTH_COSTS:
        raise RegistryError(f"depth must be one of {sorted(DEPTH_COSTS)}")
    allowed = DEPTH_COSTS[depth]
    selected, skipped = [], {}
    for name, m in sorted(reg.items(), key=lambda kv: (kv[1]["stage"], kv[0])):
        if name == RESERVED or m["cost"] in allowed:
            selected.append(name)
        else:
            skipped[name] = f"depth={depth} excludes cost={m['cost']}"
    return selected, skipped


def entry_sha256(m):
    with open(os.path.join(m["dir"], m["entry"]), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()
