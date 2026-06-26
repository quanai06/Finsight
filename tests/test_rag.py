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


def _hit(text, *, parent_id="", parent_text="", score=0.0, vector=None, note_no=None):
    return Hit(
        text=text, doc_id="d", doc_name="n", page=1, heading="", score=score,
        parent_id=parent_id, parent_text=parent_text, note_no=note_no, vector=vector or [],
    )


# ----------------------------------------------------- two-period year columns -
_RELATED_PARTY_DOC = """<!-- ===== page 9 ===== -->
## 37. Nghiệp vụ với các bên liên quan
Đơn vị tính: triệu VND

| Bên liên quan | Nội dung nghiệp vụ | Năm nay | Năm trước |
| --- | --- | --- | --- |
| Quỹ Thiện Tâm | Phải thu từ cung cấp dịch vụ | 162.253 | 324.079 |
| Công ty SV | Chuyển nhượng bất động sản | - | 6.377.153 |
"""

_BALANCE_DOC = """<!-- ===== page 10 ===== -->
## 37.2 Chi tiết các khoản phải thu và phải trả

| Bên liên quan | Nội dung | Số cuối năm | Số đầu năm |
| --- | --- | --- | --- |
| Công ty SV | Phải thu chuyển nhượng | 505.325 | 3.601.722 |
"""


def test_flow_table_pins_year_columns_and_tags_value_kind():
    chunks = chunk_markdown(_RELATED_PARTY_DOC, doc_id="d", doc_name="r.pdf", year=2022)
    t = next(c for c in chunks if c.value_kind)
    assert t.value_kind == "flow"
    # "Năm nay/Năm trước" become absolute years so the LLM can't confuse 2021 for 2022
    assert "Năm nay (2022)" in t.text
    assert "Năm trước (2021)" in t.text
    # a guidance note tells the reader to take only the asked year's column
    assert "2021" in t.text and "chỉ lấy" in t.text.lower()


def test_balance_table_tagged_as_balance_not_flow():
    chunks = chunk_markdown(_BALANCE_DOC, doc_id="d", doc_name="r.pdf", year=2022)
    t = next(c for c in chunks if c.value_kind)
    assert t.value_kind == "balance"
    assert "Số cuối năm (2022)" in t.text and "Số đầu năm (2021)" in t.text


def test_year_columns_untouched_when_year_unknown():
    chunks = chunk_markdown(_RELATED_PARTY_DOC, doc_id="d", doc_name="r.pdf")
    t = next(c for c in chunks if "Năm nay" in c.text)
    assert "Năm nay (" not in t.text  # no absolute year to pin to
    assert t.value_kind == "flow"     # kind is still detected for routing


def test_expand_note_assembles_whole_note_when_fragments_cluster():
    from src.rag.pipeline import RAGPipeline, _MAX_PARENT_CHARS

    p = RAGPipeline.__new__(RAGPipeline)
    full = "WHOLE-NOTE " * ((_MAX_PARENT_CHARS // 11) + 10)  # exceeds the parent cap

    class _VS:
        def fetch_note(self, session_id, doc_id, note_no):
            return full

    p.vectorstore = _VS()
    hits = [
        _hit("frag1", score=0.9, note_no=37),
        _hit("frag2", score=0.8, note_no=37),
        _hit("unrelated prose", score=0.5),
    ]
    out = p._expand_note("s", hits)
    assert out[0].text == full and out[0].note_no == 37  # whole note first
    assert len(out) == 2                                  # two frags -> one note
    assert any(h.text == "unrelated prose" for h in out)  # other hits preserved


def test_expand_note_noop_when_note_already_small():
    from src.rag.pipeline import RAGPipeline

    p = RAGPipeline.__new__(RAGPipeline)

    class _VS:
        def fetch_note(self, *a):
            return "short note that fits"

    p.vectorstore = _VS()
    hits = [_hit("frag", score=0.9, note_no=12), _hit("prose", score=0.4)]
    assert p._expand_note("s", hits) == hits  # nothing gained -> unchanged


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


# --------------------------------------------------------------- api embedder -
def _make_api_embedder(responses):
    """Build an ApiEmbedder without sparse, with its HTTP client stubbed to pop
    canned responses so dense embedding is tested without network/ONNX."""
    from src.rag.embeddings import ApiEmbedder

    emb = ApiEmbedder.__new__(ApiEmbedder)
    emb.model_name = "test/model"
    emb.batch_size = 2
    emb.concurrency = 1  # deterministic order for the canned-response stub
    emb.max_retries = 3
    emb.backoff = 0  # no real sleeping in tests
    emb._url = "http://stub"
    emb._headers = {}
    emb._sparse = None
    calls = {"n": 0}

    class _Resp:
        def __init__(self, status, payload):
            self.status_code = status
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    class _Client:
        def post(self, url, headers=None, json=None):
            r = responses[calls["n"]]
            calls["n"] += 1
            n = len(json["inputs"])
            return _Resp(r["status"], r.get("vectors", [[0.0, 0.0]] * n))

    emb._client = _Client()
    return emb, calls


def test_api_embedder_batches_and_aligns_passage_vectors():
    # 3 texts, batch_size=2 -> two POSTs; vectors come back in input order.
    emb, calls = _make_api_embedder(
        [
            {"status": 200, "vectors": [[1.0, 0.0], [0.0, 1.0]]},
            {"status": 200, "vectors": [[0.5, 0.5]]},
        ]
    )
    out = emb.embed_passages(["a", "b", "c"])
    assert out == [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]
    assert calls["n"] == 2  # batched into two requests


def test_api_embedder_concurrent_batches_preserve_order():
    # batch_size=2, concurrency=3 over 5 texts -> 3 batches run concurrently but
    # vectors must come back aligned with the input order. Stub derives each
    # vector from its input so out-of-order execution can't hide a misalignment.
    from src.rag.embeddings import ApiEmbedder

    emb = ApiEmbedder.__new__(ApiEmbedder)
    emb.batch_size = 2
    emb.concurrency = 3
    emb.max_retries = 1
    emb.backoff = 0
    emb._url = "http://stub"
    emb._headers = {}
    emb._sparse = None

    class _Resp:
        status_code = 200

        def __init__(self, inputs):
            self._inputs = inputs

        def json(self):
            return [[float(ord(t[0]))] for t in self._inputs]

    class _Client:
        def post(self, url, headers=None, json=None):
            return _Resp(json["inputs"])

    emb._client = _Client()
    out = emb.embed_passages(["a", "b", "c", "d", "e"])
    assert out == [[97.0], [98.0], [99.0], [100.0], [101.0]]


def test_api_embedder_retries_transient_then_succeeds():
    from src.rag.embeddings import EmbeddingError

    emb, calls = _make_api_embedder(
        [
            {"status": 503},  # cold start -> retry
            {"status": 429},  # rate limit -> retry
            {"status": 200, "vectors": [[1.0, 2.0]]},
        ]
    )
    assert emb.embed_query("q") == [1.0, 2.0]
    assert calls["n"] == 3
    # a non-retryable 4xx (bad token) raises immediately
    emb2, _ = _make_api_embedder([{"status": 401}])
    try:
        emb2.embed_query("q")
        assert False, "expected EmbeddingError on 401"
    except EmbeddingError:
        pass


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
