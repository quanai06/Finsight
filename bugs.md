# Finsight — Bugs & Performance Log

> Ghi lại bug + đo hiệu năng đợt 2026-06-22. Hai vấn đề: (1) hủy upload nhưng task
> nền vẫn chạy ngốn CPU, (2) index một file mất ~8–11 phút. Đo trên file thật
> `data/processed/ocr_clean/2021_bctc_hop_nhat...md` (191.810 ký tự → **284 chunk**),
> máy 12 core, CPU-only.

---

## BUG #1 — Hủy upload (nút X) nhưng embedding nền vẫn chạy → CPU treo 100% — ✅ ĐÃ FIX

### Triệu chứng
Upload giữa chừng bấm X, UI báo đã xóa nhưng **CPU vẫn chạy ~470%** (5 nhân) thêm
nhiều phút. Đo được process `uvicorn` ăn 470% CPU dù tài liệu đã bị xóa.

### Nguyên nhân gốc
`DELETE /documents/{doc_id}` chỉ xóa bản ghi + vector + file, **không hủy được task
embedding nền**. FastAPI `BackgroundTasks` chạy trong threadpool **không có cơ chế
cancel** — vòng lặp nhúng 284 chunk cứ chạy tới hết rồi mới cố ghi vào bản ghi đã
xóa. (Đây là **BE2** trong `error_upgrade.md`, lộ rõ vì embedding quá chậm — xem Bug #2.)

### Cách fix (đã code)
- `src/serving/routes/documents.py`: thêm `_IndexJobs` (registry theo `doc_id`, có
  lock). `DELETE` gọi `_jobs.cancel(doc_id)` **trước khi** xóa bản ghi.
- `src/rag/vectorstore.py`: `add()` nhận `should_cancel` và **poll mỗi chunk**; gặp
  cờ hủy thì **dừng ngay**, trả số chunk đã làm.
- `_process_document`: truyền `should_cancel`, khi bị hủy thì **dọn vector dở**
  (`delete_doc`) và không ghi `ready`; `finally` luôn `finish` job.
- Test: `tests/test_rag.py::test_index_jobs_cancel_lifecycle`,
  `::test_vectorstore_add_stops_early_when_cancelled`.

→ Bấm X giờ **dừng embedding trong vòng 1 chunk**, không cày nốt 284 chunk.

---

## BUG #2 — Index một file mất ~8–11 phút — ⚠️ ĐÃ GIẢM NHẸ + CÓ KHUYẾN NGHỊ

### Đo per-phase thực tế (file 2021, 284 chunk)
| Pha | Thời gian | % | ms/chunk |
| --- | --- | --- | --- |
| ingest (đọc .md) | 0.01s | ~0% | — |
| chunk (hierarchical) | 0.33s | ~0% | — |
| **embed dense — e5-large** | **689.4s (~11.5 phút)** | **99.8%** | **2.428 ms** |
| embed sparse — BM25 | 1.0s | 0.1% | 3 ms |
| **TỔNG (e5-large)** | **~691s (~11.5 phút)** | 100% | |

→ **Bottleneck là 100% embedding dense e5-large.** ingest/chunk/sparse **không đáng kể**.
Chunk thật dài (gần 512 token, nhiều bảng) nên còn chậm hơn benchmark synthetic
(545 ms/chunk) — thực tế **2.428 ms/chunk**.

### Cái KHÔNG giúp (đã đo, loại trừ)
- **Tăng threads**: benchmark `threads=12` → **chậm hơn** (545→645 ms/chunk).
  onnxruntime mặc định đã tối ưu; ép số luồng = oversubscribe → contention.
- **Tăng batch_size** (16→64): không cải thiện (617 ms/chunk).
- ⇒ **thread/batch không phải đòn bẩy.** Đã để mặc định auto, expose qua `.env` để tinh chỉnh.

### Đòn bẩy THẬT (đo được)
| Phương án | Thời gian embed | Tăng tốc | Đánh đổi |
| --- | --- | --- | --- |
| e5-large (hiện tại, 1024-dim) | 689s | 1x | chất lượng cao nhất |
| **MiniLM-L12 (384-dim)** | **39s** | **17.7x** | chất lượng truy hồi thấp hơn; phải nhúng lại |
| int8-quantize e5-large | ~230–350s (ước) | ~2–3x | giữ chất lượng; cần custom ONNX + validate |

### Đã fix trong code (phần an toàn, không đổi chất lượng)
- **Warm-up model lúc khởi động** (`app.py`): load + chạy 1 lần lúc boot → **không
  upload nào phải trả phí load/first-inference** giữa chừng. (Đáp ứng "chỉ load lần đầu".)
- **Log timing per-phase** mỗi lần index (`ingest/chunk/embed/total`) + bật log app
  (`logging.basicConfig`) để số liệu hiện ra trong log backend.
- **Config thread/batch** qua `.env`: `FINSIGHT_EMBED_THREADS=0` (auto), `FINSIGHT_EMBED_BATCH=16`.

### ⚠️ Khuyến nghị (CẦN BẠN QUYẾT — chưa tự đổi vì ảnh hưởng chất lượng)
1. **Nhanh nhất, đổi 1 dòng `.env` + nhúng lại** → MiniLM-L12:
   ```
   FINSIGHT_EMBED_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
   FINSIGHT_EMBED_DIM=384
   ```
   11.5 phút → ~40s. Đổi lại: vector 384-dim, truy hồi/đa ngôn ngữ yếu hơn e5-large.
   → Hợp nếu ưu tiên tốc độ; nên **A/B test chất lượng** trên vài câu hỏi tài chính trước.
2. **Giữ chất lượng e5-large nhưng int8-quantize** (~2–3x): cần cài `onnx`, quantize
   model (external-data 2GB) + đăng ký custom model + **kiểm chứng vector không lệch**.
   Rủi ro hơn → nên làm có kiểm thử, không làm mù.
3. (Bổ trợ) **mpnet-base 768-dim**: trung gian chất lượng/tốc độ — có thể đo thêm.

---

## Phụ — quan sát khác trong lúc test
- **Collection không tự reset khi restart** nếu đã là schema hybrid → giữ point cũ của
  các session test trước (thấy 545 point dù doc mới chỉ 289). Không phải bug, nhưng khi
  cần đo sạch nên xóa collection hoặc dùng tên collection mới.
- **`bc` không có trên máy** → script đo wall-clock bằng `bc` lỗi (đã chuyển sang đo
  per-phase bằng Python `time.perf_counter`, chính xác hơn).

---

## Trạng thái code
| Hạng mục | Trạng thái |
| --- | --- |
| Bug #1 cancel | ✅ Fixed + test |
| Bug #2 warm-up / timing log / config | ✅ Done |
| Bug #2 đổi model nhanh (MiniLM / int8) | ⏳ Chờ bạn quyết |
| Test suite | ✅ 23/23 pass |

Tất cả đang ở **working tree, chưa commit**.
