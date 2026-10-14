"""Parser for the small YAML subset used by validator.yaml and .dv/config.yaml.

Supported: block mappings and lists by indentation (spaces only),
"- key: value" list items that start a mapping, inline lists [a, b],
inline mappings {k: v}, quoted strings, integers, true/false/null and
"#" comments. Anything else raises YamlError.
"""
from __future__ import annotations

import json
import re

_KEY_RE = re.compile(r"^([A-Za-z0-9_.\-]+):(?:\s+(.*))?$")
_INT_RE = re.compile(r"^-?\d+$")


class YamlError(ValueError):
    pass


def loads(text):
    lines = []
    for no, raw in enumerate(text.splitlines(), 1):
        body = _strip_comment(raw).rstrip()
        if not body.strip():
            continue
        indent = len(body) - len(body.lstrip(" "))
        if body[indent:indent + 1] == "\t":
            raise YamlError(f"line {no}: tabs are not allowed for indentation")
        lines.append([no, indent, body.strip()])
    if not lines:
        return {}
    value, pos = _parse_block(lines, 0, lines[0][1])
    if pos != len(lines):
        raise YamlError(f"line {lines[pos][0]}: unexpected content")
    return value


def load_file(path):
    with open(path, encoding="utf-8") as f:
        return loads(f.read())


def _is_item(text):
    return text == "-" or text.startswith("- ")


def _parse_block(lines, pos, indent):
    if _is_item(lines[pos][2]):
        return _parse_list(lines, pos, indent)
    return _parse_map(lines, pos, indent)


def _parse_map(lines, pos, indent):
    result = {}
    while pos < len(lines):
        no, ind, text = lines[pos]
        if ind < indent:
            break
        if ind > indent:
            raise YamlError(f"line {no}: unexpected indentation")
        if _is_item(text):
            raise YamlError(f"line {no}: list item where a mapping key was expected")
        m = _KEY_RE.match(text)
        if not m:
            raise YamlError(f"line {no}: expected 'key: value'")
        key, rest = m.group(1), (m.group(2) or "").strip()
        if key in result:
            raise YamlError(f"line {no}: duplicate key '{key}'")
        pos += 1
        if rest:
            result[key] = _value(no, rest)
        elif pos < len(lines) and lines[pos][1] > indent:
            result[key], pos = _parse_block(lines, pos, lines[pos][1])
        elif pos < len(lines) and lines[pos][1] == indent and _is_item(lines[pos][2]):
            result[key], pos = _parse_list(lines, pos, indent)
        else:
            result[key] = None
    return result, pos


def _parse_list(lines, pos, indent):
    result = []
    while pos < len(lines):
        no, ind, text = lines[pos]
        if ind < indent or (ind == indent and not _is_item(text)):
            break
        if ind > indent:
            raise YamlError(f"line {no}: unexpected indentation")
        rest = text[1:].strip()
        if not rest:
            pos += 1
            if pos < len(lines) and lines[pos][1] > indent:
                item, pos = _parse_block(lines, pos, lines[pos][1])
            else:
                item = None
        elif _KEY_RE.match(rest):
            child = ind + (len(text) - len(rest))
            lines[pos] = [no, child, rest]
            item, pos = _parse_map(lines, pos, child)
        else:
            item = _value(no, rest)
            pos += 1
        result.append(item)
    return result, pos


def _value(no, text):
    if text.startswith("["):
        if not text.endswith("]"):
            raise YamlError(f"line {no}: unterminated inline list")
        inner = text[1:-1].strip()
        return [_value(no, part) for part in _split_top(no, inner)] if inner else []
    if text.startswith("{"):
        if not text.endswith("}"):
            raise YamlError(f"line {no}: unterminated inline mapping")
        inner = text[1:-1].strip()
        out = {}
        for part in _split_top(no, inner) if inner else []:
            m = _KEY_RE.match(part)
            if not m or m.group(2) is None:
                raise YamlError(f"line {no}: bad inline mapping entry '{part}'")
            out[m.group(1)] = _value(no, m.group(2).strip())
        return out
    return _scalar(no, text)


def _scalar(no, text):
    if text.startswith('"'):
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise YamlError(f"line {no}: bad double-quoted string") from e
    if text.startswith("'"):
        if len(text) < 2 or not text.endswith("'"):
            raise YamlError(f"line {no}: bad single-quoted string")
        return text[1:-1].replace("''", "'")
    if text in ("true", "false"):
        return text == "true"
    if text in ("null", "~"):
        return None
    if _INT_RE.match(text):
        return int(text)
    return text


def _split_top(no, text):
    parts, depth, quote, start = [], 0, None, 0
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:i].strip())
            start = i + 1
    if quote or depth:
        raise YamlError(f"line {no}: unbalanced brackets or quotes")
    parts.append(text[start:].strip())
    return parts


def _strip_comment(line):
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line
