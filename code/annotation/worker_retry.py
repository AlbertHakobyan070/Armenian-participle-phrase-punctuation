#!/usr/bin/env python3
"""
Step 3b: Re-run failed sentences (those that got PARSE_ERROR or API_ERROR).
Run this AFTER merge_results.py if error rate > 5%.
"""
import json
import os
import re
import sys
import time

# ============================================================
GEMINI_API_KEY = "YOUR_API_KEY_HERE"
FAILED_FILE = "failed_sentences.json"
PROMPT_FILE = "MASTER_GEMINI_PROMPT_v3_1.md"
OUTPUT_FILE = "retry_results.jsonl"
MODEL = "gemini-2.5-flash"
MAX_OUTPUT_TOKENS = 8192
API_DELAY = 2.0  # Slightly slower to avoid rate limits
RETRIES = 5       # More retries for previously-failed sentences
# ============================================================

def setup_sdk():
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        return "NEW", client, None
    except ImportError:
        from google import generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        return "OLD", None, genai

def call_gemini(sdk_type, client, genai_mod, prompt, user_msg):
    for attempt in range(RETRIES):
        try:
            if sdk_type == "NEW":
                r = client.models.generate_content(
                    model=MODEL,
                    contents=[
                        {"role": "user", "parts": [{"text": prompt}]},
                        {"role": "model", "parts": [{"text": "Understood. Ready."}]},
                        {"role": "user", "parts": [{"text": user_msg}]},
                    ],
                    config={"temperature": 0, "max_output_tokens": MAX_OUTPUT_TOKENS},
                )
                return r.text or None
            else:
                mo = genai_mod.GenerativeModel(MODEL)
                r = mo.generate_content([prompt, user_msg],
                    generation_config={"temperature": 0, "max_output_tokens": MAX_OUTPUT_TOKENS})
                return r.text or None
        except Exception as e:
            wait = 5 * (attempt + 1)
            print(f"  retry {attempt+1}/{RETRIES}: {str(e)[:40]}, wait {wait}s")
            time.sleep(wait)
    return None

def extract_corrected(xml_text):
    if not xml_text: return "PARSE_ERROR"
    cleaned = xml_text.replace("```xml","").replace("```","")
    m = re.search(r"<corrected_sentence>(.*?)</corrected_sentence>", cleaned, re.DOTALL)
    if m:
        r = m.group(1).strip()
        return r if r != "NO_ACTION_NEEDED" else "NO_ACTION"
    return "PARSE_ERROR"

def main():
    if not os.path.exists(FAILED_FILE):
        print(f"No {FAILED_FILE} found. Nothing to retry.")
        return

    with open(FAILED_FILE, "r", encoding="utf-8") as f:
        failed = json.load(f)
    print(f"Retrying {len(failed)} failed sentences...")

    sdk_type, client, genai_mod = setup_sdk()
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        prompt = f.read()

    # Load already-retried
    done = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    done.add(json.loads(line).get("sentence_id"))

    fixed = 0
    still_broken = 0

    with open(OUTPUT_FILE, "a", encoding="utf-8") as out:
        for i, rec in enumerate(failed):
            sid = rec["sentence_id"]
            if sid in done: continue

            print(f"  [{i+1}/{len(failed)}] sid={sid} ", end="", flush=True)
            user_msg = (
                f"MODE: STANDALONE\n\n"
                f"TASK: Correct the following Armenian sentence by applying ONLY "
                f"the participle punctuation rules.\n\n"
                f"SENTENCE: {rec['original']}\n\n"
                f"OUTPUT: Provide your analysis in the specified XML format."
            )

            raw = call_gemini(sdk_type, client, genai_mod, prompt, user_msg)
            raw = raw or "API_ERROR: None"
            corrected = extract_corrected(raw)
            is_error = corrected == "PARSE_ERROR" or raw.startswith("API_ERROR")

            result = {
                "idx": rec["idx"],
                "sentence_id": sid,
                "original": rec["original"],
                "corrected": corrected if corrected != "NO_ACTION" else rec["original"],
                "is_error": is_error,
                "worker": "retry",
            }
            out.write(json.dumps(result, ensure_ascii=False) + "\n")
            out.flush()

            if is_error:
                still_broken += 1
                print("⚠️")
            else:
                fixed += 1
                print("✓")

            time.sleep(API_DELAY)

    print(f"\nRetry complete: {fixed} fixed, {still_broken} still broken")
    print(f"Now re-run merge_results.py to incorporate retry results.")

if __name__ == "__main__":
    main()
