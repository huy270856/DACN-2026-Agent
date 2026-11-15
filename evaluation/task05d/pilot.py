"""Build a small strata-balanced pilot blind grading package from locked 05C data.

Selects N_PER_STRATUM distinct samples per stratum (TP/TN/FP/FN/NEAR) using the
evaluator-only audit manifest, then regenerates blind forms (annotation v2) for just
those samples. Strata are NEVER written into the grader-facing forms. No scores are
filled. Reuses the frozen 05C samples/records; no Qwen re-run.
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from evaluation.task05c.repair import annotation_v2
from evaluation.task05c.rubric import rubric_version


def rubric_id():
    return rubric_version()["rubric_id"]


STRATA = ("TP", "TN", "FP", "FN", "NEAR")


def select_balanced(manifest, n_per=4):
    chosen, used = [], set()
    for st in STRATA:
        picked = 0
        for s in sorted(manifest["audit_samples"], key=lambda r: r["sha256"]):
            if picked >= n_per:
                break
            if st in s["strata"] and s["sha256"] not in used:
                used.add(s["sha256"]); chosen.append(s["sha256"]); picked += 1
    return chosen


def build(audit_manifest: Path, samples_dir: Path, records_cache: Path, out_dir: Path, n_per=4):
    manifest = json.loads(audit_manifest.read_text(encoding="utf-8"))
    shas = select_balanced(manifest, n_per=n_per)

    tmp = Path(tempfile.mkdtemp(prefix="pilot_samples_"))
    try:
        for sha in shas:
            src = samples_dir / f"{sha}.json"
            if src.exists():
                shutil.copy(src, tmp / f"{sha}.json")
        annotation_v2.generate(tmp, records_cache, out_dir)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Inject rubric_version so the UI/export captures it; strata NOT written.
    forms_path = out_dir / "annotation_forms_blind_v2.json"
    data = json.loads(forms_path.read_text(encoding="utf-8"))
    data = {"rubric_version": rubric_id(), **data}
    forms_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "PILOT_README.md").write_text(
        f"# Pilot blind grading ({len(shas)} mẫu)\n\n"
        "- Cân đối theo strata (ẩn với người chấm); không có ground truth / nhãn / nhánh.\n"
        "- Mở `evaluation/task05d/ui/grading.html` trong trình duyệt, nạp "
        "`annotation_forms_blind_v2.json`, nhập Reviewer ID, chấm 0/1/2, rồi Xuất JSON.\n"
        "- Tổng hợp: `python -m evaluation.task05d.grading_import --annotations <các file> "
        "--forms annotation_forms_blind_v2.json --out aggregate.json`.\n"
        "- Không tự điền điểm; cần >=2 người chấm để tính inter-rater.\n", encoding="utf-8")
    return {"n_selected": len(shas), "selected_sha_prefixes": [s[:12] for s in shas]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build pilot blind grading package")
    ap.add_argument("--audit-manifest", required=True)
    ap.add_argument("--samples", required=True)
    ap.add_argument("--records-cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-per", type=int, default=4)
    args = ap.parse_args(argv)
    res = build(Path(args.audit_manifest), Path(args.samples), Path(args.records_cache),
                Path(args.out), n_per=args.n_per)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
