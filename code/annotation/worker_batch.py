#!/usr/bin/env python3
"""
BATCHED Annotation Worker — Harmonized with Master Prompt v3.1
"""
import json
import os
import re
import sys
import time
from datetime import datetime

# ============================================================
# CONFIGURATION — EDIT THESE
# ============================================================
GEMINI_API_KEY = "YOUR_API_KEY_HERE"

CHUNKS_DIR = "chunks"
RESULTS_DIR = "results"
PROMPT_FILE = "MASTER_GEMINI_PROMPT_v3_1.md"

MODEL = "gemini-2.5-flash"
BATCH_SIZE = 3           
MAX_OUTPUT_TOKENS = 8192  # Increased slightly to accommodate 10 full CoT blocks
API_DELAY = 2.0           
RETRIES = 5
DAILY_LIMIT = 9500        
# ============================================================

def load_prompt():
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        return f.read()

def setup_sdk():
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
        print("ERROR: No Gemini SDK found! pip install google-genai")
        sys.exit(1)

def call_gemini(sdk_type, client, genai_mod, prompt, user_msg):
    for attempt in range(RETRIES):
        try:
            if sdk_type == "NEW":
                response = client.models.generate_content(
                    model=MODEL,
                    contents=[
                        {"role": "user", "parts": [{"text": prompt}]},
                        # ALIGNED WITH MASTER PROMPT:
                        {"role": "model", "parts": [{"text": "Understood. I will process the batch and output a complete <participle_correction> XML block for EACH sentence in the exact order they are provided."}]},
                        {"role": "user", "parts": [{"text": user_msg}]},
                    ],
                    config={"temperature": 0, "max_output_tokens": MAX_OUTPUT_TOKENS},
                )
                return response.text or None
            else:
                model_obj = genai_mod.GenerativeModel(MODEL)
                response = model_obj.generate_content(
                    [prompt, user_msg],
                    generation_config={"temperature": 0, "max_output_tokens": MAX_OUTPUT_TOKENS},
                )
                return response.text or None
        except Exception as e:
            err_str = str(e)[:120]
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                wait = 60 * (attempt + 1)
                print(f"\n    RATE LIMIT hit. Waiting {wait}s...", end="", flush=True)
                time.sleep(wait)
            else:
                wait = 10 * (attempt + 1)
                print(f" [retry {attempt+1}: {err_str}]", end="", flush=True)
                time.sleep(wait)
    return None

def build_batch_message(sentences_with_ids):
    lines = [
        "MODE: STANDALONE",
        "",
        "TASK: You are about to receive a batch of sentences. You must process EACH sentence independently.",
        "For EACH sentence, output one complete <participle_correction> block exactly as defined in your master XML OUTPUT SCHEMA.",
        f"Because there are {len(sentences_with_ids)} sentences below, you MUST output exactly {len(sentences_with_ids)} <participle_correction> blocks in the exact same order.",
        "",
        "INPUT SENTENCES:"
    ]
    for i, (sid, sentence) in enumerate(sentences_with_ids):
        lines.append(f"--- SENTENCE {i+1} ---")
        lines.append(sentence)
        lines.append("")
        
    lines.append("Begin outputting your sequence of <participle_correction> blocks now:")
    return "\n".join(lines)

def parse_batch_response(raw_text, sentence_ids):
    if not raw_text:
        return {sid: "PARSE_ERROR" for sid in sentence_ids}
    
    results = {}
    
    # Harvest the final corrected sentences directly from the Master Prompt's schema
    all_corrections = re.findall(
        r"<corrected_sentence>(.*?)</corrected_sentence>", 
        raw_text, 
        re.DOTALL | re.IGNORECASE
    )
    
    all_corrections = [c.strip() for c in all_corrections]
    
    # Sequential Mapping
    for i, sid in enumerate(sentence_ids):
        if i < len(all_corrections):
            text = all_corrections[i]
            results[sid] = text if text != "NO_ACTION_NEEDED" else "NO_ACTION"
        else:
            results[sid] = "PARSE_ERROR"

    # Failsafe print if mapping fails
    error_count = sum(1 for v in results.values() if v == "PARSE_ERROR")
    if error_count > 0:
        print(f"\n[PARSE WARNING] Expected {len(sentence_ids)} corrections, found {len(all_corrections)}.")
        if error_count == len(sentence_ids):
            print(f"Raw output snippet (END OF TEXT):\n...\n{raw_text[-1000:]}\n")
            
            
    return results

