# Pilot blind grading (20 mẫu)

- Cân đối theo strata (ẩn với người chấm); không có ground truth / nhãn / nhánh.
- Mở `evaluation/task05d/ui/grading.html` trong trình duyệt, nạp `annotation_forms_blind_v2.json`, nhập Reviewer ID, chấm 0/1/2, rồi Xuất JSON.
- Tổng hợp: `python -m evaluation.task05d.grading_import --annotations <các file> --forms annotation_forms_blind_v2.json --out aggregate.json`.
- Không tự điền điểm; cần >=2 người chấm để tính inter-rater.
