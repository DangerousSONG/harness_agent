from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.knowledge_base import (
    KnowledgeBaseStore,
    MAX_FILE_BYTES,
    MAX_TOTAL_BYTES,
    MAX_QA_CONTEXT_BYTES,
)


class KnowledgeBaseStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = KnowledgeBaseStore(self.root)

    def _make_kb(self, name="demo"):
        meta = self.store.create(name=name)
        return meta["kb_id"]

    def test_create_lists_and_deletes(self):
        kb_id = self._make_kb()
        self.assertIn(kb_id, [item["kb_id"] for item in self.store.list()])
        detail = self.store.get(kb_id)
        self.assertEqual(detail["source_type"], "local")
        self.assertTrue(self.store.delete(kb_id))
        self.assertIsNone(self.store.get(kb_id))

    def test_create_rejects_blank_name(self):
        with self.assertRaises(ValueError):
            self.store.create(name="   ")

    def test_add_files_and_tree(self):
        kb_id = self._make_kb()
        self.store.add_files(kb_id, {
            "src/main.py": b"print('hi')\n",
            "docs/intro.md": b"# Intro\n\nHello.",
        })
        tree = sorted(item["path"] for item in self.store.tree(kb_id))
        self.assertEqual(tree, ["docs/intro.md", "src/main.py"])
        payload = self.store.read(kb_id, "docs/intro.md")
        self.assertEqual(payload["kind"], "text")
        self.assertIn("# Intro", payload["content"])

    def test_read_classifies_code_vs_text(self):
        kb_id = self._make_kb()
        self.store.add_files(kb_id, {
            "main.py": b"print(1)\n",
            "readme.md": b"# X\n",
        })
        self.assertEqual(self.store.read(kb_id, "main.py")["kind"], "code")
        self.assertEqual(self.store.read(kb_id, "readme.md")["kind"], "text")

    def test_read_marks_binary_without_returning_bytes(self):
        kb_id = self._make_kb()
        self.store.add_files(kb_id, {"image.bin": b"\x00\x01\x02\x03ABC"})
        payload = self.store.read(kb_id, "image.bin")
        self.assertEqual(payload["kind"], "binary")
        self.assertEqual(payload["content"], "")

    def test_path_traversal_is_blocked(self):
        kb_id = self._make_kb()
        outside = self.root / "secret.txt"
        outside.write_text("hidden", encoding="utf-8")
        # Should not write outside the KB files dir
        self.store.add_files(kb_id, {"../../secret.txt": b"leak"})
        self.assertEqual(self.store.tree(kb_id), [])
        # And reading via traversal must raise
        with self.assertRaises(FileNotFoundError):
            self.store.read(kb_id, "../../secret.txt")
        with self.assertRaises(FileNotFoundError):
            self.store.read(kb_id, "/etc/passwd")
        # outside file must still exist (we didn't overwrite it)
        self.assertEqual(outside.read_text(), "hidden")

    def test_oversized_file_is_dropped(self):
        kb_id = self._make_kb()
        oversized = b"x" * (MAX_FILE_BYTES + 1)
        self.store.add_files(kb_id, {"big.txt": oversized, "ok.txt": b"hi"})
        paths = [item["path"] for item in self.store.tree(kb_id)]
        self.assertEqual(paths, ["ok.txt"])
        self.assertTrue(self.store.get(kb_id)["truncated"])

    def test_skip_dirs_are_filtered(self):
        kb_id = self._make_kb()
        self.store.add_files(kb_id, {
            "node_modules/foo/index.js": b"x",
            "src/main.py": b"y",
        })
        paths = [item["path"] for item in self.store.tree(kb_id)]
        self.assertEqual(paths, ["src/main.py"])

    def test_qa_context_caps_total_bytes(self):
        kb_id = self._make_kb()
        # 60 KB worth of code; budget is 30 KB
        chunk = ("def f(): pass\n" * 800).encode("utf-8")
        self.store.add_files(kb_id, {
            "a.py": chunk,
            "b.py": chunk,
            "c.py": chunk,
        })
        result = self.store.qa_context([kb_id], byte_budget=MAX_QA_CONTEXT_BYTES)
        self.assertLessEqual(result["used_bytes"], MAX_QA_CONTEXT_BYTES + 200)
        self.assertGreater(len(result["sources"]), 0)
        # Sources must reference real KB paths
        for source in result["sources"]:
            self.assertEqual(source["kb_id"], kb_id)
            self.assertIn(source["path"], {"a.py", "b.py", "c.py"})

    def test_qa_context_drops_invalid_kb_ids(self):
        kb_id = self._make_kb()
        self.store.add_files(kb_id, {"x.md": b"hello"})
        result = self.store.qa_context([kb_id, "KB-DOESNOTEXIST", "../etc/passwd"])
        self.assertTrue(any("hello" in chunk for chunk in result["context"].splitlines() if chunk))
        self.assertEqual(len(result["sources"]), 1)

    def test_qa_context_hard_caps_at_3_kbs(self):
        kb_ids = [self._make_kb(f"kb-{idx}") for idx in range(5)]
        for kb_id in kb_ids:
            self.store.add_files(kb_id, {"note.md": b"# hi"})
        result = self.store.qa_context(kb_ids)
        kbs_used = {source["kb_id"] for source in result["sources"]}
        self.assertEqual(len(kbs_used), 3)

    def test_github_import_validates_url(self):
        kb_id = self._make_kb()
        meta = self.store.import_github(kb_id, "https://example.com/foo/bar")
        self.assertTrue(meta["import_error"])
        self.assertIn("github.com", meta["import_error"])

    def test_github_import_extracts_tarball(self):
        # Build a tiny tarball that mimics github's `<repo>-main/...` layout.
        import io, tarfile

        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for relative, content in [
                ("repo-main/README.md", b"# Repo\n"),
                ("repo-main/src/lib.py", b"def f(): pass\n"),
                ("repo-main/node_modules/skip/x.js", b"skip me"),
            ]:
                payload = content
                info = tarfile.TarInfo(name=relative)
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
        tarball_bytes = buffer.getvalue()

        kb_id = self._make_kb()
        with patch.object(self.store, "_fetch_tarball", return_value=tarball_bytes):
            meta = self.store.import_github(kb_id, "https://github.com/owner/repo")
        self.assertFalse(meta.get("import_error"))
        self.assertEqual(meta["source_type"], "github")
        self.assertEqual(meta["source_url"], "https://github.com/owner/repo")
        paths = sorted(item["path"] for item in self.store.tree(kb_id))
        self.assertEqual(paths, ["README.md", "src/lib.py"])


if __name__ == "__main__":
    unittest.main()
