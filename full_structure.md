# QUY TRÌNH CHUẨN HỆ THỐNG FINSIGHT — TỪ OCR ĐẾN HỎI ĐÁP RAG

> Tài liệu quy trình tác nghiệp chuẩn (SOP) mô tả toàn bộ luồng xử lý của hệ thống
> Finsight: từ khâu số hóa tài liệu tài chính (OCR) đến khâu truy hồi và sinh câu
> trả lời bằng RAG, kèm lớp đồ thị tài chính (Graph-RAG) và quy trình đánh giá chất lượng.

---

## 1. Thông tin kiểm soát tài liệu

| Hạng mục | Nội dung |
|---|---|
| Mã tài liệu | FS-SOP-001 |
| Tên tài liệu | Quy trình chuẩn xử lý dữ liệu Finsight (OCR → RAG) |
| Phiên bản | 1.0 |
| Ngày hiệu lực | 22/06/2026 |
| Người soạn thảo | Nhóm Kỹ thuật Finsight |
| Người rà soát | Trưởng nhóm Dữ liệu / ML |
| Người phê duyệt | Quản lý Sản phẩm |
| Chu kỳ rà soát | 6 tháng/lần hoặc khi thay đổi kiến trúc |
| Trạng thái | Ban hành |

---

## 2. Mục đích

Tài liệu này thiết lập **quy trình chuẩn, thống nhất và có thể lặp lại** cho việc:

1. Số hóa báo cáo tài chính (Báo cáo tài chính hợp nhất — BCTC) dạng PDF scan/ảnh
   thành văn bản có cấu trúc.
2. Lập chỉ mục (index) tài liệu vào kho vector để phục vụ truy hồi.
3. Trả lời câu hỏi của người dùng dựa trên tài liệu đã tải lên (RAG), bao gồm cả
   câu hỏi **xuyên nhiều tài liệu / nhiều năm** thông qua lớp đồ thị tài chính.
4. Đo lường và kiểm soát chất lượng đầu ra bằng bộ chỉ số chuẩn (RAGAS + chỉ số tài chính).

Mục tiêu cốt lõi: **mọi con số trong câu trả lời phải đúng tuyệt đối và truy vết
được về tài liệu nguồn**; hệ thống phải **từ chối trả lời** khi tài liệu không chứa
thông tin, thay vì bịa đặt.

---

## 3. Phạm vi áp dụng

- **Áp dụng cho:** toàn bộ luồng dữ liệu của Finsight — module OCR (`src/ocr`),
  module RAG (`src/rag`), lớp dịch vụ backend (`src/serving`), giao diện
  (`frontend/`), và bộ đánh giá (`benchmark/`, `data/rag`).
- **Loại tài liệu xử lý:** BCTC hợp nhất và các tài liệu tài chính tương tự, định
  dạng **PDF, Markdown (.md), JSON**.
- **Ràng buộc môi trường:** chạy **CPU-only (không cần GPU)** cho luồng RAG; LLM
  dùng dịch vụ Groq (`llama-3.3-70b-versatile`).
- **Ngoài phạm vi:** huấn luyện lại mô hình nền (embedding/LLM); phân tích đầu tư;
  tư vấn tài chính.

---

## 4. Thuật ngữ và định nghĩa / Từ viết tắt

| Thuật ngữ | Giải thích |
|---|---|
| **OCR** | Optical Character Recognition — nhận dạng ký tự quang học (ở đây dùng PaddleOCR-VL). |
| **RAG** | Retrieval-Augmented Generation — sinh câu trả lời có tăng cường truy hồi. |
| **BCTC** | Báo cáo tài chính (hợp nhất): CĐKT, KQKD, LCTT, Thuyết minh. |
| **CĐKT / KQKD / LCTT** | Bảng cân đối kế toán / Kết quả hoạt động kinh doanh / Lưu chuyển tiền tệ. |
| **Chunk** | Đoạn văn bản nhỏ, có cấu trúc, là đơn vị để nhúng và truy hồi. |
| **Embedding** | Vector số biểu diễn ngữ nghĩa của một đoạn văn bản. |
| **Dense / Sparse** | Vector dày (ngữ nghĩa, e5-large) / vector thưa (từ khóa, BM25). |
| **RRF** | Reciprocal Rank Fusion — hợp nhất kết quả hai nhánh truy hồi. |
| **MMR** | Maximal Marginal Relevance — chọn kết quả vừa liên quan vừa đa dạng. |
| **Routing** | Định tuyến câu hỏi tới đúng loại báo cáo / thuyết minh / năm để lọc mềm. |
| **Graph-RAG** | Lớp đồ thị tài chính liên kết cùng một chỉ tiêu qua các kỳ/năm. |
| **Mã số (line code)** | Mã chỉ tiêu cố định theo chuẩn VAS (vd: 01 = doanh thu, 50 = LN trước thuế). |
| **RAGAS** | Bộ chỉ số đánh giá RAG: Faithfulness, Answer Relevancy, Context Precision/Recall. |

