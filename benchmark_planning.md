# Kế hoạch Benchmark RAG — Finsight

> Mục tiêu: biến mọi quyết định kỹ thuật (embedding, chunking, hybrid search) thành
> quyết định **dựa trên số liệu**, không phải phỏng đoán. Đo trước, sửa sau.
>
> Thứ tự ưu tiên: **① Retrieval → ② Embedding → ③ Chunking → ④ Hybrid Search**.
> Lý do: nếu Retrieval chưa đạt ~95% thì chưa đáng đầu tư vào tầng reasoning;
> còn Embedding/Chunking/Hybrid chính là các đòn bẩy để kéo Retrieval lên.

---

## 0. Hiện trạng & khoảng trống (đọc trước khi bắt đầu)

Hạ tầng benchmark **đã có sẵn** trong repo:

| Thành phần | Vị trí | Trạng thái |
|---|---|---|
| Harness đánh giá end-to-end | `benchmark/rag/evaluate_rag.py` | ✅ chạy được (index → retrieve → generate → score) |
| Bộ chỉ số (IR + numeric + lexical + RAGAS) | `benchmark/rag/metrics.py` | ✅ có đủ hàm Recall@k, Precision@k, Hit@k, MRR, nDCG |
| Bộ câu hỏi vàng v2 | `data/rag/finsight_finqa_eval_v2.jsonl` | ✅ 483 câu, đa năm |
| Corpus 5 năm BCTC | `data/rag/corpus/` | ✅ 561 chunks |
| Báo cáo kết quả | `benchmark/rag/results/latest.md` | ✅ tự sinh JSON + Markdown |

### ⚠️ Khoảng trống lớn nhất phải xử lý đầu tiên

Hàm `recall_at_k`, `mrr`, `ndcg_at_k`, `hit_at_k` trong `metrics.py` **yêu cầu nhãn
liên quan ở mức trang/chunk** (`relevant_pages`). Nhưng bộ câu hỏi vàng hiện tại
**chỉ có** `relevant_years` + `gold_numbers`, **không có** `relevant_pages`.

Hệ quả: báo cáo `latest.md` hiện chỉ đo được **context recall theo số (proxy)** và
**period coverage**, chứ **chưa** tính được Recall@5 / Recall@10 / MRR / nDCG / Hit
Rate đúng nghĩa IR như yêu cầu.

👉 **Việc đầu tiên của Giai đoạn ① là gắn nhãn chunk liên quan cho golden set.**
Không có nhãn này thì các chỉ số IR là vô nghĩa.

---

## ① Benchmark Retrieval ⭐⭐⭐⭐⭐ (quan trọng nhất)

### Mục tiêu
- Golden set ~200 câu (đã có 483 câu — chỉ cần **bổ sung nhãn chunk liên quan**).
- Đo: **Recall@5, Recall@10, MRR, nDCG@10, Hit Rate** (đúng chuẩn IR).
- **Ngưỡng đạt: Recall@10 ≥ 95%.** Đạt mới chuyển sang xây tầng reasoning.

### Bước 1.1 — Gắn nhãn chunk liên quan (việc bắt buộc, làm trước)
Mỗi câu hỏi cần thêm trường `relevant_chunk_ids` (hoặc `relevant_pages`) trỏ tới
đúng chunk chứa đáp án. Hai cách:

1. **Bán tự động (khuyến nghị):** index corpus → với mỗi câu, tìm chunk chứa
   `gold_numbers` (canonical theo định dạng VN `.` ngăn nghìn) → đánh dấu chunk đó
   là gold → người review xác nhận nhanh. Tận dụng `extract_numbers()` đã có trong
   `metrics.py`.
2. **Thủ công:** với câu reasoning/multi_year không có số rõ ràng, gắn tay.

Đầu ra: `data/rag/finsight_finqa_eval_v3.jsonl` có thêm `relevant_chunk_ids`.

### Bước 1.2 — Bật chỉ số IR trong harness
Sửa `evaluate_rag.py` để khi item có `relevant_chunk_ids` thì gọi
`recall_at_k / reciprocal_rank / ndcg_at_k / hit_at_k` (đã có sẵn trong `metrics.py`)
và tổng hợp trung bình toàn tập + breakdown theo `answer_type`.

### Bước 1.3 — Mẫu câu hỏi vàng (đã có, đối chiếu để bổ sung)
Các dạng cần phủ (mỗi dạng ≥ 25 câu):

| Dạng (`answer_type`) | Ví dụ |
|---|---|
| `numeric_single` | "Doanh thu năm 2023 là bao nhiêu?" / "Lợi nhuận sau thuế năm 2022?" |
| `numeric_single` | "Tiền và tương đương tiền cuối kỳ?" |
| `numeric_compare` | "Doanh thu tăng bao nhiêu so với 2022?" |
| `multi_year` | "Xu hướng lợi nhuận 2021–2024?" |
| `reasoning` | "Vì sao dòng tiền hoạt động giảm?" |
| `factual` / `policy` | "Chính sách khấu hao tài sản cố định?" |
| `unanswerable` | câu không có trong tài liệu (đo abstention) |

