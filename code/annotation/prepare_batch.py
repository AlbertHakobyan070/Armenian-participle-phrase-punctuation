#!/usr/bin/env python3
import json
import os

CHUNKS_DIR = "./chunks"
RESULTS_DIR = "./results"
PROMPT_FILE = "MASTER_GEMINI_PROMPT_v3_1.md"
BATCH_SIZE = 3
NUM_WORKERS = 6
OUTPUT_FILE = "gemini_batch_requests.jsonl"

def load_prompt():
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        return f.read()

def build_user_msg(sentences_with_ids):
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

def main():
    prompt_text = load_prompt()
    # The simulated model agreement to lock it into your Master Prompt
    model_ack = "Understood. I will process the batch and output a complete <participle_correction> XML block for EACH sentence in the exact order they are provided."

    all_remaining = []
    
    print("Scanning chunks and completed results...")
    for w in range(NUM_WORKERS):
        chunk_file = os.path.join(CHUNKS_DIR, f"chunk_{w}.json")
        if not os.path.exists(chunk_file):
            print(f"  [!] Missing {chunk_file}")
            continue
            
        with open(chunk_file, "r", encoding="utf-8") as f:
            chunk_data = json.load(f)
            
        completed_indices = set()
        res_file = os.path.join(RESULTS_DIR, f"worker_{w}.jsonl")
        
        if os.path.exists(res_file):
            # Read as raw text to safely bypass any "}{" mashed line glitches
            with open(res_file, 'r', encoding='utf-8') as f:
                raw_text = f.read().replace('}{', '}\n{')
                for line in raw_text.split('\n'):
                    if not line.strip(): 
                        continue
                    try:
                        rec = json.loads(line)
                        completed_indices.add(rec.get("idx"))
                    except:
                        pass
                        
        for idx, rec in enumerate(chunk_data):
            if idx not in completed_indices:
                all_remaining.append(rec)
                
    print(f"Total remaining sentences to process: {len(all_remaining):,}")
    
    print(f"Packaging into API requests (Batch Size: {BATCH_SIZE})...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as out_f:
        batch_count = 0
        for i in range(0, len(all_remaining), BATCH_SIZE):
            batch = all_remaining[i:i + BATCH_SIZE]
            sentence_pairs = [(str(rec.get("sentence_id", rec.get("idx"))), rec["text"]) for rec in batch]
            
            user_msg = build_user_msg(sentence_pairs)
            
            # Create a unique key using the sentence IDs so we can map the results back later
            sids = [sp[0] for sp in sentence_pairs]
            request_key = "sids_" + "_".join(sids)
            
            # Google Batch API strict JSON format
            request_obj = {
                "key": request_key,
                "request": {
                    "contents": [
                        {"role": "user", "parts": [{"text": prompt_text}]},
                        {"role": "model", "parts": [{"text": model_ack}]},
                        {"role": "user", "parts": [{"text": user_msg}]}
                    ],
                    "generationConfig": {
                        "temperature": 0,
                        "maxOutputTokens": 8192
                    }
                }
            }
            out_f.write(json.dumps(request_obj, ensure_ascii=False) + '\n')
            batch_count += 1
            
    print("-" * 40)
    print(f"Successfully packaged {batch_count:,} requests into 1 file.")
    print(f"File saved as: {OUTPUT_FILE}")
    print(f"Estimated Cost (Batch API): ~${(batch_count * 3 * 0.0028) * 0.50:.2f}")
    print("-" * 40)

if __name__ == "__main__":
    main()