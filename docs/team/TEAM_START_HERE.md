# D.0 → Implementation: HƯỚNG DẪN BÀN GIAO CHO NHÓM 4 NGƯỜI

**Ngày chốt:** 2026-10-23  | **Trạng thái:** Handoff v1; D.0 là design freeze candidate, không phải runtime hoàn chỉnh.  
**Dự án:** AI Agent phát hiện và ứng phó mã độc trên Windows (EMBER + LightGBM).  
**Đọc file này đầu tiên nếu hôm nay bạn không tham gia buổi thiết kế.**

## 0. Hiểu đúng tên gọi, tránh làm sai kiến trúc

- Tài liệu SoT cũ đặt tên các node **A–Z** theo nghiệp vụ: `D – Agent Planner`, `E – Executor/Tool Registry`, `G – Static PE`, `H – EMBER`, `I – LightGBM`... **Không xóa hay đổi các node nghiệp vụ cũ.**
- Tài liệu D.0 mới gọi **Node D (Trusted Tool Orchestrator)** theo *nhánh triển khai*, với module **D1–D9**. Hai hệ thống ký hiệu này KHÁC nhau: `D1` không phải `Node A`, và `D5` không phải static analyzer. Trong source code dùng `orchestrator/` cho D1–D9; `agent/` cho Planner; `analyzers/` cho static/dynamic/process.
- Workflow đã chốt: file **known** (reputation có provenance và còn hiệu lực) → assessment theo policy; file **unknown** → static PE + EMBER/LightGBM trước; dynamic **chỉ khi chưa đủ bằng chứng hoặc policy yêu cầu**, và chỉ trong Windows VM cô lập. Known malicious KHÔNG được chạy trên host.
- Agent hỗ trợ follow-up, xử lý conflict, dừng/escalate, đề xuất response; **workflow và policy** giữ các ràng buộc. Không external AI API. Orchestrator Python, adapter analyzer có thể viết Rust/C++/Go/Node với JSON contract.

## 1. Trước khi code: đọc đúng 3 lớp tài liệu

| Lớp | Đường dẫn | Cách dùng thực tế |
|---|---|---|
| Quyết định | `docs/d0/01_ARCHITECTURE_AND_ADRS.md` | Tìm lý do workflow, runtime, provider, approval |
| Contract | `docs/d0/02_CONTRACTS_AND_LIFECYCLE.md` | Tìm trạng thái, trường bắt buộc, lỗi và state machine |
| Bridge | `docs/d0/03_BC_V12_BRIDGE.md` | Bất cứ code nào chạm Node C phải đọc |
| REA | `docs/d0/04_REA_TRACEABILITY.md` | Chỉ rõ pattern tham khảo, không copy toàn bộ REA |
| Team | `docs/d0/05_TEAM_HANDOFF.md` | Owner, review gates, thứ tự sprint |
| Security/test | `docs/d0/06_SECURITY_AND_TEST_PLAN.md` | Threat model, baseline, test âm tính |
| Schema | `d0/schemas/*.schema.json` | Nguồn chính xác cho tên field và kiểu dữ liệu |
| Fixtures | `d0/fixtures/*.json` | Input/output giả lập; KHÔNG chứng minh runtime đã chạy |
| Tests | `tests/test_d0_contracts.py` | Test contract; bổ sung test riêng cho module |

**Quy tắc:** prose và code ví dụ trong tài liệu này chỉ mô tả ý định; nếu khác JSON Schema thì dừng và tạo issue/ADR, KHÔNG tự sửa schema. `d0/schemas/` phải được lead review. Không xem schema validation là authorization.

## 2. Luồng dữ liệu để tự tích hợp

`Node B Context Collector → Node C CaseState → Workflow/Agent tạo ToolCall → D2 registry → D3 validate → D4 policy → D8 approval khi cần → D5/D6 executor/control → D7 validate ToolResult → D8 attest → D9 Case Bridge → Node C cập nhật evidence → Agent/workflow tiếp tục`.

Các file chính: `tool_spec.schema.json`, `tool_call.schema.json`, `policy_decision.schema.json`, `execution_receipt.schema.json`, `tool_result.schema.json`, `approval_request.schema.json`, `approval_event.schema.json`, `workflow_decision.schema.json`. **Đọc đúng file schema trước khi đặt tên field**.

## 3. Bảng chia người: ai làm gì, giao đầu vào/đầu ra nào?

| Người | Độ khó | Module | Nhánh song song ngoài D | Reviewer / gate |
|---|---|---|---|---|
| **1 – Tech lead** | Cao nhất | D1 Core, D4 Policy, D8 Trust/Approval | Workflow Engine, Agent Decision Loop, security/E2E | Review mọi thay đổi schema, trust, host/VM execution |
| **2** | Cao thứ hai | D5 Executor, D6 Execution Control | Static PE, EMBER feature extraction, LightGBM scoring; VM adapter có giám sát | Lead review D5/D6 và VM isolation |
| **3** | Trung bình | D3 Input Validator, D7 Result Validator | Read-only process/DLL telemetry; normalize recorded sandbox | Lead + người 2 review provenance/untrusted data |
| **4** | Trung bình | D2 Registry, D9 Case Bridge | CLI case inspector, GUI tối thiểu sau core | Lead review Node C transaction/approval bridge |

