"""Generate redacted example investigation write-ups from completed samples.

One example per stratum (TP/TN/FP/FN/NEAR). SHA-256 is shortened; the evaluator-
only true label is NOT shown in the example (it is an agent-blind artifact). These
examples illustrate both branches side by side for the lecturer.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _example_md(row) -> str:
    sha = row["sha256"][:12] + "…"
    st = row["static"]["report"]
    ag = row["agent"]["report"]
    ass = ag.get("assessment") or {}
    L = []
    L.append(f"### Mẫu `{sha}` — strata {row['strata']}")
    L.append(f"- Nhãn tĩnh (LightGBM): **{row['predicted_label'].upper()}** "
             f"(score {row['score']:.4f})  ·  track FEATURE_RECORD_REPLAY")
    L.append("")
    L.append("**A. Static-only (baseline cố định):**")
    L.append(f"> {st['explanation']}")
    L.append(f"- Khuyến nghị: {st['recommendation']['action']} "
             f"(priority {st['recommendation']['priority']}, "
             f"execution_status {st['recommendation']['execution_status']})")
    L.append("")
    L.append("**B. Static + Agent (Qwen3.5-4B):**")
    if ass:
        L.append(f"- evidence_alignment: **{ass.get('evidence_alignment')}** · "
                 f"review_required: {ass.get('review_required')} · "
                 f"verdict riêng (phi thẩm quyền): {ass.get('agent_own_verdict')}")
        L.append(f"> {ass.get('explanation','')}")
        L.append(f"- Agent đề xuất: {ass.get('agent_recommendation')}")
    else:
        L.append(f"- Agent không tạo assessment hợp lệ (run_status={ag.get('run_status')}).")
    L.append(f"- Auto-check B: citation_validity={row['agent']['auto']['citation_validity']}, "
             f"unsupported_claim={row['agent']['auto']['unsupported_claim']}, "
             f"safety_violations={row['agent']['auto']['safety_violations']}")
    L.append("")
    return "\n".join(L)


def generate(out_dir: Path):
    samples_dir = out_dir / "samples"
    rows = [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(samples_dir.glob("*.json"))]
    by_stratum = {}
    for r in rows:
        for st in r["strata"]:
            by_stratum.setdefault(st, r)  # first per stratum
    parts = ["# Phiếu điều tra ví dụ (đã ẩn thông tin nhạy cảm)\n",
             "Mỗi strata một ví dụ; true label KHÔNG hiển thị (artifact ẩn với Agent).\n"]
    for st in ("TP", "TN", "FP", "FN", "NEAR"):
        if st in by_stratum:
            parts.append(_example_md(by_stratum[st]))
    (out_dir / "example_reports_redacted.md").write_text("\n".join(parts), encoding="utf-8")
    return len(by_stratum)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    n = generate(Path(args.out))
    print(f"wrote example_reports_redacted.md with {n} strata examples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
