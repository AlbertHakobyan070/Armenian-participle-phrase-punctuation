#!/usr/bin/env python3
"""
Step 2: Annotation worker. Run one instance per chunk.
Usage:  python worker.py 0        (for chunk 0)
        python worker.py 1        (for chunk 1)
        ...etc

Each worker reads its chunk, calls Gemini Flash CoT, saves results to its own
checkpoint JSONL. Safe to interrupt with Ctrl+C and restart — resumes from
where it left off.

Run 3 workers per machine in 3 separate terminal windows:
  Mac:     python worker.py 0 &  python worker.py 1 &  python worker.py 2
  Windows: python worker.py 3    (in terminal 1)
           python worker.py 4    (in terminal 2)
           python worker.py 5    (in terminal 3)
"""
import json
import os
import re
import sys
import time

# ============================================================
# CONFIGURATION — EDIT THESE
# ============================================================
GEMINI_API_KEY = "YOUR_API_KEY_HERE"          # <-- PASTE YOUR KEY

CHUNKS_DIR = "chunks"                          # Where chunk_N.json files are
RESULTS_DIR = "results"                        # Where output goes
PROMPT_FILE = "MASTER_GEMINI_PROMPT_v3_1.md"   # Master prompt path

MODEL = "gemini-2.5-flash"
MAX_OUTPUT_TOKENS = 8192
API_DELAY = 1.2          # Seconds between calls (per worker)
RETRIES = 3               # Retry count on API failure
# ============================================================


def load_prompt():
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        return f.read()


def setup_sdk():
    """Auto-detect and configure Gemini SDK."""
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        return "NEW", client, None
    except ImportError:
        pass
    try:
        from google import generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        return "OLD", None, genai
    except ImportError:
        print("ERROR: No Gemini SDK found!")
        print("  pip install google-genai          (preferred)")
        print("  pip install google-generativeai   (alternative)")
        sys.exit(1)


def call_gemini(sdk_type, client, genai_mod, model, prompt, user_msg):
    """Call Gemini API with retries."""
    for attempt in range(RETRIES):
        try:
            if sdk_type == "NEW":
                response = client.models.generate_content(
                    model=model,
                    contents=[
                        {"role": "user", "parts": [{"text": prompt}]},
                        {"role": "model", "parts": [{"text": "Understood. Ready."}]},
                        {"role": "user", "parts": [{"text": user_msg}]},
                    ],
                    config={"temperature": 0, "max_output_tokens": MAX_OUTPUT_TOKENS},
                )
                return response.text or None
            else:
                model_obj = genai_mod.GenerativeModel(model)
                response = model_obj.generate_content(
                    [prompt, user_msg],
                    generation_config={
                        "temperature": 0,
                        "max_output_tokens": MAX_OUTPUT_TOKENS,
                    },
                )
                return response.text or None
        except Exception as e:
            if attempt < RETRIES - 1:
                wait = 3 * (attempt + 1)
                print(f" [retry {attempt+1}, wait {wait}s: {str(e)[:50]}]",
                      end="", flush=True)
                time.sleep(wait)
            else:
                print(f" [FAILED after {RETRIES} retries: {str(e)[:50]}]",
                      end="", flush=True)
                return None
    return None


def extract_corrected(xml_text):
    """Extract <corrected_sentence> from Gemini XML response."""
    if not xml_text:
        return "PARSE_ERROR"
    cleaned = xml_text.replace("```xml", "").replace("```", "")
    match = re.search(
        r"<corrected_sentence>(.*?)</corrected_sentence>",
        cleaned, re.DOTALL
    )
    if match:
        result = match.group(1).strip()
        if result == "NO_ACTION_NEEDED":
            return "NO_ACTION"
        return result
    return "PARSE_ERROR"