def load_daily_counter(worker_id):
    counter_file = os.path.join(RESULTS_DIR, f"daily_counter_{worker_id}.json")
    if os.path.exists(counter_file):
        with open(counter_file, "r") as f:
            data = json.load(f)
        if data.get("date") == datetime.now().strftime("%Y-%m-%d"):
            return data.get("count", 0), counter_file
    return 0, counter_file

def save_daily_counter(counter_file, count):
    with open(counter_file, "w") as f:
        json.dump({"date": datetime.now().strftime("%Y-%m-%d"), "count": count}, f)

def main():
    if len(sys.argv) < 2:
        print("Usage: python worker_batch.py <chunk_id>")
        sys.exit(1)

    chunk_id = int(sys.argv[1])
    sdk_type, client, genai_mod = setup_sdk()
    prompt = load_prompt()
    os.makedirs(RESULTS_DIR, exist_ok=True)

    chunk_file = os.path.join(CHUNKS_DIR, f"chunk_{chunk_id}.json")
    with open(chunk_file, "r", encoding="utf-8") as f:
        chunk_data = json.load(f)

    print(f"Worker {chunk_id} (BATCHED) | SDK: {sdk_type} | Model: {MODEL}")
    print(f"  Chunk: {len(chunk_data):,} sentences | Batch size: {BATCH_SIZE}")

    checkpoint_file = os.path.join(RESULTS_DIR, f"worker_{chunk_id}.jsonl")
    completed_indices = set()
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    completed_indices.add(json.loads(line).get("idx"))
        print(f"  Resuming: {len(completed_indices)} sentences done")

    remaining = [(idx, rec) for idx, rec in enumerate(chunk_data) if idx not in completed_indices]
    
    if not remaining:
        print("  Chunk complete!")
        return

    daily_count, counter_file = load_daily_counter(chunk_id)
    worker_daily_limit = DAILY_LIMIT // 6
    
    start_time = time.time()
    batch_num = 0
    total_processed = 0
    total_errors = 0
    api_calls_today = daily_count

    with open(checkpoint_file, "a", encoding="utf-8") as out_f:
        for batch_start in range(0, len(remaining), BATCH_SIZE):
            batch = remaining[batch_start:batch_start + BATCH_SIZE]
            batch_num += 1

            if api_calls_today >= worker_daily_limit:
                print(f"\n  ⏸️ Daily limit reached. Restart tomorrow.")
                save_daily_counter(counter_file, api_calls_today)
                break

            sentence_pairs = [(str(rec.get("sentence_id", idx)), rec["text"]) for idx, rec in batch]
            sentence_ids = [sp[0] for sp in sentence_pairs]

            total_done = len(completed_indices) + total_processed
            print(f"  Batch {batch_num} [{total_done+1}–{total_done+len(batch)}/{len(chunk_data)}] ", end="", flush=True)

            user_msg = build_batch_message(sentence_pairs)
            t0 = time.time()
            raw_response = call_gemini(sdk_type, client, genai_mod, prompt, user_msg)
            call_time = time.time() - t0
            api_calls_today += 1

            corrections = parse_batch_response(raw_response or "", sentence_ids)

            batch_errors = 0
            for idx, rec in batch:
                sid = str(rec.get("sentence_id", idx))
                corrected = corrections.get(sid, "PARSE_ERROR")
                is_error = corrected == "PARSE_ERROR"

                if corrected == "NO_ACTION":
                    corrected = rec["text"]

                if is_error:
                    batch_errors += 1
                    total_errors += 1

                out_f.write(json.dumps({
                    "idx": idx,
                    "sentence_id": sid,
                    "original": rec["text"],
                    "corrected": corrected,
                    "is_error": is_error
                }, ensure_ascii=False) + "\n")
                completed_indices.add(idx)

            out_f.flush()
            total_processed += len(batch)
            save_daily_counter(counter_file, api_calls_today)

            err_str = f" ({batch_errors} err)" if batch_errors else ""
            print(f"✓ {call_time:.1f}s{err_str}", flush=True)
            time.sleep(API_DELAY)

    print(f"\nWorker {chunk_id} SESSION COMPLETE. Errors: {total_errors}")

if __name__ == "__main__":
    main()