---

## 5. Trách nhiệm

| Vai trò | Trách nhiệm chính |
|---|---|
| **Kỹ sư dữ liệu** | Vận hành OCR, kiểm tra chất lượng trích xuất, chuẩn hóa tài liệu golden. |
| **Kỹ sư ML/RAG** | Cấu hình chunking, embedding, truy hồi, lớp Graph-RAG; chạy benchmark. |
| **Kỹ sư backend** | Vận hành API tải lên / lập chỉ mục / hỏi đáp; bảo đảm hiệu năng đồng thời. |
| **Người kiểm soát chất lượng** | Phê duyệt tiêu chí chấp nhận OCR và ngưỡng chỉ số RAGAS. |
| **Quản lý sản phẩm** | Phê duyệt phiên bản quy trình, quyết định phát hành. |

---

## 6. Tổng quan kiến trúc hệ thống

```
            ┌──────────────────────────────────────────────────────────────┐
            │                        NGƯỜI DÙNG (Frontend React/Vite)        │
            └───────────────┬───────────────────────────┬──────────────────┘
                            │ tải tài liệu                │ đặt câu hỏi
                            ▼                             ▼
        ┌───────────────────────────┐        ┌──────────────────────────────┐
        │  API tải lên / lập chỉ mục │        │        API hỏi đáp (chat)     │
        │     (src/serving)          │        │        (src/serving)         │
        └─────────────┬─────────────┘        └───────────────┬──────────────┘
                      │                                        │
   PDF/MD/JSON  ──► OCR (src/ocr) ─► Hậu xử lý ─► Ingest ─► Chunking ─► Embedding
                                                                 │
                                                                 ▼
                                                   ┌─────────────────────────┐
                                                   │  Qdrant (dense + BM25)   │
                                                   └────────────┬────────────┘
                                                                │ truy hồi hybrid
                            Routing + Graph-RAG (xuyên năm) ◄────┤
                                                                ▼
                                              Dedup + MMR ─► Ngữ cảnh top-K
                                                                ▼
                                                   LLM Groq (sinh câu trả lời)
                                                                ▼
                                                  Câu trả lời + trích dẫn nguồn

   Lưu trữ phụ trợ: PostgreSQL (metadata phiên/tài liệu/chat) · Redis (bộ nhớ ngắn hạn)
```

---

## 7. Quy trình thực hiện chi tiết

### Bước 1 — Thu thập và tiếp nhận tài liệu
- Người dùng tải tài liệu (PDF/MD/JSON) lên một **phiên (session)**.
- Hệ thống kiểm tra định dạng (`SUPPORTED_EXTENSIONS`) và dung lượng (mặc định ≤ 50 MB),
  lưu bản gốc vào `data/sessions/<id>/uploads/`, tạo bản ghi tài liệu trạng thái
  `processing` trong PostgreSQL và trả về ngay (HTTP 201). Công việc nặng chạy nền.
- *Đầu vào:* tệp tài liệu. *Đầu ra:* tài liệu đã lưu + bản ghi `processing`.

### Bước 2 — OCR / Trích xuất văn bản (`src/ocr`, `src/serving/ingest.py`)
- **PDF có lớp text:** trích trực tiếp bằng PyMuPDF (nhanh, CPU).
- **PDF scan (không có lớp text):** chạy **PaddleOCR-VL** để nhận dạng (chạy ngoại tuyến
  trên máy có GPU hoặc bật `FINSIGHT_ENABLE_API_OCR`); bảng được xuất ra cả Markdown
  và JSON có cấu trúc (`*_tables.json`).
- **MD/JSON:** dùng trực tiếp / kết xuất JSON-bảng thành Markdown pipe sạch.
- *Đầu ra:* văn bản Markdown chuẩn hóa (+ nhãn nguồn: `pdf-text` / `ocr` / `markdown` / `json`).

### Bước 3 — Hậu xử lý & chuẩn hóa
- Chuyển bảng HTML của OCR sang Markdown pipe + JSON gọn (`src/ocr.postprocess`),
  giảm ~57% ký tự, giữ nguyên số liệu.
