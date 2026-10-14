import unittest

import _path  # noqa: F401
from dvlib import yamlish


class LoadsTest(unittest.TestCase):
    def test_valid(self):
        cases = [
            ("empty", "", {}),
            ("comment only", "# hi\n", {}),
            ("scalars",
             "a: 1\nb: true\nc: null\nd: hello world\ne: \"q: #x\"\nf: 'it''s'\n",
             {"a": 1, "b": True, "c": None, "d": "hello world", "e": "q: #x", "f": "it's"}),
            ("inline list", "t: [T1, T2]\nempty: []\n", {"t": ["T1", "T2"], "empty": []}),
            ("inline map", "o: {stage: 3, cost: low}\n", {"o": {"stage": 3, "cost": "low"}}),
            ("nested map", "a:\n  b:\n    c: 1\n  d: 2\n", {"a": {"b": {"c": 1}, "d": 2}}),
            ("block list same indent", "l:\n- x\n- y\nz: 1\n", {"l": ["x", "y"], "z": 1}),
            ("list of maps",
             "docs:\n  - path: a\n    authority: authoritative\n  - path: b\n",
             {"docs": [{"path": "a", "authority": "authoritative"}, {"path": "b"}]}),
            ("trailing comment", "a: 1 # one\n", {"a": 1}),
            ("url value", "u: http://x/y\n", {"u": "http://x/y"}),
            ("empty value", "a:\nb: 2\n", {"a": None, "b": 2}),
        ]
        for name, text, want in cases:
            with self.subTest(name):
                self.assertEqual(yamlish.loads(text), want)

    def test_invalid(self):
        cases = [
            ("tab indent", "a:\n\tb: 1\n"),
            ("duplicate key", "a: 1\na: 2\n"),
            ("bad indent", "a: 1\n  b: 2\n"),
            ("no colon", "just text\n"),
            ("unterminated list", "a: [1, 2\n"),
            ("bad inline map", "a: {b}\n"),
            ("list item in mapping", "a: 1\n- x\n"),
        ]
        for name, text in cases:
            with self.subTest(name):
                with self.assertRaises(yamlish.YamlError):
                    yamlish.loads(text)


if __name__ == "__main__":
    unittest.main()
