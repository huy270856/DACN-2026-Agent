# DACN Unified Application — Architecture

`dacn/` là lớp wiring mỏng. Nó **gọi trực tiếp** API thật của Node B/C/D, không
subprocess, không copy logic, không đổi contract. Node D (Windows-only) chỉ được
import **lazy** trong `smoke`.

## Thành phần

```
dacn/
├── __init__.py      # không side effect lúc import
├── __main__.py      # python -m dacn -> cli.main()
├── cli.py           # argparse: intake | inspect | smoke (+ validation, exit codes)
├── application.py   # wiring: gọi Node B/C/D; shape kết quả cho CLI
└── config.py        # AppConfig: storage roots (home/collections/cases/artifacts/ledgers)
```

## Luồng dữ liệu

```mermaid
flowchart TD
    U["python -m dacn (cli.py)"] --> A["application.py (wiring)"]

    subgraph intake
      A -->|collect_file_context / collect_process_context| B["Node B\ncontext_collector"]
      B -->|context + target_ref + facets| A
      A -->|build_case_state / save_case_state\nhoặc apply_update('collection')| C["Node C\ncase_state / case_manager"]
      C -->|case_id, revision| A
    end

    subgraph inspect
      A -->|case_path + read_json + validate_case| C
      C -->|CaseState, evidence, unknowns| A
    end

    subgraph smoke["smoke (Windows, benign mock)"]
      A -.lazy import.-> D["Node D\nOrchestrator (D1)"]
      D --> D2["D2 Registry"] --> D3["D3 InputValidator"]
      D3 --> D4["D4 PolicyEngine"] --> D8["D8 TrustedSigner (TEST key)"]
      D8 --> D5["D5/D6 Executor\n(benign mock adapter)"]
      D5 --> D7["D7 ResultValidator"] --> D9["D9 CaseBridge"]
      D9 -->|commit tool-result| C
    end

    A --> OUT["JSON summary"]
```

## Ranh giới & nguyên tắc
- **Node B → Node C**: context của Node B mang `target_ref` + facets (`sha256`,
  `format`, `file_identity`, …); `build_case_state` biến mỗi facet thành evidence
  (`trust_level=UNTRUSTED_CONTENT`). Không đổi schema TargetRef.
- **Node C revision**: tạo case (revision=1); `apply_update('collection')` tăng
  revision dưới lock và từ chối target đổi (chống TOCTOU).
- **Node D**: lắp D1–D9 từ public API thật; D4/D8 là implementation thật, D8 dùng
  `InMemoryKeyProvider` (TEST). Adapter/pins/policy cố định trong code — người dùng
  không truyền được. Không chạy file người dùng.
- **Platform**: `orchestrator.core`/`executor`/`provider_install` import lazy trong
  `smoke`; `intake`/`inspect` không phụ thuộc Windows executor.
```
