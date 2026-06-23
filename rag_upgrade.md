# Finsight — Nhật ký nâng cấp RAG

> Ghi lại toàn bộ thay đổi trong đợt nâng cấp RAG (2026-06-22): từ **dense-only +
> reranker** sang **hybrid + hierarchical chunking theo cấu trúc BCTC**, CPU-only,
> **không dùng reranker** (rerank bị xem là quá nặng trên CPU).
Perceptual---

## 0. Tóm tắt 1 dòng

Dense (e5-large) **+ BM25 sparse → RRF** thay cho dense-only; **MMR + gộp parent**
thay cho reranker; **chunker hiểu cấu trúc BCTC** (CĐKT/KQKD/LCTT/Thuyết minh) +
**định tuyến câu hỏi** tới đúng nhánh báo cáo. Tất cả ONNX/CPU, không PyTorch, không GPU.

---

## 1. Dọn dẹp hạ tầng

- **Chuyển `docker-compose.yml` ra root** (xoá thư mục `docker/`). Lệnh giờ gọn:
  `docker compose up -d`. Đã cập nhật mọi tham chiếu trong `README.md`,
  `log_structure.md`, `.env`, `.env.example`.

Mục tiêu: trị gốc rễ "hỏi số liệu mà không ra" và "chunking mù không hiểu cấu trúc
báo cáo tài chính". Nguồn vấn đề lấy từ `error_upgrade.md` (mục B, RAG1–RAG15).


---

## 2. Giai đoạn 1 — Hybrid Retrieval (thay dense-only, bỏ reranker)

### 2.1. Cái gì & vì sao
Dense-only kém với token số ("5.538.327"), mã chỉ tiêu, năm → **RAG1** là nguyên
nhân #1. Research (Qdrant hybrid, Anthropic Contextual Retrieval, Snowflake
finance-RAG) xác nhận **hybrid + MMR** lấy lại phần lớn lợi ích của reranker mà
rẻ hơn nhiều trên CPU.

> Ghi chú: **bge-m3 KHÔNG có trong FastEmbed** (chỉ FlagEmbedding/PyTorch) nên
> không hợp nguyên tắc ONNX/CPU-không-PyTorch của project. Chốt dùng **e5-large
> (dense) + Qdrant/bm25 (sparse)**.

### 2.2. Stack
| Lớp | Trước | Sau |
| --- | --- | --- |
| Dense | e5-large / mpnet (lệch) | **e5-large 1024** (thống nhất code ↔ .env) |
| Sparse | — | **BM25** (`Qdrant/bm25`, ONNX, ~0 RAM, IDF do Qdrant tính) |
| Fusion | — | **RRF** (`prefetch` + `FusionQuery` trong Qdrant) |
| Hậu xử lý | reranker (đang tắt) | **Gộp parent + MMR** + ngưỡng score (tuỳ chọn) |

### 2.3. File đụng tới
- `src/rag/embeddings.py` — thêm BM25 sparse (`embed_sparse_passages_iter`,
  `embed_sparse_query`), trả `SparseVec`; FastEmbed lazy-load.
- `src/rag/vectorstore.py` — collection **named vectors** `dense` + `bm25`
  (sparse có `Modifier.IDF`); `search()` chạy hybrid RRF, trả dense vector cho MMR;
  tự tạo lại collection khi schema đổi.
- `src/rag/pipeline.py` — bỏ phụ thuộc reranker mặc định; thêm **MMR** (đa dạng
  hoá, trị văn bản lặp), **gộp bảng** (small-to-big), ngưỡng score chống bịa;
  prompt ép **đơn vị + kỳ/năm**; sửa bug `page 0`, bỏ heading lặp.
- `src/serving/config.py` / `deps.py` / `routes/documents.py` — cấu hình hybrid/MMR;
  reranker **mặc định TẮT**; doc-context prefix (tên + năm).

### 2.4. Lỗi audit đã trị
RAG1 (hybrid), RAG5 (candidates 50 / top_k 8), RAG7/8 (heading/page),
RAG9 (prompt đơn vị/kỳ), RAG12 (chunk 1800 ký tự), RAG14 (MMR/dedup/threshold).

---

## 3. Giai đoạn 2 — Hierarchical Financial Chunker (Core A–D)

### 3.1. Vấn đề
Chunking cũ đọc được Markdown (trang/heading/bảng) nhưng **không hiểu cấu trúc
báo cáo tài chính** — không biết đâu là Bảng cân đối, đâu là Thuyết minh số 12,
không gắn chunk vào cây báo cáo. Research (arXiv 2402.05131 *Financial Report
Chunking*: Page Accuracy 68%→84%; arXiv 2510.24402 metadata-driven filtering/routing)
xác nhận chunk theo phần tử cấu trúc + metadata routing cho gain lớn.

### 3.2. Cái gì đã làm
**A. Nhận diện section** — `src/rag/financial_sections.py` (heuristic VN, **không LLM**):
- `detect_statement_type` → `cdkt` (Bảng cân đối) · `kqkd` (Kết quả KD) ·
  `lctt` (Lưu chuyển tiền tệ) · `thuyet_minh` (Thuyết minh) · `kiem_toan` · `bgd`.
- `detect_note_no` → bắt số thuyết minh ("12.", "V.5", "Note 8").
- `route_query` → đoán câu hỏi hỏi về báo cáo/thuyết minh/năm nào; **ambiguous thì
  không route** (tránh route sai).

