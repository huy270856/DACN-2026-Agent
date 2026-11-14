# Phiếu điều tra ví dụ (đã ẩn thông tin nhạy cảm)

Mỗi strata một ví dụ; true label KHÔNG hiển thị (artifact ẩn với Agent).

### Mẫu `062a293f9bd4…` — strata ['TP']
- Nhãn tĩnh (LightGBM): **MALICIOUS** (score 0.9984)  ·  track FEATURE_RECORD_REPLAY

**A. Static-only (baseline cố định):**
> Mô hình LightGBM (dacn-lgbm-ember2018v2-5db192ec1bda) phân loại tĩnh: MALICIOUS (raw score 0.9984 so với threshold 0.8322; score >= threshold ⇒ malicious). Raw score KHÔNG phải xác suất đã hiệu chỉnh. Quan sát tĩnh về sections: 4 section, 1 section entropy≥7 (có thể do nén/đóng gói), 0 section vừa ghi vừa thực thi. Imports tĩnh: 7 thư viện, 295 hàm import (khả năng tĩnh, không phải hành vi đã chạy). Chuỗi tĩnh: 0 lần khớp URL, 0 khớp khóa registry, 3 MZ nhúng (chỉ là chỉ dấu tĩnh).
- Khuyến nghị: CONSIDER_QUARANTINE (priority HIGH, execution_status NOT_EXECUTED)

**B. Static + Agent (Qwen3.5-4B):**
- evidence_alignment: **CONSISTENT** · review_required: True · verdict riêng (phi thẩm quyền): SUSPICIOUS
> The static prediction is authoritative and consistent with observable artifacts (high entropy sections, MFC imports). However, due to the replay nature of the model and lack of runtime data, a manual review or dynamic analysis is required to confirm actual malicious behavior.
- Agent đề xuất: MANUAL_REVIEW
- Auto-check B: citation_validity=1.0, unsupported_claim=False, safety_violations=[]

### Mẫu `05c55a9af4c8…` — strata ['TN']
- Nhãn tĩnh (LightGBM): **BENIGN** (score 0.0035)  ·  track FEATURE_RECORD_REPLAY

**A. Static-only (baseline cố định):**
> Mô hình LightGBM (dacn-lgbm-ember2018v2-5db192ec1bda) phân loại tĩnh: BENIGN (raw score 0.0035 so với threshold 0.8322; score >= threshold ⇒ malicious). Raw score KHÔNG phải xác suất đã hiệu chỉnh. Quan sát tĩnh về sections: 8 section, 0 section entropy≥7 (có thể do nén/đóng gói), 0 section vừa ghi vừa thực thi. Imports tĩnh: 61 thư viện, 2341 hàm import (khả năng tĩnh, không phải hành vi đã chạy). Chuỗi tĩnh: 16 lần khớp URL, 1 khớp khóa registry, 1 MZ nhúng (chỉ là chỉ dấu tĩnh).
- Khuyến nghị: MONITOR (priority LOW, execution_status NOT_EXECUTED)

**B. Static + Agent (Qwen3.5-4B):**
- evidence_alignment: **CONSISTENT** · review_required: True · verdict riêng (phi thẩm quyền): INSUFFICIENT_EVIDENCE
> While the static evidence strongly suggests benignity (low malware score, standard CRM imports/exports), a final decision requires runtime verification to rule out behavioral anomalies or obfuscation that static analysis cannot detect.
- Agent đề xuất: MONITOR
- Auto-check B: citation_validity=1.0, unsupported_claim=False, safety_violations=[]

### Mẫu `0e3de5e1f012…` — strata ['FP']
- Nhãn tĩnh (LightGBM): **MALICIOUS** (score 0.9486)  ·  track FEATURE_RECORD_REPLAY

