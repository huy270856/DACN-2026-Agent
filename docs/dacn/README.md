# DACN — Unified Application CLI (`python -m dacn`)

Một entry point chung gọi trực tiếp API Python của **Node B** (Context Collector),
**Node C** (CaseState/CaseManager) và **Node D** (D1–D9 Orchestrator) — không tạo
subprocess riêng cho từng Node, không copy logic. Không thực thi target, không tích
hợp REA/Ghidra/EMBER/LightGBM/LLM.

## Yêu cầu
- Windows + Python 3.12 (intake/inspect chạy đa nền tảng; `smoke` cần Windows cho D5/D6).
- `pip install -r requirements.txt -r requirements-d0.txt` (psutil cho PID; jsonschema cho Node D).

## Lệnh

Chạy từ **repository root** (PowerShell):

```powershell
# 1) Thu thập context file + tạo case (Node B -> Node C)
python -m dacn intake --file "C:\samples\hello.exe"

# PID intake (kèm backing file tùy chọn)
python -m dacn intake --pid 1234
python -m dacn intake --pid 1234 --include-backing-file

# Nối một collection vào case đã có (Node C kiểm tra identity, từ chối target khác)
python -m dacn intake --file "C:\samples\hello.exe" --case-id CASE-<32hex>

# 2) Đọc lại CaseState/evidence/unknowns thật đã lưu (Node C)
python -m dacn inspect --case-id CASE-<32hex>

# 3) Khởi tạo + chạy D1–D9 thật với benign mock analyzer (Windows)
python -m dacn smoke
```

Storage root cấu hình được (mặc định `$DACN_HOME` hoặc `.\dacn_data`), đặt **trước** lệnh:

```powershell
python -m dacn --home "D:\dacn_store" intake --file "C:\samples\hello.exe"
```

## Output (JSON)
- `intake`: `case_id`, `sha256`, `format` (PE/UNKNOWN/UNSUPPORTED/MALFORMED), `identity_strength`,
  `collection_status`, `revision`, `case_action` (created/updated), đường dẫn case/context.
- `inspect`: `lifecycle_status`, `revision`, `target_ref`, `sha256`, `format`, danh sách `evidence`
  (kèm `trust_level=UNTRUSTED_CONTENT`), `residual_unknowns`.
- `smoke`: `supported`, `phase`, `outcome`, `run_id`, `d7_validated_and_d9_committed`, `signer`
  (TEST key, không phải production), `note`.

## Exit codes
`0` OK · `2` intake có collection_status FAILED (vd file không tồn tại) · `3` smoke unsupported
(không phải Windows) · `4` smoke chạy nhưng outcome không SUCCESS/PARTIAL · `5` lỗi ứng dụng (invalid
case id, target mismatch…).

## Bảo mật & giới hạn
- **Không thực thi** file người dùng đưa vào (Node B chỉ đọc nhị phân).
- `smoke` dùng **adapter/pins/policy/key cố định trong code**; CLI **không** cho truyền adapter command,
  executable path hay policy từ người dùng. Key = `InMemoryKeyProvider` (TEST), không đụng production key.
- Không hardcode đường dẫn máy cá nhân hay secret; storage qua `--home`/`$DACN_HOME`.
- `smoke`/Node D **chỉ Windows**; nền tảng khác báo `supported:false` (không giả PASS).
- Mock analyzer là lành tính — **không** chứng minh EMBER/LightGBM/Ghidra/REA đã hoạt động thật.

Sơ đồ kiến trúc: [ARCHITECTURE.md](ARCHITECTURE.md). Báo cáo test: [TEST_REPORT.md](TEST_REPORT.md).
