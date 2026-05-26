from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.kb_index import (
    BM25Search,
    build_index,
    chunk_text,
    tokenize,
)
from runtime.knowledge_base import KnowledgeBaseStore


class TokenizeTests(unittest.TestCase):
    def test_ascii_tokens_lowercased_and_filtered(self):
        tokens = tokenize("Authentication module uses JWT and OAuth2.")
        self.assertIn("authentication", tokens)
        self.assertIn("jwt", tokens)
        self.assertIn("oauth2", tokens)
        # Stopwords stripped
        self.assertNotIn("and", tokens)

    def test_cjk_bigrams_and_drops_stop_chars(self):
        tokens = tokenize("用户认证模块使用 JWT 进行验证")
        # bigrams of "用户认证模块使用"
        self.assertIn("用户", tokens)
        self.assertIn("认证", tokens)
        self.assertIn("模块", tokens)
        self.assertIn("jwt", tokens)
        # single-char Chinese stopwords are not bigrams of useful content
        self.assertNotIn("的", tokens)
        self.assertNotIn("了", tokens)

    def test_empty_safe(self):
        self.assertEqual(tokenize(""), [])
        self.assertEqual(tokenize("   "), [])


class ChunkTextTests(unittest.TestCase):
    def test_short_content_returns_single_chunk(self):
        chunks = chunk_text("hello world")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["text"], "hello world")

    def test_splits_on_paragraph_breaks(self):
        # Each paragraph is small individually; combined exceeds target.
        paragraphs = ["para " + ("x" * 200)] * 5
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, target=400, overlap=20)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk["text"]), 500)  # tolerate paragraph length
            self.assertGreater(len(chunk["text"]), 0)

    def test_long_paragraph_hard_split_with_overlap(self):
        text = "a" * 2500
        chunks = chunk_text(text, target=800, overlap=50)
        self.assertGreaterEqual(len(chunks), 3)
        for chunk in chunks:
            self.assertLessEqual(len(chunk["text"]), 800)


class BM25SearchTests(unittest.TestCase):
    def _build(self, chunks):
        records = [{"path": "doc.md", "start": 0, "end": len(c), "text": c} for c in chunks]
        return BM25Search(build_index(records))

    def test_returns_top_k_ranked_chunks(self):
        index = self._build([
            "Authentication module uses JWT tokens for login.",
            "The frontend renders the main dashboard.",
            "Cookie-based login is supported by the legacy subsystem.",
            "Random text about something unrelated.",
        ])
        # "login" appears in 2 chunks; "jwt" only in chunk 0. The chunk
        # that matches both terms should outrank the chunk that matches
        # only "login".
        hits = index.query("jwt login", top_k=4)
        self.assertEqual(len(hits), 2)
        self.assertIn("Authentication module uses JWT", hits[0]["text"])
        self.assertGreater(hits[0]["score"], hits[1]["score"])

    def test_empty_query_returns_empty(self):
        index = self._build(["anything"])
        self.assertEqual(index.query(""), [])

    def test_no_match_returns_empty(self):
        index = self._build(["one two three"])
        self.assertEqual(index.query("xylophone tubular"), [])


class StoreBM25Integration(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = KnowledgeBaseStore(self.root)

    def test_add_files_writes_index_and_qa_context_uses_bm25(self):
        kb_id = self.store.create(name="codebase")["kb_id"]
        self.store.add_files(kb_id, {
            "src/auth.py": (
                b"def login_with_jwt(token):\n"
                b"    \"\"\"Authenticate the user via a JWT bearer token.\"\"\"\n"
                b"    return verify_jwt(token)\n"
            ),
            "src/render.py": (
                b"def render_dashboard():\n"
                b"    return template('dashboard.html')\n"
            ),
            "docs/intro.md": (
                b"# Project\n\nA toy project for testing.\n"
            ),
        })
        # The index file should now exist.
        self.assertTrue((self.root / ".knowledge_bases" / kb_id / "index.json").exists())
        meta = self.store.get(kb_id)
        self.assertGreater(meta["chunk_count"], 0)
        self.assertEqual(meta["retrieval"], "bm25")

        # Query for "jwt" should pick the auth chunk first.
        bundle = self.store.qa_context([kb_id], query="how is authentication via jwt done?")
        self.assertEqual(bundle["retrieval"], "bm25")
        self.assertTrue(bundle["sources"])
        top = bundle["sources"][0]
        self.assertEqual(top["path"], "src/auth.py")
        self.assertGreater(top["score"], 0)
        self.assertIn("jwt", " ".join(top["matched_terms"]))
        self.assertIn("login_with_jwt", bundle["context"])
        # Naive concat-mode KB (no query) still works.
        no_query = self.store.qa_context([kb_id], query="")
        self.assertEqual(no_query["retrieval"], "naive_concat")

    def test_qa_context_falls_back_when_no_index_exists(self):
        kb_id = self.store.create(name="legacy")["kb_id"]
        # Bypass add_files (which would build an index) to simulate a KB
        # written before BM25 shipped.
        kb_dir = self.root / ".knowledge_bases" / kb_id
        (kb_dir / "files").mkdir(exist_ok=True)
        (kb_dir / "files" / "note.md").write_text("hello there", encoding="utf-8")
        bundle = self.store.qa_context([kb_id], query="hello")
        self.assertEqual(bundle["retrieval"], "naive_concat")
        self.assertIn("hello there", bundle["context"])

    def test_reupload_refreshes_index(self):
        kb_id = self.store.create(name="growing")["kb_id"]
        self.store.add_files(kb_id, {"a.md": b"alpha alpha alpha"})
        first_chunks = self.store.get(kb_id)["chunk_count"]
        self.store.add_files(kb_id, {"b.md": b"beta beta beta beta beta"})
        second_chunks = self.store.get(kb_id)["chunk_count"]
        self.assertGreater(second_chunks, first_chunks)
        bundle = self.store.qa_context([kb_id], query="beta")
        self.assertEqual(bundle["retrieval"], "bm25")
        self.assertEqual(bundle["sources"][0]["path"], "b.md")


if __name__ == "__main__":
    unittest.main()
