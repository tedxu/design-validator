#!/usr/bin/env python3
"""Deterministic checks for design-validator runs.

Exit codes: 0 ok; 1 input files have fixable errors; 2 cannot proceed.
stdout is always one JSON object.
"""
import argparse
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dvlib import commands, registry, runinit, yamlish  # noqa: E402


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _parser():
    p = _Parser(prog="verify.py", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=_Parser)
    init = sub.add_parser("init")
    init.add_argument("design")
    init.add_argument("--depth", default="standard", choices=sorted(registry.DEPTH_COSTS))
    init.add_argument("--repo", default=".")
    init.add_argument("--baseline", default=None)
    for name in ("assumptions", "audit", "report"):
        sub.add_parser(name).add_argument("run_dir")
    results = sub.add_parser("results")
    results.add_argument("run_dir")
    results.add_argument("--stage", type=int, required=True)
    inp = sub.add_parser("input")
    inp.add_argument("run_dir")
    inp.add_argument("--validator", required=True)
    return p


def main(argv=None):
    try:
        args = _parser().parse_args(argv)
        if args.cmd == "init":
            code, out = commands.cmd_init(args.design, args.repo, args.depth, baseline=args.baseline)
        elif args.cmd == "assumptions":
            code, out = commands.cmd_assumptions(args.run_dir)
        elif args.cmd == "results":
            code, out = commands.cmd_results(args.run_dir, args.stage)
        elif args.cmd == "input":
            code, out = commands.cmd_input(args.run_dir, args.validator)
        elif args.cmd == "audit":
            code, out = commands.cmd_audit(args.run_dir)
        else:
            code, out = commands.cmd_report(args.run_dir)
    except ValueError as e:
        if not isinstance(e, (registry.RegistryError, yamlish.YamlError)):
            code, out = 2, {"ok": False, "errors": [f"usage: {e}"]}
        else:
            code, out = 2, {"ok": False, "errors": [str(e)]}
    except (commands.StateError, runinit.InitError) as e:
        code, out = 2, {"ok": False, "errors": [str(e)]}
    except Exception as e:  # noqa: BLE001 - report every failure as JSON
        traceback.print_exc(file=sys.stderr)
        code, out = 2, {"ok": False, "errors": [f"internal error: {e!r}"]}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