### Bảng kết quả mục tiêu (Giai đoạn ①)

| Cấu hình | Recall@5 | Recall@10 | MRR | nDCG@10 | Hit Rate |
|---|---|---|---|---|---|
| Baseline hiện tại | | | | | |
| Mục tiêu | ≥ 0.90 | **≥ 0.95** | ≥ 0.85 | ≥ 0.90 | ≥ 0.97 |

### Lệnh chạy
```bash
docker compose up -d qdrant
python -m benchmark.rag.evaluate_rag --retrieval-only          # toàn bộ, không cần Groq
python -m benchmark.rag.evaluate_rag --retrieval-only --limit 20   # lặp nhanh
```

---

## ② Benchmark Embedding

> Đừng mặc định model embedding nào là tốt nhất. Đo trên **tài liệu tài chính
> tiếng Việt** mới biết.

### Các model cần thử

| Model | Backend | Chiều | Ghi chú |
|---|---|---|---|
| `intfloat/multilingual-e5-large` | local (FastEmbed/ONNX) | 1024 | **baseline hiện tại** |
| `AITeamVN/Vietnamese_Embedding` | API (`FINSIGHT_EMBED_BACKEND=api`) | 1024 | đã tích hợp (xem `embedding.md`) |
| BGE-M3 | — | 1024 | ⚠️ chưa có trong FastEmbed (xem memory) → cần TEI/sentence-transformers |
| Nomic Embed (`nomic-embed-text-v1.5`) | local/ONNX | 768 | |
| Jina Embeddings v3 | API/local | 1024 | đa ngôn ngữ |
| E5 (multilingual base/small) | local | 384/768 | so latency vs large |

### Chỉ số đo cho mỗi model
- **Chất lượng:** Recall@5, Recall@10, MRR, nDCG@10 (chạy lại harness Giai đoạn ①).
- **Latency:** thời gian embed trung bình / câu truy vấn (ms) và / chunk khi index.
- **CPU:** % CPU lúc embed (môi trường no-GPU).
- **RAM:** dung lượng đỉnh khi load model + index.

### Bảng kết quả mục tiêu (Giai đoạn ②)

| Model | Recall@10 | MRR | nDCG@10 | Latency/query (ms) | CPU | RAM (GB) |
|---|---|---|---|---|---|---|
| e5-large (baseline) | | | | | | |
| Vietnamese_Embedding (API) | | | | | | |
| Nomic Embed | | | | | | |
| Jina v3 | | | | | | |
| E5-base | | | | | | |

### Cách chuyển model (env, đọc bởi `src/serving/config.py`)
```bash
# Local
FINSIGHT_EMBED_MODEL=intfloat/multilingual-e5-large FINSIGHT_EMBED_DIM=1024 \
  python -m benchmark.rag.evaluate_rag --retrieval-only

# API (Vietnamese_Embedding)
FINSIGHT_EMBED_BACKEND=api FINSIGHT_API_EMBED_MODEL=AITeamVN/Vietnamese_Embedding \
  python -m benchmark.rag.evaluate_rag --retrieval-only
```
> Lưu ý: đổi model/chiều embedding → **bắt buộc re-index** corpus (chạy không có `--no-index`).

---

## ③ Benchmark Chunking

> Có thể chính chunking là nguyên nhân Retrieval chưa tốt. Đo để biết.

### Các chiến lược cần thử

| Chiến lược | Mô tả | Tham số |
|---|---|---|
| Fixed chunk | cắt cố định theo ký tự/token | size ∈ {512, 1024, 1800} |
| Recursive chunk | cắt đệ quy theo separator | size 1024, overlap 200 |
| **Structure-aware** | bám cấu trúc bảng/note (của chúng ta) | `chunk_markdown` hiện tại |
| Semantic chunk | cắt theo ranh giới ngữ nghĩa (embedding) | threshold 0.7 |

### Tham số hiện tại (mặc định, đọc từ config)
- `FINSIGHT_CHUNK_SIZE=1800`
- `FINSIGHT_CHUNK_OVERLAP=250`

### Chỉ số đo
- Recall@10 / MRR / nDCG@10 (chính).
- Số chunk sinh ra (ảnh hưởng chi phí index + RAM).
- Context recall theo số (proxy đã có) — chunking sai sẽ làm số bị cắt khỏi chunk.

### Bảng kết quả mục tiêu (Giai đoạn ③)

