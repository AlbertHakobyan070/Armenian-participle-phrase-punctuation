#!/usr/bin/env python3
"""
Batch API Unpacker
Extracts Vertex AI batch responses and formats them to match your project.
"""
import json
import os
import re

BATCH_OUTPUT_DIR = "./results/batch_output/"
# We save this inside your results folder so it sits alongside your live data
FINAL_OUTPUT_FILE = "./results/results/worker_6.jsonl" 

def main():
    os.makedirs(BATCH_OUTPUT_DIR, exist_ok=True)
    # Added a broader check in case the file name doesn't include "prediction"
    files = [f for f in os.listdir(BATCH_OUTPUT_DIR) if f.endswith('.jsonl')]
    
    if not files:
        print(f"[!] No prediction files found.")
        print(f"Please download your '.jsonl' files from Cloud Storage")
        print(f"and place them inside the '{BATCH_OUTPUT_DIR}' folder.")
        return

    total_extracted = 0
    total_errors = 0

    print("Unpacking Vertex AI Batch Results...\n")

    with open(FINAL_OUTPUT_FILE, 'w', encoding='utf-8') as out_f:
        for filename in files:
            filepath = os.path.join(BATCH_OUTPUT_DIR, filename)
            
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip(): continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                        
                    # THE FIX: Google Batch leaves the custom "key" at the root level of the JSON
                    request_key = record.get("key", "")
                    
                    if not request_key.startswith("sids_"): continue
                    sids = request_key.replace("sids_", "").split("_")
                    
                    # Extract the generated text
                    try:
                        resp_text = record["response"]["candidates"][0]["content"]["parts"][0]["text"]
                    except KeyError:
                        # If Google's API threw an error for this specific batch, mark the 3 sentences for retry
                        for sid in sids:
                            out_f.write(json.dumps({"sentence_id": sid, "is_error": True, "corrected": ""}, ensure_ascii=False) + '\n')
                            total_errors += 1
                        continue
                        
                    # Split the response into the 3 distinct blocks
                    blocks = re.findall(r'<participle_correction>.*?</participle_correction>', resp_text, re.DOTALL)
                    
                    if len(blocks) == len(sids):
                        # Perfect match: 3 sentences sent, 3 XML blocks received
                        for sid, block in zip(sids, blocks):
                            out_rec = {
                                "sentence_id": sid,
                                "corrected": block, 
                                "is_error": False
                            }
                            out_f.write(json.dumps(out_rec, ensure_ascii=False) + '\n')
                            total_extracted += 1
                    else:
                        # Mismatch: The AI merged blocks or skipped one. Mark for retry backlog.
                        for sid in sids:
                            out_rec = {
                                "sentence_id": sid,
                                "corrected": resp_text,
                                "is_error": True
                            }
                            out_f.write(json.dumps(out_rec, ensure_ascii=False) + '\n')
                            total_errors += 1

    print(f"-" * 40)
    print(f"✅ Unpacking Complete!")
    print(f"Successfully unpacked: {total_extracted:,} sentences")
    print(f"Errors marked for retry: {total_errors:,}")
    print(f"File saved as: {FINAL_OUTPUT_FILE}")
    print(f"-" * 40)

if __name__ == "__main__":
    main()