**Không chia đều số lượng module.** Người 1 có trách nhiệm tích hợp; người 2 chịu lõi analyzer; người 3/4 có thể hoàn thành độc lập nhờ fixtures.

## 4. Quy trình 1 ticket: cách bắt đầu ngay hôm nay

1. Đọc `README_D0.md` → `01` → `02` → file ticket được giao. Nếu D9 đọc thêm `03`; nếu D4/D8 đọc thêm `06`.
2. Xem **schema đúng tên** trong `d0/schemas/`; mở fixture cùng tên trong `d0/fixtures/`. Không tự tạo field lạ.
3. Viết interface/mock trước; tạo unit tests với fixture hợp lệ, sai schema, timeout/unavailable (nếu phù hợp), case/target mismatch.
4. Triển khai module chỉ trong file ownership được giao. Mọi đổi schema → issue + ADR + lead duyệt trước khi merge.
5. Chạy `python -m unittest discover -s tests -p "test_d0*.py" -v` và unit tests mới; chạy B/C regression trên Windows.
6. PR phải ghi: ticket ID, schema version, file sửa, ví dụ input/output, test log, security caveats và checklist Definition of Done.

## 5. Thứ tự triển khai / song song

**Gate 0 (trước sprint):** D.0 merge vào main; cả nhóm chạy 21 contract tests và xác nhận có `bc_contracts.py` từ B/C v1.2. D.0 không phải production runtime.

**Sprint D.1 (song song):** người 1 D4 policy + D8 mock boundary + D1 skeleton; người 2 static ML adapter + D5 mock executor; người 3 D3 + D7; người 4 D2 + D9 compatibility skeleton. Tích hợp qua fixture/mock, chưa chạy malware thật.

**Sprint D.2:** người 1 D1 integration + workflow mock; người 2 D6 timeout/cancel + recorded telemetry/VM interface; người 3 process/DLL read-only + dynamic normalization; người 4 D9 audit ledger + CLI case view.

**Sprint D.3 (security gates):** D8 login/keys, D9 atomic revision inside case lock, real receipts/attestation, static E2E. Dynamic VM chỉ bật sau snapshot/restore, isolation, telemetry và reset test.

**Sprint D.4:** Windows regression, fault injection, E2E, fixed pipeline vs rule workflow vs AI Agent; đo FPR/F1/tool cost, không giả định Agent luôn tốt hơn.

## 6. Không được làm

- Không chạy unknown/malicious executable trên Windows host; không dùng Docker làm sandbox chính.
- Không cho Agent giữ HMAC key, tự xác thực approval, gọi shell hay sửa CaseState trực tiếp.
- Không silently fallback provider; một ToolRun pin `provider_id` và version.
- Không biến `UNKNOWN`, `UNAVAILABLE`, `FAILED`, `PARTIAL`, `TIMEOUT` thành benign/success.
- Không coi `receipt_sha256` là chữ ký; không coi snapshot check là atomic revision guard.
- Không đưa raw logs/strings của malware vào prompt như chỉ dẫn; phải đánh dấu untrusted và giữ raw artifact riêng.

## 7. Bridge Node C: rủi ro kỹ thuật cần nhớ

Node C v1.2 nhận tool name snake_case và chỉ hỗ trợ một số status. D9 phải map tool ID canonical sang legacy name (ví dụ `static.ember_features` → `static_ember_features`), giữ **bản gốc ToolResult + Receipt** trong audit ledger, rồi mới project dữ liệu vào Node C. `PARTIAL`→`DEGRADED`; `TIMEOUT/CANCELLED`→`FAILED` trong projection; `DENIED` không ghi thành ToolResult thành công. Trước D.3 phải bổ sung `expected_revision` **trong khóa của `case_manager.apply_update`**, không chỉ so sánh trước khi khóa. Những điều này là *implementation gaps*, chưa được D.0 giải quyết.

## 8. Cách tạo nhánh và PR

```powershell
# Sau khi D.0 đã merge vào main
git switch main
git pull --ff-only origin main
git switch -c feat/d2-tool-registry
# code + test, sau đó
git add orchestrator/registry.py tests/test_d2_registry.py
git commit -m "feat(d2): implement versioned tool registry"
git push -u origin feat/d2-tool-registry
```

Các nhánh khác: `feat/d1-d4-d8-core-policy-trust`, `feat/d5-d6-static-adapters`, `feat/d3-d7-validation`, `feat/d2-d9-registry-bridge`. Tách PR theo module khi có thể, tránh một PR khổng lồ.

## 9. Definition of Done (áp dụng cho mọi ticket)

- Interface, input/output, lỗi và ownership được ghi trong README/module docstring; schema hợp lệ và versioned.
- Có tests success + invalid input + negative security; test Windows thực khi phụ thuộc Windows.
- Không thay đổi D.0 contract không qua ADR; không có dữ liệu/hành vi được suy diễn thành thành công.
- PR có test log, ít nhất 1 người review; lead duyệt thay đổi ảnh hưởng trust boundary.
- Demo với fixture/recorded telemetry; ghi rõ phần nào mới là mock, phần nào đã chạy thật.

## 10. Liên kết nguồn tham khảo

REA: https://github.com/morluto/rea ; đối chiếu chi tiết trong `docs/d0/04_REA_TRACEABILITY.md`. D.0 chỉ tham khảo tool/provider/evidence/coverage/limitations/approval boundary; không nhập toàn bộ REA vào runtime.