**B. Cây phân cấp** — `src/rag/chunking.py`:
- Mỗi chunk có `section_id` + `parent_section_id` (ancestor được đăng ký kể cả khi
  heading cha không có nội dung trực tiếp).
- Gắn `statement_type` + `note_no` + `year`, **kế thừa xuống** theo nhánh heading.

**C. Section-parent cho prose (small-to-big)** — mục thuyết minh nhỏ (≤4000 ký tự):
trúng 1 tiểu mục → đưa **cả mục** cho LLM. Mục lớn thì không gộp (tránh nuốt mất
phần liên quan). Tổng quát hoá cơ chế parent vốn chỉ dùng cho bảng.

**D. Routing + filtering** — `vectorstore.py` + `pipeline.py`:
- Payload + index `statement_type` / `note_no` / `year`; `search()` nhận filter.
- Pipeline **soft-filter** theo route, **fallback bậc thang**: lọc statement+note+year
  → rỗng thì bỏ `year` → vẫn rỗng thì bỏ hết. **Không bao giờ chặn cứng.**
- Toggle `FINSIGHT_USE_ROUTING` (mặc định `true`).

> **E (note cross-ref: line-item ↔ thuyết minh) — CHƯA làm**, để dành giai đoạn sau.

### 3.3. Lỗi audit đã trị thêm
RAG4 (lọc năm/tài liệu), RAG6 (đơn vị bảng), RAG11 (parent-child / small-to-big).

---

## 4. Cấu hình mới (`.env`)

```
# Embedding (dense)
FINSIGHT_EMBED_MODEL=intfloat/multilingual-e5-large
FINSIGHT_EMBED_DIM=1024
# Hybrid (dense + BM25, RRF)
FINSIGHT_USE_HYBRID=true
FINSIGHT_SPARSE_MODEL=Qdrant/bm25
# Rerank TẮT (MMR thay thế)
FINSIGHT_USE_RERANKER=false
# Retrieval
FINSIGHT_RETRIEVE_CANDIDATES=50
FINSIGHT_TOP_K=8
FINSIGHT_MMR_LAMBDA=0.6          # 1=liên quan, 0=đa dạng
FINSIGHT_SCORE_THRESHOLD=0.0     # >0 = grounding nghiêm ngặt (có thể bỏ sót khớp BM25)
FINSIGHT_USE_ROUTING=true        # định tuyến theo statement/note/year (soft + fallback)
# Chunking
FINSIGHT_CHUNK_SIZE=1800
FINSIGHT_CHUNK_OVERLAP=250
```

---

## 5. Kiểm chứng

- **Unit test:** `tests/test_rag.py` — 9 test (chunking parent-child, đơn vị, MMR,
  gộp parent, nhận diện section, note_no, routing ambiguous/note/year, section-parent).
  Toàn bộ **21/21 test pass** (12 OCR cũ + 9 RAG mới).
- **End-to-end với Qdrant thật:**
  | Câu hỏi | Route | Kết quả |
  | --- | --- | --- |
  | "doanh thu thuần năm 2023" | `kqkd` | đúng bảng KQKD, BM25 bắt đúng số |
  | "tổng tài sản" | `cdkt` | đúng bảng CĐKT |
  | "mã chỉ tiêu TS-401" | (BM25) | RRF score 1.0 — khớp mã chính xác |
  | "thuyết minh 12 hàng tồn kho" | `thuyet_minh`+`note_no=12` | đúng mục, đã mở rộng cả mục |

---

## 6. Lưu ý vận hành

- **Phải nhúng lại tài liệu** (re-upload): schema vector + payload đổi nên collection
  `finsight_chunks` cũ tự bị xoá & tạo lại ở lần khởi động đầu (đã ghi cảnh báo log).
  Chưa có script re-embed từ Postgres → cách nhanh nhất là upload lại file.
- **Heuristic tiếng Việt cần tinh chỉnh theo dữ liệu thật.** Báo cáo dùng tên mục lạ
  (vd "Báo cáo tình hình tài chính") → thêm pattern vào `financial_sections.py`.
  Routing đã soft + fallback nên sai cũng không vỡ.
- Toàn bộ thay đổi đang ở **working tree, chưa commit** (chờ review).

---

## 7. Bản đồ file thay đổi

```
docker-compose.yml              (mới ở root, xoá docker/)
.env, .env.example              cấu hình hybrid/MMR/routing/chunking
src/rag/
  financial_sections.py         (MỚI) nhận diện section BCTC + routing câu hỏi
  embeddings.py                 + BM25 sparse
  vectorstore.py                hybrid RRF + payload/filter hierarchy
  chunking.py                   cây mục BCTC + section-parent (small-to-big)
  pipeline.py                   routing + gộp parent + MMR + prompt đơn vị/kỳ
  __init__.py                   docstring mô tả hybrid
src/serving/
  config.py, deps.py            wiring cấu hình mới
  routes/documents.py           truyền year + doc-context vào chunker
tests/test_rag.py               (MỚI) 9 unit test cho RAG
log_structure.md                cập nhật kiến trúc theo stack mới
```

---

## 8. Hướng tiếp theo (chưa làm)

- **E. Note cross-ref** — line-item/bảng nhắc "Thuyết minh số X" → đính kèm chunk
  thuyết minh tương ứng lúc trả lời.
- **Contextual Retrieval** — Groq sinh 1–2 câu ngữ cảnh per-chunk lúc index
  (Anthropic: giảm ~49% lỗi truy hồi) — gain lớn nhất còn lại, vẫn không cần rerank.
- **Script re-embed** từ Markdown đã lưu trên đĩa (tránh phải re-upload tay).