def build_user_message(sentence):
    return (
        f"MODE: STANDALONE\n\n"
        f"TASK: Correct the following Armenian sentence by applying ONLY "
        f"the participle punctuation rules.\n\n"
        f"SENTENCE: {sentence}\n\n"
        f"OUTPUT: Provide your analysis in the specified XML format."
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: python worker.py <chunk_id>")
        print("  chunk_id: 0-5 (Mac: 0,1,2  Windows: 3,4,5)")
        sys.exit(1)

    chunk_id = int(sys.argv[1])

    # Setup
    sdk_type, client, genai_mod = setup_sdk()
    prompt = load_prompt()
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # Load chunk
    chunk_file = os.path.join(CHUNKS_DIR, f"chunk_{chunk_id}.json")
    if not os.path.exists(chunk_file):
        print(f"ERROR: {chunk_file} not found!")
        sys.exit(1)

    with open(chunk_file, "r", encoding="utf-8") as f:
        chunk_data = json.load(f)

    print(f"Worker {chunk_id} | SDK: {sdk_type} | Model: {MODEL}")
    print(f"  Chunk: {len(chunk_data):,} sentences from {chunk_file}")

    # Load checkpoint (resume support)
    checkpoint_file = os.path.join(RESULTS_DIR, f"worker_{chunk_id}.jsonl")
    completed = set()
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    completed.add(rec.get("idx", rec.get("sentence_id", -1)))
        print(f"  Resuming: {len(completed)} already done")

    remaining = len(chunk_data) - len(completed)
    print(f"  Remaining: {remaining}")

    if remaining == 0:
        print("  Nothing to do — chunk complete!")
        return

    # Process
    start_time = time.time()
    errors = 0
    matches = 0
    processed = 0

    with open(checkpoint_file, "a", encoding="utf-8") as out_f:
        for idx, record in enumerate(chunk_data):
            if idx in completed:
                continue

            sentence = record["text"]
            sentence_id = record.get("sentence_id", idx)

            processed += 1
            total_done = len(completed) + processed
            print(f"  [{total_done}/{len(chunk_data)}] ", end="", flush=True)

            # Call Gemini
            user_msg = build_user_message(sentence)
            t0 = time.time()
            raw_response = call_gemini(
                sdk_type, client, genai_mod, MODEL, prompt, user_msg
            )
            call_time = time.time() - t0

            raw_response = raw_response or "API_ERROR: None"

            # Extract result
            corrected = extract_corrected(raw_response)
            is_error = corrected == "PARSE_ERROR" or raw_response.startswith("API_ERROR")

            if is_error:
                errors += 1

            # Build output record
            result = {
                "idx": idx,
                "sentence_id": sentence_id,
                "original": sentence,
                "corrected": corrected if corrected != "NO_ACTION" else sentence,
                "is_error": is_error,
                "call_time_s": round(call_time, 2),
                "raw_response_len": len(raw_response),
                "worker": chunk_id,
            }

            # Write to checkpoint
            out_f.write(json.dumps(result, ensure_ascii=False) + "\n")
            out_f.flush()

            # Status
            status = "⚠️" if is_error else "✓"
            print(f"{status} {call_time:.1f}s", flush=True)

            time.sleep(API_DELAY)

            # Progress report every 100 sentences
            if processed % 100 == 0:
                elapsed = time.time() - start_time
                rate = processed / elapsed * 3600
                eta_h = (remaining - processed) / rate if rate > 0 else 0
                err_pct = errors / processed * 100
                print(f"\n  --- Progress: {total_done}/{len(chunk_data)} | "
                      f"Rate: {rate:.0f}/h | ETA: {eta_h:.1f}h | "
                      f"Errors: {errors} ({err_pct:.1f}%) ---\n")

    # Final report
    elapsed = time.time() - start_time
    rate = processed / elapsed * 3600 if elapsed > 0 else 0
    print(f"\n{'='*50}")
    print(f"Worker {chunk_id} COMPLETE")
    print(f"  Processed: {processed}")
    print(f"  Errors: {errors} ({errors/processed*100:.1f}%)")
    print(f"  Time: {elapsed:.0f}s ({elapsed/3600:.1f}h)")
    print(f"  Rate: {rate:.0f} sentences/hour")
    print(f"  Output: {checkpoint_file}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