- Đối chiếu với **bộ golden** (`data/golden/`) đã được con người soát để bảo đảm độ chính xác.

### Bước 4 — Chunking có cấu trúc (`src/rag/chunking.py`)
- Tôn trọng cấu trúc tài liệu: **không cắt ngang bảng**, không tách tiêu đề khỏi nội dung.
- Mỗi chunk mang metadata: `page`, `heading`, `statement_type` (cdkt/kqkd/lctt/thuyết minh),
  `note_no`, `year`, `section_id` (cây mục lục).
- Bảng dùng cơ chế **parent-child** (truy hồi khớp nhóm dòng, sinh câu trả lời được
  đưa cả bảng); đính kèm **đơn vị tính** và **caption**; prepend ngữ cảnh tài liệu (tên + năm).

### Bước 5 — Embedding & Lập chỉ mục (`src/rag/embeddings.py`, `vectorstore.py`)
- Mỗi chunk được nhúng **2 vector**: **dense** `intfloat/multilingual-e5-large` (1024 chiều,
  ngữ nghĩa, đa ngôn ngữ) và **sparse** `Qdrant/bm25` (từ khóa/số/mã, chính xác).
- Chạy trên **FastEmbed/ONNX, CPU**. Upsert theo lô vào **Qdrant** (một collection,
  cô lập theo `session_id`). Tiến độ % được cập nhật về DB để hiển thị trên UI.

### Bước 6 — Truy hồi Hybrid + Routing + Graph-RAG (`src/rag/pipeline.py`, `graph_retrieval.py`)
- **Hybrid:** chạy song song nhánh dense + BM25, hợp nhất bằng **RRF** trong Qdrant.
- **Routing:** định tuyến câu hỏi tới đúng `statement_type`/`note_no`/`year` để lọc mềm,
  có suy biến an toàn (bỏ lọc năm trước, rồi bỏ hết khi không có kết quả).
- **Graph-RAG (xuyên năm):** nếu câu hỏi nhắc **≥ 2 năm** hoặc cụm "các năm / giai đoạn /
  tăng trưởng", hệ thống **fan-out** truy hồi theo từng năm rồi trộn xen kẽ, bảo đảm
  ngữ cảnh có đủ mọi kỳ — đây là cơ chế trả lời câu hỏi liên kết nhiều file/nhiều năm.
- **Hậu truy hồi:** gộp bảng cha (parent collapse) + **MMR** (vector hóa bằng numpy)
  để chọn top-K vừa liên quan vừa không trùng lặp.

### Bước 7 — Sinh câu trả lời (`src/rag/llm.py`)
- Ghép ngữ cảnh top-K + lịch sử hội thoại ngắn (Redis) và gọi **Groq** (`llama-3.3-70b`).
- **System prompt** ràng buộc: chỉ dùng ngữ cảnh; nêu kèm **đơn vị tính + kỳ/năm**;
  **trích dẫn nguồn** dạng `[1]`; **không bịa số**; trả lời theo ngôn ngữ câu hỏi.

---

## 8. Sơ đồ luồng quy trình (Lưu đồ)

```
 [Tải tài liệu]
       │
       ▼
 Định dạng hợp lệ? ──Không──► Từ chối (báo lỗi định dạng)
       │ Có
       ▼
 PDF có lớp text? ──Không──► [OCR PaddleOCR-VL] ─┐
       │ Có                                       │
       ▼                                          ▼
 [Trích text PyMuPDF] ─────────────────► [Markdown chuẩn hóa]
                                                  │
                                                  ▼
                                          [Chunking có cấu trúc]
                                                  │
                                                  ▼
                                   [Embedding dense + BM25] ──► [Qdrant]
                                                  │
          ┌───────────────────────────────────────┘
          ▼
 [Câu hỏi] ─► Đa kỳ? ──Có──► [Graph-RAG fan-out theo năm]
                 │ Không
                 ▼
            [Hybrid + Routing] ─► [Dedup + MMR] ─► [Ngữ cảnh top-K]
                                                        │
                                                        ▼
                                Có ngữ cảnh phù hợp? ──Không──► [Từ chối trả lời]
                                                        │ Có
                                                        ▼
                                                  [LLM sinh trả lời + trích dẫn]
```

---

## 9. Kiểm soát chất lượng