| Chunking | size/overlap | #chunks | Recall@10 | MRR | nDCG@10 | CtxRecall# |
|---|---|---|---|---|---|---|
| Fixed 512 | 512 / 64 | | | | | |
| Fixed 1024 | 1024 / 128 | | | | | |
| Recursive | 1024 / 200 | | | | | |
| Structure-aware (baseline) | 1800 / 250 | | | | | |
| Semantic | — | | | | | |

### Lệnh chạy (quét size)
```bash
for S in 512 1024 1800; do
  FINSIGHT_CHUNK_SIZE=$S python -m benchmark.rag.evaluate_rag --retrieval-only
done
```
> Mỗi lần đổi chunking → re-index (không dùng `--no-index`).

---

## ④ Hybrid Search (tinh chỉnh)

> Để **số liệu** quyết định trọng số, không đoán.

### Tham số cần quét

| Tham số | Env | Mặc định | Khoảng quét |
|---|---|---|---|
| Bật hybrid (dense+BM25) | `FINSIGHT_USE_HYBRID` | true | {true, false} |
| Trọng số dense vs BM25 | (RRF / fusion trong `src/rag`) | — | dense ∈ {0.3…0.7} |
| Tham số RRF `k` | (mã fusion) | 60 | {20, 40, 60, 100} |
| top_k | `FINSIGHT_TOP_K` | 8 | {5, 8, 10, 15} |
| Số ứng viên truy hồi | `FINSIGHT_RETRIEVE_CANDIDATES` | 50 | {30, 50, 80} |
| MMR lambda | `FINSIGHT_MMR_LAMBDA` | 0.6 | {0.4, 0.6, 0.8} (1=relevance, 0=diversity) |
| Routing | `FINSIGHT_USE_ROUTING` | true | {true, false} |
| Graph fan-out | `FINSIGHT_USE_GRAPH` | true | {true, false} (giúp multi_year) |

### A/B mẫu
```bash
# BM25 có thực sự kéo được con số chính xác không?
FINSIGHT_USE_HYBRID=true  python -m benchmark.rag.evaluate_rag --retrieval-only
FINSIGHT_USE_HYBRID=false python -m benchmark.rag.evaluate_rag --retrieval-only

# Graph-RAG cross-period (giúp câu multi_year)
FINSIGHT_USE_GRAPH=true  python -m benchmark.rag.evaluate_rag --retrieval-only
FINSIGHT_USE_GRAPH=false python -m benchmark.rag.evaluate_rag --retrieval-only
```

### Bảng kết quả mục tiêu (Giai đoạn ④)

| Cấu hình | Hybrid | dense:BM25 | RRF k | top_k | MMR λ | Recall@10 | MRR | nDCG@10 |
|---|---|---|---|---|---|---|---|---|
| Baseline | true | — | 60 | 8 | 0.6 | | | |
| Best (điền sau) | | | | | | | | |

---

## Quy trình tổng & nguyên tắc

1. **Một biến mỗi lần.** Mỗi run chỉ đổi một knob → mới quy được nguyên nhân.
2. **Khóa golden set.** Sau khi gắn nhãn `relevant_chunk_ids` thì đóng băng v3, không sửa giữa chừng.
3. **Ghi lại mọi run.** Harness tự lưu `results/rag_eval_<timestamp>.{json,md}` + cập nhật `latest.md`. Lập một bảng tổng hợp tay so sánh các cấu hình.
4. **Deterministic trước, LLM-judge sau.** Chỉ số IR + numeric không cần API; RAGAS (`--judge --judge-sample 40`) chạy trên mẫu vì Groq free ~12k TPM.
5. **Cổng chất lượng:** chỉ chuyển sang xây reasoning khi **Recall@10 ≥ 95%** trên golden set.

### Thứ tự thực thi đề xuất
```
① Gắn nhãn chunk + bật chỉ số IR  →  đo baseline Recall@k/MRR/nDCG/Hit
② Quét embedding (giữ chunking + hybrid cố định)  →  chọn model tốt nhất
③ Quét chunking (giữ embedding tốt nhất)          →  chọn chiến lược tốt nhất
④ Tinh chỉnh hybrid (giữ ②③ tốt nhất)             →  chốt cấu hình cuối
```

### Việc cần làm ngay (checklist)
- [ ] Viết script gắn nhãn `relevant_chunk_ids` (bán tự động qua `gold_numbers`).
- [ ] Sinh `data/rag/finsight_finqa_eval_v3.jsonl` và review.
- [ ] Bổ sung tính Recall@k/MRR/nDCG/Hit vào `evaluate_rag.py` (hàm đã có trong `metrics.py`).
- [ ] Chạy baseline → điền bảng Giai đoạn ①.
- [ ] Lần lượt ② → ③ → ④, điền các bảng kết quả.



docker compose up -d qdrant
.venv/bin/python -m benchmark.rag.evaluate_rag \
  --dataset data/rag/finsight_golden_v1.jsonl --retrieval-only