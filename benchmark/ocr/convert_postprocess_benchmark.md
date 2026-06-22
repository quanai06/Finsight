# Convert Benchmark — HTML → Markdown + JSON (postprocess)

Chuyển bảng HTML của OCR (PaddleOCR-VL) sang Markdown sạch + JSON có cấu trúc,
chạy bằng `python -m src.ocr.postprocess`.

| Năm | Số bảng | Ký tự (trước → sau) |
|---|---|---|
| 2021 | 75 | 467K → 192K |
| 2022 | 85 | 516K → 224K |
| 2023 | 81 | 563K → 241K |
| 2024 | 81 | 601K → 263K |
| 2025 | 88 | 572K → 249K |
| **Tổng** | **410** | **2.72M → 1.17M (-57%)** |
