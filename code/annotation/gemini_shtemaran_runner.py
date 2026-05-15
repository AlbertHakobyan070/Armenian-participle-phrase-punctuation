#!/usr/bin/env python3
"""
gemini_shtemaran_runner.py — Zero-shot Gemini 2.5 Flash on Shtemaran 292

SETUP (paid tier, < $0.50 total):
  1. console.cloud.google.com -> NLP project -> Billing -> Link account
  2. APIs & Services -> enable "Generative Language API"

USAGE:
  python gemini_shtemaran_runner.py --api-key YOUR_KEY

  If interrupted, just re-run — auto-resumes from checkpoint.

INPUT:  ./Data Full/shtemaran_292_benchmark.jsonl
OUTPUT: ./Data Full/shtemaran_gemini_results.json
"""

import json
import os
import sys
import time
import argparse
import urllib.request
import urllib.error
from pathlib import Path

INPUT_JSONL = Path("./Data Full/shtemaran_292_benchmark.jsonl")
OUTPUT_JSON = Path("./Data Full/shtemaran_gemini_results.json")
MODEL       = "gemini-2.5-flash"
DELAY       = 10.0

# ── Zero-shot prompt (Armenian characters written directly) ───
PROMPT = (
    "You are an Armenian language expert. Your task is to correct ONLY the "
    "punctuation related to participle phrases (participial constructions "
    "ending in -լով or -ած) in the given Armenian sentence.\n\n"
    "Think step by step:\n"
    "1. Identify all participle verb forms (words ending in -լով or "
    "-ած that are VERBS, not nouns).\n"
    "2. Determine if each participle has dependent words (additives/objects).\n"
    "3. Determine the position of the participle phrase relative to the main "
    "verb (before, within, or after).\n"
    "4. Apply the correct punctuation:\n"
    "   - Commas (,) for INTRAPOSITION (participle phrase between subject and verb)\n"
    "   - \u0532\u0578\u0582\u0569 (՝) for PREPOSITION (before main clause) "
    "and POSTPOSITION (after main clause)\n"
    "5. Do NOT change any other punctuation, words, or spelling.\n"
    "6. Lone participles (no dependent words) get NO punctuation.\n\n"
    "Output ONLY the corrected sentence. No explanations."
)


def call_gemini(sentence, api_key, max_retries=5):
    url = (f"https://generativelanguage.googleapis.com/v1beta/"
           f"models/{MODEL}:generateContent?key={api_key}")

    payload = {
        "contents": [{
            "parts": [{"text": f"{PROMPT}\n\nSENTENCE: {sentence}"}]
        }],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 2048,
            "thinkingConfig": {"thinkingBudget": 2048}
        }
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"})

    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            candidates = result.get("candidates", [])
            if not candidates:
                return None, "no_candidates"

            parts = candidates[0].get("content", {}).get("parts", [])
            text_parts = [p["text"] for p in parts
                         if "text" in p and not p.get("thought")]
            if text_parts:
                return text_parts[-1].strip(), None
            for p in parts:
                if "text" in p:
                    return p["text"].strip(), None
            return None, "no_text_in_response"

        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            if e.code == 429:
                wait = min(15 * (2 ** attempt), 300)
                print(f"    429 rate limited (attempt {attempt+1}/{max_retries}). "
                      f"Waiting {wait}s...")
                time.sleep(wait)
            elif e.code == 503:
                wait = 20 * (attempt + 1)
                print(f"    503 unavailable. Waiting {wait}s...")
                time.sleep(wait)
            elif e.code == 403:
                print(f"    403 FORBIDDEN: {body}")
                return None, f"forbidden_403: {body}"
            else:
                print(f"    HTTP {e.code}: {body}")
                return None, f"http_{e.code}: {body}"
        except urllib.error.URLError as e:
            wait = 10 * (attempt + 1)
            print(f"    Connection error: {e.reason}. Waiting {wait}s...")
            time.sleep(wait)
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                return None, str(e)

    return None, "max_retries_exceeded"


def save_results(results, path):
    tmp = Path(str(path) + ".tmp")
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--input", default=str(INPUT_JSONL))
    parser.add_argument("--output", default=str(OUTPUT_JSON))
    parser.add_argument("--delay", type=float, default=DELAY)
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: No API key.")
        print("  python gemini_shtemaran_runner.py --api-key YOUR_KEY")
        sys.exit(1)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: {input_path} not found. Run Step 3 of the notebook first.")
        sys.exit(1)

    sentences = []
    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                sentences.append(json.loads(line))
    print(f"Loaded {len(sentences)} sentences")

    output_path = Path(args.output)
    results = {}
    if output_path.exists():
        with open(output_path, 'r', encoding='utf-8') as f:
            results = json.load(f)
        if results:
            print(f"Auto-resuming: {len(results)} already done")

    total = len(sentences)
    to_do = sum(1 for s in sentences if str(s["id"]) not in results)
    errors, consecutive_errors = 0, 0
    t0 = time.time()

    if to_do == 0:
        print(f"All {total} done! Output: {output_path}")
        return

    print(f"\n{to_do} remaining, ~{to_do * args.delay / 60:.0f} min\n")

    processed = 0
    for rec in sentences:
        sid = str(rec["id"])
        if sid in results:
            continue

        result, error = call_gemini(rec["original"], api_key)
        if result:
            results[sid] = result
            consecutive_errors = 0
        else:
            errors += 1
            consecutive_errors += 1
            results[sid] = rec["original"]
            print(f"  [{len(results)}/{total}] ERROR id={sid}: {error}")
            if consecutive_errors >= 5:
                print(f"\n!!! 5 consecutive errors. Saving and stopping.")
                save_results(results, output_path)
                sys.exit(1)

        processed += 1
        if processed % 10 == 0 or len(results) == total:
            elapsed = time.time() - t0
            remaining = total - len(results)
            rate = processed / elapsed if elapsed > 0 else 1
            print(f"  [{len(results)}/{total}] {elapsed:.0f}s, "
                  f"~{remaining / rate:.0f}s left, {errors} err")
        if processed % 20 == 0:
            save_results(results, output_path)
        if total - len(results) > 0:
            time.sleep(args.delay)

    save_results(results, output_path)
    elapsed = time.time() - t0
    print(f"\nDONE in {elapsed/60:.1f} min. {len(results)}/{total}, {errors} errors")
    print(f"Output: {output_path}")
    print(f"\nNext: open eval_shtemaran_292.ipynb, run from Step 6")


if __name__ == "__main__":
    main()