**A. Static-only (baseline cố định):**
> Mô hình LightGBM (dacn-lgbm-ember2018v2-5db192ec1bda) phân loại tĩnh: MALICIOUS (raw score 0.9486 so với threshold 0.8322; score >= threshold ⇒ malicious). Raw score KHÔNG phải xác suất đã hiệu chỉnh. Quan sát tĩnh về sections: 5 section, 0 section entropy≥7 (có thể do nén/đóng gói), 0 section vừa ghi vừa thực thi. Imports tĩnh: 7 thư viện, 166 hàm import (khả năng tĩnh, không phải hành vi đã chạy). Chuỗi tĩnh: 0 lần khớp URL, 0 khớp khóa registry, 5 MZ nhúng (chỉ là chỉ dấu tĩnh).
- Khuyến nghị: CONSIDER_QUARANTINE (priority HIGH, execution_status NOT_EXECUTED)

**B. Static + Agent (Qwen3.5-4B):**
- evidence_alignment: **CONSISTENT** · review_required: True · verdict riêng (phi thẩm quyền): UNKNOWN
> While the static label strongly suggests malicious intent, the lack of a calibrated probability and the reliance on engineered features warrant monitoring rather than immediate quarantine or execution.
- Agent đề xuất: MONITOR
- Auto-check B: citation_validity=1.0, unsupported_claim=False, safety_violations=[]

### Mẫu `01358d1b4e7d…` — strata ['FN']
- Nhãn tĩnh (LightGBM): **BENIGN** (score 0.6319)  ·  track FEATURE_RECORD_REPLAY

**A. Static-only (baseline cố định):**
> Mô hình LightGBM (dacn-lgbm-ember2018v2-5db192ec1bda) phân loại tĩnh: BENIGN (raw score 0.6319 so với threshold 0.8322; score >= threshold ⇒ malicious). Raw score KHÔNG phải xác suất đã hiệu chỉnh. Quan sát tĩnh về sections: 6 section, 0 section entropy≥7 (có thể do nén/đóng gói), 0 section vừa ghi vừa thực thi. Imports tĩnh: 11 thư viện, 213 hàm import (khả năng tĩnh, không phải hành vi đã chạy). Chuỗi tĩnh: 1 lần khớp URL, 0 khớp khóa registry, 2 MZ nhúng (chỉ là chỉ dấu tĩnh).
- Khuyến nghị: MONITOR (priority LOW, execution_status NOT_EXECUTED)

**B. Static + Agent (Qwen3.5-4B):**
- evidence_alignment: **CONSISTENT** · review_required: True · verdict riêng (phi thẩm quyền): INSUFFICIENT_EVIDENCE
> The observable static evidence (imports, exports, entropy) is consistent with the benign prediction. However, due to the model's limitations and the uncalibrated score, we cannot definitively conclude safety without dynamic analysis.
- Agent đề xuất: MONITOR
- Auto-check B: citation_validity=1.0, unsupported_claim=False, safety_violations=[]

### Mẫu `083aa766fe16…` — strata ['NEAR']
- Nhãn tĩnh (LightGBM): **BENIGN** (score 0.8299)  ·  track FEATURE_RECORD_REPLAY

**A. Static-only (baseline cố định):**
> Mô hình LightGBM (dacn-lgbm-ember2018v2-5db192ec1bda) phân loại tĩnh: BENIGN (raw score 0.8299 so với threshold 0.8322; score >= threshold ⇒ malicious). Raw score KHÔNG phải xác suất đã hiệu chỉnh. Quan sát tĩnh về sections: 9 section, 1 section entropy≥7 (có thể do nén/đóng gói), 2 section vừa ghi vừa thực thi. Imports tĩnh: 3 thư viện, 431 hàm import (khả năng tĩnh, không phải hành vi đã chạy). Chuỗi tĩnh: 0 lần khớp URL, 0 khớp khóa registry, 1 MZ nhúng (chỉ là chỉ dấu tĩnh).
- Khuyến nghị: MANUAL_REVIEW (priority MEDIUM, execution_status NOT_EXECUTED)

**B. Static + Agent (Qwen3.5-4B):**
- evidence_alignment: **CONSISTENT** · review_required: True · verdict riêng (phi thẩm quyền): INSUFFICIENT_EVIDENCE
> The observable PE evidence aligns with the static benign label, but the model's limitations and lack of trusted reputation require continued monitoring rather than immediate trust or quarantine.
- Agent đề xuất: MONITOR
- Auto-check B: citation_validity=1.0, unsupported_claim=False, safety_violations=[]
