"""Unit tests for the hybrid-RAG pieces that need no running infrastructure:
structure-aware chunking (parent-child tables, unit capture, doc context) and the
post-retrieval logic that replaces the reranker (parent collapse + MMR)."""

from __future__ import annotations

from src.rag.chunking import chunk_markdown
from src.rag.financial_sections import detect_note_no, detect_statement_type, route_query
from src.rag.pipeline import _collapse_parents, _mmr
from src.rag.vectorstore import Hit

_TABLE_DOC = """<!-- ===== page 7 ===== -->
## Báo cáo kết quả kinh doanh
Đơn vị tính: triệu đồng

| Chỉ tiêu | Năm 2023 | Năm 2022 |
| --- | --- | --- |
| Doanh thu thuần | 5.538.327 | 4.120.000 |
| Lợi nhuận sau thuế | 1.200.000 | 980.000 |
"""


def test_table_chunks_are_parented_and_carry_unit_and_page():
    chunks = chunk_markdown(
        _TABLE_DOC, doc_id="d1", doc_name="VIC.pdf", doc_context="Tài liệu: VIC.pdf · Năm: 2023"
    )
    tables = [c for c in chunks if ":t" in c.parent_id]
    assert tables, "table rows should become parented chunks"
    t = tables[0]
    # small-to-big: the child carries the whole table as parent_text
    assert "Doanh thu thuần" in t.parent_text and "Lợi nhuận sau thuế" in t.parent_text
    # unit of measure travels with the table (so figures keep their 1000x scale)
    assert "triệu đồng" in t.text
    # doc context prefix + page metadata are present for citations
    assert "VIC.pdf" in t.text
    assert t.page == 7
    # the unit must not be duplicated by the caption/unit capture
    assert t.text.count("Đơn vị tính") == 1


def test_doc_context_prefix_on_prose():
    md = "<!-- ===== page 1 ===== -->\n# Thuyết minh\n\n" + ("Doanh thu tăng. " * 200)
    chunks = chunk_markdown(md, doc_id="d2", doc_name="r.pdf", doc_context="Tài liệu: r.pdf")
    assert chunks
    assert all("Tài liệu: r.pdf" in c.text for c in chunks)
    # the large paragraph is split into multiple windowed chunks
    assert len(chunks) > 1


def _hit(text, *, parent_id="", parent_text="", score=0.0, vector=None):
    return Hit(
        text=text, doc_id="d", doc_name="n", page=1, heading="", score=score,
        parent_id=parent_id, parent_text=parent_text, vector=vector or [],
    )


def test_collapse_parents_merges_table_rowgroups_into_one_full_table():
    hits = [
        _hit("rowgroup A", parent_id="d:t1", parent_text="FULL TABLE", score=0.9),
        _hit("rowgroup B", parent_id="d:t1", parent_text="FULL TABLE", score=0.8),
        _hit("prose", score=0.5),
    ]
    out = _collapse_parents(hits)
    assert len(out) == 2  # two row-groups collapse to one
    table = next(h for h in out if h.parent_id == "d:t1")
    assert table.text == "FULL TABLE"  # expanded to the whole table


def test_mmr_drops_near_duplicates_in_favour_of_diversity():
    # two near-identical vectors + one distinct; MMR(k=2) should pick one of the
    # duplicates plus the distinct one rather than both duplicates.
    dup1 = _hit("dup1", score=1.0, vector=[1.0, 0.0])
    dup2 = _hit("dup2", score=0.99, vector=[0.99, 0.01])
    diff = _hit("diff", score=0.6, vector=[0.0, 1.0])
    picked = _mmr([dup1, dup2, diff], k=2, lam=0.5)
    texts = {h.text for h in picked}
    assert "diff" in texts
    assert not {"dup1", "dup2"} <= texts  # not both duplicates


def test_mmr_returns_all_when_k_exceeds_candidates():
    hits = [_hit("a", score=1.0, vector=[1, 0]), _hit("b", score=0.5, vector=[0, 1])]
    assert _mmr(hits, k=5, lam=0.6) == hits


