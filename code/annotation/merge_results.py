#!/usr/bin/env python3
"""
Step 3: Merge all worker results into a single annotated dataset.
Run this AFTER all 6 workers have completed.

Produces:
  - annotated_120k.jsonl  (full annotated dataset)
  - annotation_report.json (stats)
"""
import json
import os
from collections import Counter

# ============================================================
RESULTS_DIR = "results"
OUTPUT_FILE = "annotated_120k.jsonl"
REPORT_FILE = "annotation_report.json"
NUM_WORKERS = 6
# ============================================================

def main():
    all_results = []
    worker_stats = {}

    for w in range(NUM_WORKERS):
        path = os.path.join(RESULTS_DIR, f"worker_{w}.jsonl")
        if not os.path.exists(path):
            print(f"WARNING: {path} not found! Worker {w} incomplete?")
            continue

        records = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))

        errors = sum(1 for r in records if r.get("is_error"))
        avg_time = sum(r.get("call_time_s", 0) for r in records) / len(records) if records else 0

        worker_stats[f"worker_{w}"] = {
            "count": len(records),
            "errors": errors,
            "error_rate": round(errors / len(records) * 100, 2) if records else 0,
            "avg_call_time": round(avg_time, 2),
        }

        all_results.extend(records)
        print(f"Worker {w}: {len(records):,} sentences ({errors} errors)")

    # Sort by sentence_id to restore original order
    all_results.sort(key=lambda r: r.get("sentence_id", r.get("idx", 0)))

    # Remove duplicates (if any worker overlap)
    seen = set()
    deduped = []
    for r in all_results:
        key = r.get("sentence_id", r.get("idx"))
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    # Write merged output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in deduped:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Stats
    total = len(deduped)
    errors = sum(1 for r in deduped if r.get("is_error"))
    valid = total - errors
    changed = sum(1 for r in deduped if not r.get("is_error") and r["corrected"] != r["original"])

    report = {
        "total_sentences": total,
        "valid": valid,
        "errors": errors,
        "error_rate": round(errors / total * 100, 2) if total else 0,
        "changed": changed,
        "unchanged": valid - changed,
        "worker_stats": worker_stats,
    }

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n{'='*50}")
    print(f"MERGE COMPLETE")
    print(f"  Total: {total:,}")
    print(f"  Valid: {valid:,} ({valid/total*100:.1f}%)")
    print(f"  Errors: {errors:,} ({errors/total*100:.1f}%)")
    print(f"  Changed: {changed:,}")
    print(f"  Unchanged: {valid - changed:,}")
    print(f"\n  Output: {OUTPUT_FILE}")
    print(f"  Report: {REPORT_FILE}")
    print(f"{'='*50}")

    if errors > total * 0.05:
        print(f"\n⚠️  Error rate > 5%. Consider re-running failed sentences.")
        # Extract failed sentence IDs for re-run
        failed = [r for r in deduped if r.get("is_error")]
        failed_file = "failed_sentences.json"
        with open(failed_file, "w", encoding="utf-8") as f:
            json.dump([{"idx": r["idx"], "sentence_id": r["sentence_id"],
                        "original": r["original"], "worker": r["worker"]}
                       for r in failed], f, ensure_ascii=False, indent=1)
        print(f"  Failed sentences saved to: {failed_file}")
        print(f"  Re-run these with: python worker_retry.py")


if __name__ == "__main__":
    main()
