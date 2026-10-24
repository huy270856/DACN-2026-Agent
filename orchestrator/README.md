# D3 và D7 của Tuấn

Triển khai theo ticket D3-01/D7-01 và gói nhóm cung cấp
`DACN_D0_REA_informed_v1_1_EMBER.zip`, bản cập nhật ngày 24/10/2026.
Các schema/fixture EMBER và thay đổi `d0/validate.py` được lấy nguyên từ ZIP.
Contract này là đề xuất nội bộ của nhóm, không phải schema do upstream EMBER cung cấp.
Lead vẫn review contract và PR theo quy trình của nhóm.

## D3: kiểm tra yêu cầu trước khi chạy

```python
from orchestrator.input_validator import validate_tool_call, ValidationError

candidate = validate_tool_call(call, spec, case_snapshot)
```

- `call`: ToolCall theo `tool_call.schema.json`.
- `spec`: ToolSpec do D2 cung cấp; `None` nghĩa là tool không tồn tại.
- `case_snapshot`: có `case_id`, `revision`, `target_ref` từ B/C.
- Kết quả là bản sao yêu cầu hợp lệ; lỗi là `ValidationError` có `code`, `message`, `call_id`.
- `provider_available` do D2 cung cấp, không lấy từ Agent.
- Mặc định dùng schema trong `d0/schemas`; có thể truyền `input_schemas` từ catalog tin cậy để test tool khác.

D3 kiểm tra schema, tool/provider/version, target, case/revision và budget.
Riêng EMBER, `ember-input-v1` áp dụng cho `call['arguments']`:

```json
{"feature_version": 2}
```

`include_feature_vector: true` cũng hợp lệ. Bỏ field này có nghĩa là dùng mặc định
true nhưng D3 không tự thêm field vào call, tránh làm thay đổi digest arguments.
`false` bị từ chối theo README của patch vì nhánh bỏ vector chưa được thiết kế.

Call hợp lệ chưa phải quyền chạy: D4 xét policy, D1/D9 kiểm tra revision atomically,
D5 xác minh file/process thực tế trước khi chạy. Không coi snapshot là khóa giao dịch.

## D7: kiểm tra payload rồi đóng gói kết quả

```python
from orchestrator.result_validator import normalize_ember_result, ResultValidationError

result = normalize_ember_result(provider_payload, receipt, call, spec)
```

Đây là hàm dùng khi tích hợp EMBER. `provider_payload` phải có:
`schema_version`, `feature_version`, `extractor`, `target_sha256`, `feature_count`,
`features`; `warnings` là tùy chọn. Hàm kiểm tra:

- Payload theo `ember-output-v1`, version 2, đủ 2381 số hữu hạn.
- SHA-256 khớp cả target trong call và target D5/D6 đã xác minh trong receipt.
- Call/receipt/tool/provider/version và budget nhất quán.
- Sau đó tạo ToolResult theo `tool_result.schema.json` và kiểm tra lại envelope.

Toàn bộ payload được giữ trong observation facet `static.ember_features`:
`SUCCESS`, `COMPLETE`, `provider_output`, `UNTRUSTED_CONTENT`.
Extractor version, hash, vector và warnings được giữ nguyên. Warnings không rỗng
được đưa thêm vào limitations. COMPLETE ở đây chỉ nói về payload trích xuất,
không khẳng định đã quan sát mọi hành vi của file hay file là benign.

Khi extraction thất bại, gọi với `provider_payload=None` và lỗi từ D5/D6:

```python
result = normalize_ember_result(
    None, receipt, call, spec,
    error={"code": "timeout", "message": "Extraction timed out"},
)
```

`receipt['outcome']` phải phản ánh trạng thái thật. FAILED/TIMEOUT/CANCELLED/DENIED
phải có error và không được kèm payload thành công. Không tạo vector toàn số 0 để
thay kết quả lỗi. PARTIAL có thể giữ một extraction đã hoàn tất với target đã xác minh.
Mã lỗi exception nội bộ viết hoa; mã lỗi trên ToolResult dùng chữ thường theo schema.

`validate_tool_result(...)` là hàm cấp thấp để kiểm tra D.0 envelope/artifacts.
Hàm này không thay thế `normalize_ember_result` và không tự kiểm tra raw payload
theo output schema. Các test envelope cũ chỉ kiểm tra tầng này.

## Giới hạn dung lượng và artifacts

Payload JSON canonical phải nằm trong `call.budget.max_output_bytes` và giới hạn
của ToolSpec. Không tự tăng budget và không dùng artifact để vượt cap của provider.
Nếu payload hợp lệ nhưng việc thêm envelope làm kết quả quá lớn, D7 có thể chuyển
payload sang artifact qua hai callback do kho lưu trữ tin cậy cung cấp:

- `artifact_writer(bytes) -> artifact reference` theo schema artifact.
- `artifact_reader(reference) -> bytes` để kiểm tra lại kích thước/hash/nội dung.

Giá trị inline trở thành null, toàn bộ payload ở `artifact_ref`; provenance,
coverage và limitations được giữ. Thiếu kho lưu trữ thì báo lỗi, không bỏ vector.
Đây vẫn là provider payload đầy đủ, không phải hỗ trợ `include_feature_vector=false`.

D7 kiểm tra đường dẫn tương đối và digest. Kho thật phải kiểm soát root theo case,
ACL, symlink/reparse, atomic writes và thu gom artifact không được commit sau lỗi.
Callback test dùng dictionary trong bộ nhớ; chưa phải kho lưu trữ production.
D8 xác thực/ký và D9 commit/audit vẫn là trách nhiệm riêng. Receipt digest không phải chữ ký.

## Kiểm thử

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Đã xác minh ngày 24/10/2026: 101 test trong `tests/` PASS.
Regression toàn repo bằng `.venv` có dependency B/C `psutil==7.2.2`:
197 test, 195 PASS và 2 skipped, không có failure/error.
Chạy lại toàn bộ trên Windows bằng:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
```

- `test_d0_contracts.py`: contract nền của nhóm.
- `test_ember_contracts.py`: tests nguyên bản từ gói EMBER.
- `test_d3_input_validator.py`: D3 chung và arguments EMBER thật.
- `test_d7_result_validator.py`: envelope, lỗi, provenance và artifacts.
- `test_d7_ember_normalization.py`: payload EMBER, liên kết hash, chuẩn hóa,
  failure/partial, budget, artifact và luồng D3 → D7 dùng fixture.

Output EMBER mẫu toàn số 0 là dữ liệu tổng hợp để kiểm thử contract.
Call mẫu cũ có budget 4096 bytes và receipt 128 bytes chỉ phù hợp ví dụ đếm features.
Test payload đầy đủ tạo bản sao call với budget 32768 bytes (dưới ToolSpec 65536)
và receipt mô phỏng tương ứng; không thay fixture gốc, không sửa receipt ở runtime.

Trước khi tích hợp thật: Huy xác nhận extractor EMBER v2 có đúng 2381 đặc trưng,
thứ tự/version phù hợp và D5 cung cấp hash đã xác minh. Nhóm nối kho artifact thật,
D8/D9 và kiểm thử tích hợp. LightGBM inference cần contract riêng; D7 này không
đưa ra score hay kết luận mã độc.
