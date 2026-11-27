# Báo cáo Day 14 — Dao Quang Tuan — 2A202603194


- Mã học viên dùng với `--student`: `194`
- `seed_tag` trong `frames_A.txt`: `393590736f`

## 1. Dự đoán trước sweep (bước 5b)

Ghi **trước** khi chạy `scripts/pp_sweep.py`, rồi commit và push ngay (lịch sử commit là bằng chứng thời điểm viết). Không sửa phần này sau khi có kết quả.

> **Trạng thái: học viên đã duyệt (2026-11-27).** Bản này do trợ lý AI (Claude Code) soạn theo yêu cầu của học viên, chỉ dựa trên `pred_A.json`, `ref_A.json` và ảnh BEV tập A ở cấu hình gốc, **trước khi** chạy `scripts/pp_sweep.py`. Học viên đã đọc và duyệt nội dung trước khi commit.

- Tham số tôi nghĩ giảm công sửa nhiều nhất: **`min_points`**, nâng lên khoảng **5** và giữ `score_thr` ở mức thấp (0.1–0.2). Dự đoán: nâng `score_thr` lên ≥ 0.3 sẽ làm **tăng** chi phí.
- Vì sao (nhìn ảnh BEV tập A: box thừa nhiều hay box sót nhiều?):
  - Cấu hình gốc: 7 box thừa (7 × 0.3 = 2.1) và 3 box sót (3 × 1.0 = 3.0), tổng 5.1. Box sót chiếm phần lớn chi phí, mà cả hai tham số chỉ **lọc bớt** box nên không thể giảm phần "thêm". Vì vậy sweep chỉ cắt được tối đa 2.1.
  - Score của 7 box thừa nằm trong khoảng 0.27–0.50, trộn lẫn với box đúng (trung vị score toàn bộ 87 box là 0.44). Có 14 box score < 0.3 nhưng chỉ 1 box trong đó là box thừa, nên `score_thr=0.3` có thể xóa nhầm khoảng 13 box đúng. Mỗi box đúng bị mất biến thành 1 lần "thêm" (1.0), đắt hơn hẳn 0.3 tiết kiệm được.
  - Hai box thừa ở s05f16 gần như không có điểm LiDAR: Car `pp_id` 25 (1 điểm, đè lên cabin xe ben) và Car `pp_id` 21 (2 điểm, trong bụi cây 47.9 m). `min_points=5` lọc được cả hai, dự kiến tiết kiệm khoảng 0.6. Trong tập A chỉ có 2 box dưới 5 điểm, nên ít rủi ro mất box đúng.
  - `min_points=10` rủi ro hơn: có 6 box dưới 10 điểm, trong đó 4 box không nằm trong danh sách box thừa (có thể là xe hoặc người ở xa).
  - Các box thừa còn lại không lọc được bằng hai tham số này: 2 box bao chính xe ghi dữ liệu (score 0.44–0.46, hơn 500 điểm) và Cyclist trên hàng rào / nhà chờ (86–188 điểm).
- Tác động dự kiến: chi phí tập A giảm từ 5.1 xuống khoảng **4.5** (khoảng −12%), không thể xuống dưới khoảng 3.0 vì 3 box sót (Bus, xe ben, Pedestrian) không phụ thuộc tham số lọc.
- Rủi ro: chỉ 3 frame tune, nên 2 box ít điểm ở một frame (s05f16) quyết định kết quả; leave-one-out có thể cho thấy cấu hình không ổn định. Ở tập B, người hoặc xe đạp ở xa có thể có dưới 5 điểm và bị lọc nhầm.

## 2. Tập A: sửa tay và tune

| Cấu hình | Xóa | Thêm | Sửa | Chi phí |
|---|---:|---:|---:|---:|
| Gốc | 7 | 3 | 0 | 5.1 |
| `best_config.json` | | | | |

Số đo gốc từ `scripts/pp_prelabel.py --frames d14_194/frames_A.txt --gt d14_194/ref_A.json`: GT 83, dự đoán 87, khớp 80 (s02f27: xóa 3 thêm 1 → 1.9; s03f31: xóa 1 thêm 1 → 1.3; s05f16: xóa 3 thêm 1 → 1.9).

