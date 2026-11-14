# Đề xuất schema bổ sung: `static-prediction-v1` (CHƯA được owner duyệt)

> Trạng thái: **PROPOSED / additive**. Tài liệu này **không** thay đổi contract
> D0 `ember-output-v1` (vốn chỉ mô tả *feature extraction*, không có verdict).
> Đây là schema *mới, cộng thêm*, mô tả output của bước **prediction** để TASK
> 05B có thể đưa vào Node C kèm provenance. Cần project owner phê duyệt trước khi
> coi là chính thức.

## 1. Lý do

- `ember-output-v1` cố tình dừng ở vector 2381 chiều, không chứa model score hay
  nhãn. Đây là ranh giới kiến trúc đúng: feature extraction tách khỏi inference.
- TASK 05A tạo ra một bước *prediction* mới (LightGBM). Output của bước này cần
  một schema riêng, **cộng thêm**, không ghi đè contract cũ.

## 2. Nguyên tắc tương thích

1. Không sửa `ember-output-v1`. Prediction tiêu thụ output của extractor, không
   thay thế nó.
2. Không nới lỏng D4/D8 để test PASS. Prediction là một provider payload mới,
   phải đi qua D3 (validate schema) → D5 (execute) → D7 (normalize) như mọi tool.
3. Score thô của LightGBM **không** phải xác suất đã hiệu chỉnh (uncalibrated);
   schema ghi rõ `score_is_calibrated_probability: false`.

## 3. Payload đề xuất (provider payload, trước khi D7 bọc thành ToolResult)

```json
{
  "schema_version": "static-prediction-v1",
  "target_sha256": "<hex 64>",
  "feature_version": 2,
  "feature_count": 2381,
  "extractor": { "name": "dacn-independent-ember-v2", "version": "0.1.0",
                 "lief_version": "0.15.1" },
  "model_id": "dacn-lgbm-ember2018v2-<12 hex>",
  "model_sha256": "<hex 64>",
  "threshold": 0.8321860386013389,
  "raw_score": 0.0050861,
  "score_is_calibrated_probability": false,
  "predicted_label": "benign | malicious",
  "predicted_class": 0,
  "parser_status": "OK | PARSED_NULL | MALFORMED | ERROR",
  "limitations": ["..."],
  "error": null
}
```

## 4. Ràng buộc quan trọng

- `model_sha256` bắt buộc; D8 (integrity) có thể từ chối nếu digest không khớp
  manifest. CLI tham chiếu đã thực thi hành vi này (từ chối chấm điểm khi mismatch).
- `raw_score` là số thực; verdict dựa trên `threshold` được chọn trên tập
  validation (không phải test).
- Khi `parser_status != OK` hoặc không tạo được vector: `raw_score`/
  `predicted_label` = null, không bịa zero-vector.
- `feature_version`/`feature_count` phải khớp model; mismatch → từ chối, không
  đoán.

## 5. Chưa làm trong 05A (để 05B quyết định cùng owner)

- Ánh xạ sang Node C evidence/observation cụ thể và provenance chain đầy đủ.
- Calibration (nếu muốn xác suất thực) — chỉ fit trên tập không chồng lắp test.
- Chính sách D4 cho ngưỡng/ëscalation dựa trên score.