# --------------------------------------------------------------- hierarchy ---
def test_detect_statement_type_vietnamese_headings():
    assert detect_statement_type("Bảng cân đối kế toán hợp nhất") == "cdkt"
    assert detect_statement_type("Báo cáo kết quả hoạt động kinh doanh") == "kqkd"
    assert detect_statement_type("Báo cáo lưu chuyển tiền tệ") == "lctt"
    assert detect_statement_type("Thuyết minh báo cáo tài chính") == "thuyet_minh"
    assert detect_statement_type("Mục lục") == ""


def test_detect_note_no():
    assert detect_note_no("12. Tiền và các khoản tương đương tiền") == 12
    assert detect_note_no("V.5 Hàng tồn kho") == 5
    assert detect_note_no("Tiền mặt") is None


def test_route_query_single_and_ambiguous_and_note():
    assert route_query("doanh thu thuần năm 2023 là bao nhiêu").statement_type == "kqkd"
    assert route_query("tổng tài sản cuối kỳ").statement_type == "cdkt"
    # mentions both an income-statement and a balance-sheet term -> ambiguous
    assert route_query("doanh thu và tổng tài sản").statement_type == ""
    r = route_query("xem thuyết minh 12 về tiền mặt")
    assert r.statement_type == "thuyet_minh" and r.note_no == 12
    assert route_query("lợi nhuận năm 2022").year == 2022


def test_chunk_markdown_tags_statement_type_and_section_parent():
    md = """# Thuyết minh báo cáo tài chính

## 5. Hàng tồn kho

Hàng tồn kho cuối kỳ bao gồm nguyên vật liệu và thành phẩm, được ghi nhận theo
giá thấp hơn giữa giá gốc và giá trị thuần có thể thực hiện được."""
    chunks = chunk_markdown(md, doc_id="d9", doc_name="r.pdf", year=2023)
    note = next(c for c in chunks if c.note_no is not None)
    assert note.statement_type == "thuyet_minh"   # inherited down the tree
    assert note.note_no == 5
    assert note.year == 2023
    assert note.section_id and note.parent_section_id   # has a place in the tree
    # the short note prose is expanded to its whole-section parent (small-to-big)
    assert note.parent_id == note.section_id
    assert "giá trị thuần" in note.parent_text


# --------------------------------------------------------------- cancellation -
def test_index_jobs_cancel_lifecycle():
    from src.serving.routes.documents import _IndexJobs
    jobs = _IndexJobs()
    assert jobs.cancel("d1") is False          # not running -> nothing to cancel
    jobs.start("d1")
    assert jobs.is_cancelled("d1") is False
    assert jobs.cancel("d1") is True            # running -> cancellable
    assert jobs.is_cancelled("d1") is True
    jobs.finish("d1")
    assert jobs.is_cancelled("d1") is False      # cleared after finish


class _FakeEmbedder:
    """Stand-in so vectorstore.add can be exercised without ONNX/Qdrant."""
    has_sparse = False

    def embed_passages_iter(self, texts):
        for _ in texts:
            yield [0.0, 0.0]


def test_vectorstore_add_stops_early_when_cancelled():
    from src.rag import vectorstore as vs_mod
    from src.rag.chunking import Chunk

    vs = vs_mod.VectorStore.__new__(vs_mod.VectorStore)  # skip __init__/Qdrant
    vs.embedder = _FakeEmbedder()
    vs.hybrid = False
    upserts = []
    vs.client = type("C", (), {"upsert": lambda self, col, points: upserts.append(len(points))})()
    vs.collection = "c"

    chunks = [Chunk(text=f"t{i}", doc_id="d", doc_name="n") for i in range(200)]
    # cancel immediately -> should index 0 and never upsert
    done = vs.add("s", chunks, should_cancel=lambda: True)
    assert done == 0
    assert upserts == []