### 9.1 Chất lượng OCR (`benchmark/ocr/`)
- Tiêu chí chấp nhận trên trang chuẩn: **Number F1 = 100%** (số liệu là tối thượng),
  Char accuracy ≥ 85%, Word F1 ≥ 90%. Báo cáo: `ocr_validation_report.{md,csv}`.

### 9.2 Chất lượng RAG (`benchmark/rag/`, `data/rag/`)
- **Bộ dữ liệu đánh giá:** `finsight_finqa_eval_v2.jsonl` (~500 câu hỏi tài chính,
  gồm cả số và chữ, nhiều năm), đáp án được trích **xác định** từ bảng số liệu và
  **tự kiểm chứng chéo** (giá trị "năm nay" của báo cáo năm Y phải bằng "năm trước" của báo cáo Y+1).
- **Phương pháp đánh giá (theo RAGAS + tài chính):**
  - *Truy hồi:* Context Recall (số học), độ phủ kỳ (period coverage), Recall@k/MRR (khi có nhãn trang).
  - *Sinh:* khớp số tuyệt đối (FinanceBench-style), Token-F1/ROUGE-L, độ chính xác từ chối.
  - *RAGAS (LLM judge):* Context Precision, Context Recall, Faithfulness, Answer Relevancy, Answer Correctness.
- **Cách chạy:** `python -m benchmark.rag.evaluate_rag` (thêm `--retrieval-only`
  nếu không cần Groq; `--judge` để chạy RAGAS trên mẫu). Báo cáo lưu ở `benchmark/rag/results/`.

### 9.3 Kiểm soát chống bịa đặt
- System prompt cấm bịa số; ngưỡng điểm truy hồi (tùy chọn) loại câu khi không đủ liên quan;
  cơ chế **từ chối trả lời** khi không có ngữ cảnh — được đo bằng tập câu hỏi `unanswerable`.

---

## 10. Vận hành & hiệu năng (tải nhiều tệp đồng thời)

Kịch bản tham chiếu: **~10 tệp × ~100 trang tải lên cùng lúc**.

| Vấn đề | Biện pháp đã áp dụng |
|---|---|
| Quá tải CPU do nhiều job embedding chạy song song | **Cổng đồng thời** `FINSIGHT_EMBED_CONCURRENCY` (mặc định 1) — `BoundedSemaphore` bao quanh bước embedding; phần parse/chunk vẫn song song. |
| Cạnh tranh luồng yêu cầu (chat/poll bị nghẽn) | Bước embedding được tuần tự hóa qua cổng đồng thời; có thể tăng pool kết nối DB. |
| Cạn pool kết nối PostgreSQL | Nâng `pool_size=20, max_overflow=20, pool_recycle=1800`. |
| MMR chậm (vòng lặp Python O(n²)) | **Vector hóa bằng numpy** (một phép nhân ma trận). |
| Vector mồ côi khi hủy giữa chừng | Kiểm tra `should_cancel` trước cả lần flush cuối của lô upsert. |

> Khuyến nghị mở rộng: tách bước lập chỉ mục ra **worker nền chuyên dụng** (ThreadPoolExecutor
> giới hạn 1–2) thay vì BackgroundTask trên threadpool phục vụ request, để chat/poll luôn mượt.

---

## 11. Tài liệu tham khảo và biểu mẫu liên quan

- `data/rag/EVALUATION_METHODS.md` — khảo cứu phương pháp đánh giá RAG và lựa chọn cho Finsight.
- `data/rag/README.md`, `benchmark/rag/README.md` — mô tả bộ dữ liệu và cách chạy benchmark.
- `rag_upgrade.md`, `log_structure.md`, `error_upgrade.md` — nhật ký nâng cấp và audit.
- Mã nguồn lõi: `src/ocr/`, `src/rag/`, `src/serving/`.
- Tham chiếu học thuật: RAGAS (arXiv:2309.15217), FinanceBench (arXiv:2311.11944),
  LightRAG (EMNLP 2025), GraphRAG (Microsoft).

---

## 12. Lịch sử thay đổi

| Phiên bản | Ngày | Người soạn | Nội dung thay đổi | Người duyệt |
|---|---|---|---|---|
| 1.0 | 22/06/2026 | Nhóm Kỹ thuật Finsight | Ban hành lần đầu: chuẩn hóa quy trình OCR → RAG; bổ sung lớp Graph-RAG xuyên năm, bộ dữ liệu đánh giá ~500 câu và benchmark RAGAS; tối ưu hiệu năng tải nhiều tệp. | (chờ duyệt) |

---

*— Hết tài liệu FS-SOP-001 —*
