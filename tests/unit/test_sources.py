import os
import tempfile
import unittest

import _path  # noqa: F401
import helpers as h
from dvlib import sources

TEXT = "line one\n  line   two\nline three\nline four\nline five\n"


class MatchExcerptTest(unittest.TestCase):
    def test_cases(self):
        cases = [
            ("exact", TEXT, 2, 2, "line two", 0, None),
            ("whitespace-insensitive", TEXT, 1, 2, "line one line two", 0, None),
            ("crlf text", TEXT.replace("\n", "\r\n"), 3, 3, "line three", 0, None),
            ("outside range", TEXT, 1, 1, "line three", 0, "excerpt not found in lines 1-1"),
            ("slack reaches", TEXT, 1, 1, "line three", 3, None),
            ("slack clamps to end", TEXT, 5, 5, "line two", 3, None),
            ("past end", TEXT, 9, 9, "x", 0, "line 9 is past the end (5 lines)"),
            ("inverted range", TEXT, 3, 2, "x", 0, "invalid line range 3-2"),
            ("empty excerpt", TEXT, 1, 1, "  ", 0, "empty excerpt"),
        ]
        for name, text, start, end, excerpt, slack, want in cases:
            with self.subTest(name):
                self.assertEqual(sources.match_excerpt(text, start, end, excerpt, slack=slack), want)


class MarkdownSectionTest(unittest.TestCase):
    DOC = "# Pack\n\nintro\n\n## Alpha\n\na text\n\n### Alpha detail\n\nmore\n\n## Beta\n\nb text\n"

    def test_cases(self):
        cases = [
            ("includes subsection", "Alpha", ["a text", "more"], ["b text"]),
            ("last section", "Beta", ["b text"], ["a text"]),
            ("whitespace in heading", "  Alpha   detail ", ["more"], ["b text"]),
        ]
        for name, heading, present, absent in cases:
            with self.subTest(name):
                section = sources.markdown_section(self.DOC, heading)
                for p in present:
                    self.assertIn(p, section)
                for a in absent:
                    self.assertNotIn(a, section)
        self.assertIsNone(sources.markdown_section(self.DOC, "Gamma"))


class SourceReaderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo, self.commit = h.make_repo(self.tmp.name, {"a.py": "committed\n"})
        h.write_files(self.repo, {"a.py": "modified in worktree\n", "new.py": "untracked\n"})

    def tearDown(self):
        self.tmp.cleanup()

    def test_read(self):
        reader = sources.SourceReader(self.repo, self.commit, worktree_paths={"new.py"})
        cases = [
            ("committed file uses baseline", "a.py", ("committed\n", "commit")),
            ("untracked file read from disk", "new.py", ("untracked\n", "worktree")),
            ("dot path normalized", "./a.py", ("committed\n", "commit")),
        ]
        for name, path, want in cases:
            with self.subTest(name):
                self.assertEqual(reader.read(path), want)
        snapshot = sources.SourceReader(self.repo, None)
        self.assertEqual(snapshot.read("a.py"), ("modified in worktree\n", "worktree"))

    def test_rejects(self):
        reader = sources.SourceReader(self.repo, self.commit)
        for name, path in [("parent escape", "../x"), ("absolute", "/etc/hosts"),
                           ("missing", "nope.py"), ("nested escape", "a/../../x")]:
            with self.subTest(name):
                with self.assertRaises(sources.SourceError):
                    reader.read(path)


if __name__ == "__main__":
    unittest.main()