- **3 box thêm:** Bus ở s03f31 và Truck (xe ben) ở s05f16, hai xe lớn model KITTI không phát hiện; Pedestrian ở nhà chờ xe buýt s02f27 (model đoán Cyclist `pp_id` 19 dài 2.13 m; box đúng chỉ 0.6 × 0.6 m nên BEV IoU < 0.3, scorer tính là 1 xóa + 1 thêm).
- **7 box xóa:** 2 box Car bao chính xe ghi dữ liệu (tâm cách LiDAR 0.3–0.4 m; `pp_id` 14 ở s02f27, `pp_id` 8 ở s03f31); Cyclist `pp_id` 26 trên hàng rào ở s02f27 (camera không có xe); Cyclist `pp_id` 19 nói trên; ở s05f16 có Car `pp_id` 25 đè lên cabin xe ben (1 điểm LiDAR trong hộp), Car `pp_id` 21 trong bụi cây cách 47.9 m (2 điểm) và Cyclist `pp_id` 16 cách 21.1 m.
- Box thừa (7 × 0.3 = 2.1) nhiều về số lượng, nhưng box sót (3 × 1.0 = 3.0) chiếm phần lớn chi phí.

- Tham số đã đổi trong `best_config.json`: ...
- Kết quả leave-one-out (dán các dòng `scripts/pp_sweep.py` in ra): ...
- Cấu hình có ổn định trên từng frame không? Vì sao tôi vẫn chọn (hoặc không chọn) nó: ...

## 3. Trước/sau (bước 8)

![so sánh](../../d14_194/compare/<frame>.jpg)

- `scripts/pp_compare.py` báo giảm (hoặc tăng) ...% công sửa trên tập A.
- Dự đoán ở mục 1 đúng hay sai? Giải thích bằng số box xóa/thêm/sửa: ...

## 4. Tập B

Số đo từ `scripts/pp_prelabel.py --frames d14_194/frames_B.txt --config d14_194/best_config.json --gt d14_194/ref_B.json`:

| Xóa | Thêm | Sửa | Chi phí |
|---:|---:|---:|---:|
| | | | |

- Loại box tốn công sửa nhất ở tập B: ...

## 5. Giới hạn

- **Chỉ 3 frame để tune.** Tập A có 83 box tham chiếu nhưng chỉ 10 thao tác xóa/thêm. Với ít lỗi như vậy, một box thay đổi cũng làm chi phí lệch rõ, nên cấu hình "tốt nhất" dễ overfit; cần đọc leave-one-out trước khi tin.
- **Model học trên KITTI** (LiDAR 64 tia, chỉ phía trước, 3 lớp Car/Pedestrian/Cyclist). Model không biết Truck/Bus: cả 2 box phải thêm ở tập A đều là xe lớn (Bus, xe ben). Luật đổi lớp theo kích thước không cứu được box mà model không phát hiện.
- **Chi phí là công thức** (`0.3·xóa + 1.0·thêm + 0.5·sửa`), không phải thời gian sửa thật, nên không quy ra "giờ công tiết kiệm".
- **Chỉ tính box trong 50 m** và ghép bằng BEV IoU ≥ 0.3. Vật ở xa hơn 50 m hoặc lệch ít hơn ngưỡng sửa (0.3 m, 0.2 m, 10°) không được tính.
- **`ref_*.json` là nhãn tôi tự sửa**, không phải ground truth chính thức. Một số vật ở xa, nhiều cây che (ví dụ một xe tải cách khoảng 49 m ở s05f16) khó xác định nên có thể còn sót.

> ✍️ Phần dưới là phụ lục kỹ thuật, lấy từ code và số đo thực tế. Ký hiệu ⏳ = chờ số đo; ✍️ = học viên tự viết/xác nhận.

## Phụ lục A. Pipeline

