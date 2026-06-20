# OCR Number Validation Report
Tables scanned: 412 across 9 file(s) — {'2021': 75, '2022': 85, '2023': 81, '2024': 81, '2025': 88, 'page_001_tables': 0, 'page_002_tables': 0, 'page_013_tables': 1, 'page_014_tables': 1}
**Flagged cells: 257**  (high 177, medium 0, low 80)

## By rule
| Rule | Count |
|---|---|
| adjacent_duplicate | 103 |
| ragged_row | 80 |
| big_num_in_ref_col | 45 |
| cross_year_mismatch | 29 |

## Flagged cells (review these against the PDF)
| sev | file | table | row(Mã) | column | value | rule | detail |
|---|---|---|---|---|---|---|---|
| high | 2021 | 6 | 4 | cols 3,4 | 623.385 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2021 | 7 | 20 | Thuyết minh | 34.064.705 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2021 | 7 | 20 | cols 2,3 | 34.064.705 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2021 | 9 | 2 | Thuyết minh | 14.919.628 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2021 | 10 | 1 | Thuyết minh | 20.461.915 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2021 | 14 | 18 | cols 2,3 | 324.510 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2021 | 19 | 5 | cols 1,2 | -70.638 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2021 | 21 | 13 | cols 1,2 | 73.367 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2021 | 42 | 11 | cols 1,2 | 2.016 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2021 | 43 | 7 | cols 8,9 | 159.903 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2021 | 43 | 8 | cols 8,9 | 376.543 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2021 | 43 | 10 | cols 8,9 | 10.382.468 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2021 | 43 | 11 | cols 8,9 | -1.718.207 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2021 | 44 | 2 | cols 0,1 | -1.344.123 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2021 | 46 | 4 | cols 1,2 | 62.338.466 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2021 | 46 | 7 | cols 1,2 | 62.338.466 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2022 | - | các khoản dự phòng | Năm trước (vs 2021) | 10.100.081 | cross_year_mismatch | 2022 'năm trước'=10.100.081 ≠ 2021 'năm nay'=-7.287.409 (có thể do trình bày lại) |
| high | 2022 | - | tiền lãi vay đã trả | Năm trước (vs 2021) | -9.217.300 | cross_year_mismatch | 2022 'năm trước'=-9.217.300 ≠ 2021 'năm nay'=-10.731.071 (có thể do trình bày lại) |
| high | 2022 | 5 | 414 | cols 3,4 | 18.481.872 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2022 | 5 | 415 | cols 3,4 | -1.344.123 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2022 | 6 | 23 | Thuyết minh | (10.944.221) | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2022 | 9 | 32 | Thuyết minh | (3.382.021) | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2022 | 9 | 33 | Thuyết minh | 31.751.891 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2022 | 9 | 34 | Thuyết minh | 7.959.840 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2022 | 9 | 35 | Thuyết minh | 18.352.236 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2022 | 9 | 36 | Thuyết minh | (98.774) | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2022 | 9 | 37 | Thuyết minh | 26.213.302 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2022 | 14 | 1 | cols 1,2 | 1.994.665 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2022 | 14 | 2 | cols 1,2 | 2.388.268 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2022 | 14 | 3 | cols 1,2 | 4.382.933 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2022 | 23 | 11 | cols 6,7 | -1.120.095 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2022 | 31 | 1 | cols 4,5 | -83.775 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2022 | 31 | 4 | cols 4,5 | -83.775 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2022 | 31 | 8 | cols 4,5 | -46.599 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2022 | 41 | 5 | cols 8,9 | 159.903 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2022 | 41 | 7 | cols 8,9 | 10.382.468 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2022 | 41 | 8 | cols 8,9 | -1.718.207 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2022 | 42 | 6 | cols 8,9 | 4.723.482 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2022 | 42 | 7 | cols 8,9 | -3.382.021 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2022 | 43 | 3 | cols 1,2 | -1.344.123 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2022 | 45 | 5 | cols 1,2 | 103.645.482 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2022 | 45 | 6 | cols 1,2 | 103.645.482 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2022 | 73 | 5 | cols 1,2 | 15.048 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2023 | - | các khoản tương đương tiền | Năm trước (vs 2022) | 18.316.977 | cross_year_mismatch | 2023 'năm trước'=18.316.977 ≠ 2022 'năm nay'=7.896.325 (có thể do trình bày lại) |
| high | 2023 | - | trả trước cho người bán ngắn | Năm trước (vs 2022) | 25.276.287 | cross_year_mismatch | 2023 'năm trước'=25.276.287 ≠ 2022 'năm nay'=37.954.852 (có thể do trình bày lại) |
| high | 2023 | - | phải thu về cho vay ngắn hạn | Năm trước (vs 2022) | 37.954.852 | cross_year_mismatch | 2023 'năm trước'=37.954.852 ≠ 2022 'năm nay'=8.256.866 (có thể do trình bày lại) |
| high | 2023 | - | phải thu ngắn hạn khác | Năm trước (vs 2022) | 8.256.866 | cross_year_mismatch | 2023 'năm trước'=8.256.866 ≠ 2022 'năm nay'=55.864.370 (có thể do trình bày lại) |
| high | 2023 | - | dự phòng phải thu ngắn hạn k | Năm trước (vs 2022) | 55.864.370 | cross_year_mismatch | 2023 'năm trước'=55.864.370 ≠ 2022 'năm nay'=-1.120.358 (có thể do trình bày lại) |
| high | 2023 | - | phải trả ngắn hạn khác | Năm trước (vs 2022) | 75.558.793 | cross_year_mismatch | 2023 'năm trước'=75.558.793 ≠ 2022 'năm nay'=67.921.473 (có thể do trình bày lại) |
| high | 2023 | - | vay ngắn hạn | Năm trước (vs 2022) | 15.314.812 | cross_year_mismatch | 2023 'năm trước'=15.314.812 ≠ 2022 'năm nay'=-34.376.185 (có thể do trình bày lại) |
| high | 2023 | - | vay dài hạn đến hạn trả | Năm trước (vs 2022) | 16.086.798 | cross_year_mismatch | 2023 'năm trước'=16.086.798 ≠ 2022 'năm nay'=-6.795.198 (có thể do trình bày lại) |
| high | 2023 | - | trái phiếu dài hạn đến hạn t | Năm trước (vs 2022) | 9.192.847 | cross_year_mismatch | 2023 'năm trước'=9.192.847 ≠ 2022 'năm nay'=-11.000.000 (có thể do trình bày lại) |
| high | 2023 | - | trái phiếu dài hạn | Năm trước (vs 2022) | 58.393.968 | cross_year_mismatch | 2023 'năm trước'=58.393.968 ≠ 2022 'năm nay'=-11.871.918 (có thể do trình bày lại) |
| high | 2023 | 5 | 4 | cols 3,4 | 549.217 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2023 | 5 | 415 | cols 3,4 | -1.344.123 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2023 | 8 | 01 | Thuyết minh | 13.769.352 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 02 | Thuyết minh | 17.605.842 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 03 | Thuyết minh | 6.442.431 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 04 | Thuyết minh | 2.523.845 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 05 | Thuyết minh | (17.296.045) | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 08 | Thuyết minh | 40.291.296 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 09 | Thuyết minh | (50.508.784) | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 10 | Thuyết minh | (9.345.650) | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 11 | Thuyết minh | 17.867.029 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 12 | Thuyết minh | 650.334 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 13 | Thuyết minh | 2.352.947 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 14 | Thuyết minh | (14.438.520) | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 15 | Thuyết minh | (6.880.320) | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 20 | Thuyết minh | (20.011.668) | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 21 | Thuyết minh | (54.548.151) | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 22 | Thuyết minh | 5.774.148 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 23 | Thuyết minh | (13.925.224) | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 24 | Thuyết minh | 12.921.899 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 25 | Thuyết minh | (26.339.194) | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 26 | Thuyết minh | 47.294.434 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 27 | Thuyết minh | 1.836.680 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 8 | 30 | Thuyết minh | (26.985.408) | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 9 | 40 | Thuyết minh | 48.718.276 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 9 | 50 | Thuyết minh | 1.721.200 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 9 | 60 | Thuyết minh | 26.213.302 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 9 | 61 | Thuyết minh | 48.121 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2023 | 12 | 1 | cols 1,2 | 2.352.924 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2023 | 12 | 2 | cols 1,2 | 2.277.479 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2023 | 12 | 3 | cols 1,2 | 2.368.268 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2023 | 12 | 4 | cols 1,2 | 6.998.671 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2023 | 39 | 4 | cols 4,5 | 9.501.445 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2023 | 39 | 6 | cols 4,5 | 9.501.445 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2023 | 41 | 5 | cols 8,9 | 4.723.482 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2023 | 41 | 6 | cols 8,9 | -3.382.021 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2023 | 42 | 5 | cols 7,8 | 10.740.611 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2023 | 43 | 3 | cols 1,2 | -1.344.123 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2023 | 44 | 10 | cols 1,2 | 54.921.745 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2023 | 44 | 11 | cols 1,2 | 103.645.482 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2023 | 44 | 12 | cols 1,2 | 103.645.482 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2023 | 44 | 15 | cols 1,2 | 54.921.745 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2023 | 70 | 7 | cols 4,5 | 48.694 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2023 | 72 | 9 | cols 1,2 | 15.048 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | - | các khoản tương đương tiền | Năm trước (vs 2023) | 26.529.351 | cross_year_mismatch | 2024 'năm trước'=26.529.351 ≠ 2023 'năm nay'=1.453.272 (có thể do trình bày lại) |
| high | 2024 | - | trả trước cho người bán ngắn | Năm trước (vs 2023) | 37.390.279 | cross_year_mismatch | 2024 'năm trước'=37.390.279 ≠ 2023 'năm nay'=27.473.498 (có thể do trình bày lại) |
| high | 2024 | - | phải thu về cho vay ngắn hạn | Năm trước (vs 2023) | 7.637.650 | cross_year_mismatch | 2024 'năm trước'=7.637.650 ≠ 2023 'năm nay'=37.390.279 (có thể do trình bày lại) |
| high | 2024 | - | phải thu ngắn hạn khác | Năm trước (vs 2023) | 96.748.810 | cross_year_mismatch | 2024 'năm trước'=96.748.810 ≠ 2023 'năm nay'=7.637.650 (có thể do trình bày lại) |
| high | 2024 | - | dự phòng phải thu ngắn hạn k | Năm trước (vs 2023) | -1.135.506 | cross_year_mismatch | 2024 'năm trước'=-1.135.506 ≠ 2023 'năm nay'=96.748.810 (có thể do trình bày lại) |
| high | 2024 | - | tài sản ngắn hạn khác | Năm trước (vs 2023) | 292.336 | cross_year_mismatch | 2024 'năm trước'=292.336 ≠ 2023 'năm nay'=36.094.273 (có thể do trình bày lại) |
| high | 2024 | - | vốn góp từ cổ đông | Năm trước (vs 2023) | 38.236.616 | cross_year_mismatch | 2024 'năm trước'=38.236.616 ≠ 2023 'năm nay'=38.785.833 (có thể do trình bày lại) |
| high | 2024 | 3 | 411 | cols 3,4 | 38.785.833 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 3 | 4 | cols 3,4 | 38.236.616 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 3 | 5 | cols 3,4 | 549.217 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 3 | 415 | cols 3,4 | -1.344.123 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 7 | 40 | Thuyết minh | 10.934.354 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2024 | 7 | 50 | Thuyết minh | 14.937.764 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2024 | 7 | 60 | Thuyết minh | 27.982.623 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2024 | 7 | 61 | Thuyết minh | (338.021) | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2024 | 14 | 1 | cols 1,2 | 1.500.000 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 14 | 3 | cols 1,2 | 2.128.250 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 14 | 4 | cols 1,2 | 3.628.250 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 15 | 1 | cols 1,2 | 5.090.634 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 15 | 2 | cols 3,4 | 2.277.479 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 15 | 3 | cols 3,4 | 2.368.268 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 15 | 4 | cols 1,2 | 5.090.634 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 19 | 8 | cols 1,2 | 821.600 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 23 | 23 | cols 1,2 | 1.032.337 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 31 | 0 | cols 3,4 | 4.761.841 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 31 | 2 | cols 3,4 | -395.694 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 31 | 4 | cols 3,4 | 4.269.216 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 31 | 6 | cols 3,4 | -350.416 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 41 | 4 | cols 4,5 | 9.501.445 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 41 | 6 | cols 4,5 | 9.501.445 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 44 | 9 | cols 8,9 | 10.740.611 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 45 | 4 | cols 1,2 | -1.344.123 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 46 | 3 | cols 1,2 | 38.785.833 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 46 | 6 | cols 1,2 | 3.878.583.306 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 46 | 7 | cols 1,2 | 3.878.583.306 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 46 | 8 | cols 1,2 | 3.823.661.561 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 46 | 9 | cols 1,2 | 54.921.745 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 46 | 10 | cols 1,2 | 103.645.482 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 46 | 11 | cols 1,2 | 103.645.482 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 46 | 12 | cols 1,2 | 3.774.937.824 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 46 | 13 | cols 1,2 | 3.720.016.079 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 46 | 14 | cols 1,2 | 54.921.745 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 61 | 14 | cols 3,4 | 51.326 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 70 | 2 | cols 1,2 | -60.950 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2024 | 75 | 13 | cols 1,2 | 15.048 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | - | tài sản ngắn hạn khác | Năm trước (vs 2024) | 25.937.361 | cross_year_mismatch | 2025 'năm trước'=25.937.361 ≠ 2024 'năm nay'=312.596 (có thể do trình bày lại) |
| high | 2025 | - | lãi cơ bản trên cổ phiếu | Năm trước (vs 2024) | 1.523 | cross_year_mismatch | 2025 'năm trước'=1.523 ≠ 2024 'năm nay'=3.045 (có thể do trình bày lại) |
| high | 2025 | - | lãi suy giảm trên cổ phiếu | Năm trước (vs 2024) | 1.488 | cross_year_mismatch | 2025 'năm trước'=1.488 ≠ 2024 'năm nay'=2.976 (có thể do trình bày lại) |
| high | 2025 | - | các khoản dự phòng | Năm trước (vs 2024) | 22.627.124 | cross_year_mismatch | 2025 'năm trước'=22.627.124 ≠ 2024 'năm nay'=10.427.372 (có thể do trình bày lại) |
| high | 2025 | - | lỗ chênh lệch tỷ giá hối đoá | Năm trước (vs 2024) | 10.427.372 | cross_year_mismatch | 2025 'năm trước'=10.427.372 ≠ 2024 'năm nay'=2.567.767 (có thể do trình bày lại) |
| high | 2025 | - | tăng các khoản phải thu | Năm trước (vs 2024) | 32.282.622 | cross_year_mismatch | 2025 'năm trước'=32.282.622 ≠ 2024 'năm nay'=-95.017.737 (có thể do trình bày lại) |
| high | 2025 | - | tăng hàng tồn kho | Năm trước (vs 2024) | -95.017.737 | cross_year_mismatch | 2025 'năm trước'=-95.017.737 ≠ 2024 'năm nay'=-23.011.001 (có thể do trình bày lại) |
| high | 2025 | - | tiền lãi vay đã trả | Năm trước (vs 2024) | -450.000 | cross_year_mismatch | 2025 'năm trước'=-450.000 ≠ 2024 'năm nay'=-23.899.300 (có thể do trình bày lại) |
| high | 2025 | - | thuế thu nhập doanh nghiệp đ | Năm trước (vs 2024) | -23.899.300 | cross_year_mismatch | 2025 'năm trước'=-23.899.300 ≠ 2024 'năm nay'=-11.845.057 (có thể do trình bày lại) |
| high | 2025 | - | tiền và tương đương tiền cuố | Năm trước (vs 2024) | -338.021 | cross_year_mismatch | 2025 'năm trước'=-338.021 ≠ 2024 'năm nay'=42.582.366 (có thể do trình bày lại) |
| high | 2025 | 3 | 414 | cols 3,4 | 15.306.530 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 3 | 415 | cols 3,4 | -1.344.123 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 7 | 31 | Thuyết minh | 2.267.028 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2025 | 7 | 40 | Thuyết minh | (2.577.141) | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2025 | 7 | 50 | Thuyết minh | 101.619.123 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2025 | 7 | 60 | Thuyết minh | 30.935.609 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2025 | 7 | 61 | Thuyết minh | 42.582.366 | big_num_in_ref_col | cột Thuyết minh chứa số lớn → OCR điền nhầm ô |
| high | 2025 | 11 | 1 | cols 1,2 | 1.583.614 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 11 | 3 | cols 1,2 | 1.583.614 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 12 | 1 | cols 1,2 | 8.254.830 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 12 | 2 | cols 1,2 | 8.254.830 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 12 | 5 | cols 1,2 | 368.150 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 12 | 6 | cols 1,2 | 368.150 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 16 | 4 | cols 1,2 | 10.079.466 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 21 | 7 | cols 1,2 | 1.032.337 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 24 | 8 | cols 2,3 | 293.279 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 35 | 9 | cols 1,2 | 490.199 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 35 | 32 | cols 1,2 | 754.133 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 43 | 4 | cols 1,2 | 3.631.150 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 43 | 6 | cols 1,2 | 3.631.150 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 45 | 3 | cols 1,2 | -1.344.123 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 45 | 9 | cols 1,2 | 38.785.833 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 63 | 7 | cols 3,4 | 140.534 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 64 | 10 | cols 3,4 | 92.706 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| high | 2025 | 66 | 9 | cols 3,4 | 194.100 | adjacent_duplicate | hai ô số kề nhau trùng giá trị |
| low | 2021 | 10 | 1 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2021 | 41 | 12 | 3/6 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2021 | 41 | 13 | 3/6 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2022 | 9 | 32 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2022 | 9 | 33 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2022 | 9 | 34 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2022 | 9 | 35 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2022 | 9 | 36 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2022 | 9 | 37 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2022 | 9 | 38 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2022 | 30 | 11 | 8/10 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2022 | 56 | 2 | 3/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2022 | 56 | 6 | 2/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2022 | 56 | 11 | 3/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2022 | 56 | 16 | 2/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2022 | 56 | 18 | 2/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2022 | 61 | 4 | 3/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2022 | 61 | 7 | 3/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2022 | 71 | 2 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 9 | 40 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 9 | 50 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 9 | 60 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 9 | 61 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 27 | 17 | 9/11 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 34 | 3 | 2/3 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 34 | 4 | 2/3 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 34 | 5 | 2/3 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 34 | 6 | 2/3 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 34 | 10 | 2/3 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 34 | 14 | 2/3 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 39 | 11 | 3/6 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 39 | 12 | 3/6 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 41 | 1 | 9/10 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 41 | 2 | 9/10 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 57 | 8 | 3/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 70 | 3 | 8/10 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 70 | 4 | 9/10 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 53 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 54 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 55 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 56 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 57 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 58 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 59 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 60 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 61 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 62 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 72 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 73 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 74 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 75 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 76 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 77 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 78 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 79 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 80 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 81 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2023 | 79 | 82 | 7/8 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2024 | 7 | 40 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2024 | 7 | 50 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2024 | 7 | 60 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2024 | 7 | 61 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2024 | 41 | 11 | 3/6 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2024 | 58 | 4 | 2/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2024 | 58 | 5 | 2/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2024 | 61 | 10 | 3/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2024 | 63 | 10 | 3/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2025 | 7 | 40 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2025 | 7 | 50 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2025 | 7 | 60 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2025 | 7 | 61 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2025 | 43 | 4 | 3/6 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2025 | 43 | 6 | 3/6 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2025 | 43 | 8 | 3/6 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2025 | 43 | 9 | 3/6 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2025 | 43 | 10 | 3/6 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2025 | 43 | 12 | 3/6 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2025 | 48 | 2 | 4/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2025 | 62 | 1 | 3/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
| low | 2025 | 66 | 5 | 3/5 cols |  | ragged_row | số cột khác header → bảng có thể bị vỡ |