1. **Chọn frame:** `vf_cvat.py day14` sinh `frames_A.txt` (3 frame tune) và `frames_B.txt` (12 frame nộp) từ mã học viên `194` + SEED (`seed_tag=393590736f`). Không sửa tay.
2. **Model:** PointPillars pre-trained KITTI ([zhulf0804/PointPillars](https://github.com/zhulf0804/PointPillars) `620e6b0`), chạy CPU. Voxelize và rotated NMS là bản Python thuần (`vf_pp/upstream.py`).
3. **Đổi miền VF → KITTI:** `x_kitti = −y_vf`, `y_kitti = x_vf`. Model chỉ nhìn 90° phía trước nên mỗi frame chạy 4 lượt xoay (`passes=4`) để phủ 360°, rồi gộp bằng NMS (`merge_nms_thr`).
4. **Hậu xử lý:** lọc `score_thr`, `min_points`, `range_m=50`. Box Car dài/cao được đổi lớp thành Truck/Bus theo luật kích thước (`truck_l_min`, `bus_l_min`…).
5. **Sửa tay trên CVAT:** pre-label đưa lên task `D14-194-A/B` kèm thuộc tính `pp_id`, `score`, `warn`, `note`. Người gán nhãn xóa/thêm/sửa rồi Save. `vf_cvat.py reference` xuất `ref_*.json`.
6. **Tune:** `pp_sweep.py` grid `score_thr × min_points` trên tập A so với `ref_A.json`, kèm leave-one-out.
7. **Áp dụng:** `best_config.json` → `pred_B.json` → task B → sửa tay → `ref_B.json`.

Tái lập đã kiểm: chạy lại bước 2 trên tập A cho kết quả trùng khớp `pred_A.json`. Selftest `TẤT CẢ OK`. `pytest` (chạy lại 2026-11-27): 49/51 test pass; 2 test fail trong `tests/test_student_guide_deliverables.py` vì repo không còn file `RULES.md` (test kiểm tài liệu đề, không kiểm sản phẩm nộp).

## Phụ lục B. Phương pháp đo

- Chi phí sửa = `0.3·xóa + 1.0·thêm + 0.5·sửa`, chỉ tính box có tâm ≤ 50 m (BEV).
- Ghép pred–ref khi BEV IoU ≥ 0.3. Box đã ghép vẫn tính "sửa" nếu sai lớp, tâm lệch > 0.3 m, một kích thước lệch > 0.2 m hoặc phương trục dài lệch > 10° (coi 180° là cùng phương).
- `ref_*.json` là **nhãn tham chiếu do tôi sửa**, không phải ground truth chính thức. Chi phí là công thức, không phải thời gian sửa thật.

## Phụ lục C. Công cụ hỗ trợ ngoài pre-label của lab (khai báo)

✍️ Xác nhận công cụ nào bạn thực sự đã dùng, xóa dòng không dùng:

- `tools/d14_assist.py bev`: vẽ ảnh BEV có số `pp_id` và đánh dấu "M#" ở cụm điểm không có box (ứng viên bị sót). Chỉ là gợi ý. Mọi box đều do tôi xác nhận bằng camera rồi vẽ/sửa tay.
- `tools/d14_assist.py notes`: ghi gợi ý vào thuộc tính `note` của cuboid. Không đổi tọa độ, kích thước, lớp.
- `tools/d14_camserver.py` + `tools/cvat-d14-cameras.user.js`: chiếu cuboid đã Save lên 7 camera để kiểm. Chỉ đọc, không ghi nhãn.
- `tools/d14_draft.py`: tìm cụm điểm LiDAR chưa có box, chiếu lên camera để lọc. Trên tập A, 32 ứng viên chỉ có 1 vật thật (xe ben ở s05f16, cách 28.6 m); phần còn lại là nhà chờ, hàng cây, biển quảng cáo. Box này được đẩy lên CVAT dưới dạng nháp (`note = AI_DRAFT - can kiem`, lớp Truck). Tôi đã kiểm và chỉnh box này trên CVAT (dời tâm từ (10.91, −26.42) sang (11.61, −28.69), xoay yaw 1.452 → 1.560) rồi mới xuất `ref_A.json`.
- Kiểm tra QA tự động trên tập A (Claude Code): so kích thước với Bảng 4.3, đếm điểm LiDAR trong hộp, chiếu hộp nghi vấn lên camera. Theo yêu cầu của tôi, công cụ đã sửa trực tiếp trên CVAT 4 lỗi thấy rõ trên camera: xóa box Car bao chính xe ghi dữ liệu (s03f31), xóa box Car trong bụi cây cách 47.9 m (s05f16), xóa box Car trùng cabin xe ben (s05f16), đổi chiều rộng Bus từ 3.11 m thành 2.55 m (s03f31). Lần 2 sửa thêm 2 box ở s02f27: xóa Cyclist trên hàng rào (camera không có xe), thu Pedestrian ở nhà chờ từ 2.13 m xuống 0.6 × 0.6 × 1.7 m theo cụm điểm của người và hạ đáy sát mặt đường. Đã sao lưu trước mỗi lần sửa (`out/cvat_backup_D14-194-A_truoc_suaQA*_*.json`). ✍️ Tôi đã mở CVAT kiểm lại các thay đổi này.
- Trợ lý AI (Claude Code): chạy lệnh, kiểm tra CVAT/dữ liệu, sửa một phần nhãn tập A qua API theo yêu cầu của tôi (liệt kê đầy đủ ở hai dòng trên), điền bảng số liệu, viết mục 5 và các phụ lục kỹ thuật. Dự đoán 5b và kết luận đối chiếu ở mục 3 do tôi tự viết.

## Phụ lục D. Bảng so sánh A/B

| Tập | Cấu hình | GT (ref) | Pred | Khớp | Xóa | Thêm | Sửa | Chi phí |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A | Gốc | 83 | 87 | 80 | 7 | 3 | 0 | 5.1 |
| A | `best_config.json` | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| B | `best_config.json` | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

Phân tích sai số theo lớp (box thêm/sửa nhiều nhất là Truck/Bus, Pedestrian hay Cyclist?): ⏳
