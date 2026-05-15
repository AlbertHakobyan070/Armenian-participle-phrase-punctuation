# Sequence Labeling for Low-Resource Syntax: Automatic Punctuation of Armenian Participle Clauses

**Author:** Albert Hakobyan  
**Affiliation:** American University of Armenia, Zaven P. and Sonia Akian College of Science & Engineering  
**Supervisor:** Prof. Sachin Kumar  
**Linguist Collaborator:** Anahit Hovhannisyan  
**Date:** May 2026

## Project Objective

This project develops a knowledge distillation pipeline for automatic punctuation of Armenian participle phrases — a syntactically complex area where even educated writers frequently make errors. A Gemini 2.5 Flash teacher model, guided by linguist-curated prompts, annotated 112K sentence pairs from the OSCAR corpus. These annotations trained four student architectures (BiLSTM, HyeBERT, mBERT, and a BiLSTM–mBERT ensemble), which were evaluated on two human-annotated benchmarks.

The ensemble achieved a macro-F1 of 0.6745 on the Shtemaran benchmark, within 2.5% of the Gemini teacher (0.6997) and statistically indistinguishable from it (McNemar's p = 0.111). Student models outperformed the teacher on comma placement.

## Repository Structure

```
.
├── code/
│   ├── data_pipeline/              # Corpus construction (Steps 1-4)
│   │   ├── 01_participle_extraction_and_alignment.ipynb
│   │   ├── 02_stanza_preprocessing_pipeline.ipynb
│   │   ├── 03_corpus_filtering_and_sampling.ipynb
│   │   └── 04_corpus_and_gold_postprocessing.ipynb
│   │
│   ├── annotation/                 # Gemini batch annotation pipeline
│   │   ├── worker.py               # Single-sentence API annotation worker
│   │   ├── worker_batch.py         # Vertex AI batch prediction worker
│   │   ├── worker_retry.py         # Retry handler for failed sentences
│   │   ├── merge_results.py        # Merge worker outputs into final JSONL
│   │   ├── prepare_batch.py        # Prepare JSONL for Vertex AI batch prediction
│   │   ├── unpack_batch.py         # Unpack Vertex AI batch results
│   │   ├── run_mac.sh              # Launch script (macOS)
│   │   ├── run_windows.bat         # Launch script (Windows)
│   │   ├── gemini_shtemaran_runner.py  # Gemini zero-shot eval on Shtemaran
│   │   └── MASTER_GEMINI_PROMPT_v3_1.md  # Linguist-curated annotation prompt
│   │
│   ├── training/                   # Model training notebooks
│   │   ├── train_bilstm_v3.ipynb
│   │   ├── train_hyebert_v3_matched.ipynb
│   │   ├── mbert_optuna_colab.ipynb
│   │   └── ensemble_bilstm_mbert.ipynb
│   │
│   └── evaluation/                 # Evaluation notebooks (produce paper tables/figures)
│       ├── eval_gold_2k.ipynb      # Table I, correction coverage
│       └── eval_shtemaran_292.ipynb # Table II, Figures 1-2, McNemar's test
│
├── data/
│   ├── gold_2k/                    # 2,008 human-annotated sentences
│   │   ├── gold_2k_annotation_Main.xlsx
│   │   ├── gold_2k_metadata_final.json
│   │   └── gold_2k_sentences_final.txt
│   │
│   └── shtemaran/                  # 292 textbook-quality benchmark sentences
│       ├── Gold_Final.txt
│       ├── Partial_NP_Final.txt
│       └── ONLY_Participle-related_punct_in-place.txt
│
├── weights/                        # Trained model weights (Git LFS)
│   ├── bilstm_v3_best.pt
│   ├── armenian_vocab.json
│   ├── armenian_embeddings.pt
│   ├── mbert_best.pt
│   ├── mbert_best_config.json
│   ├── hyebert_v3_best.pt
│   ├── best_config.json
│   └── results.json
│
├── requirements.txt
├── LICENSE
└── README.md
```

## How to Reproduce Results

### Prerequisites

```bash
pip install -r requirements.txt
```

PyTorch installation may require platform-specific instructions — see https://pytorch.org/get-started/locally/

### Hardware Used

| Component | Platform | Used For |
|-----------|----------|----------|
| MacBook Pro M1 Pro (16 GB) | PyTorch MPS | BiLSTM training, ensemble, all evaluations |
| Desktop PC, 2× GTX 1070 Ti (8 GB each) | CUDA 11.8 | HyeBERT fine-tuning |
| Google Colab T4 (16 GB) | CUDA (free tier) | mBERT Optuna HPO + final training |

### Reproducing Paper Tables and Figures

**Table I (Gold 2K results):**
```bash
jupyter notebook code/evaluation/eval_gold_2k.ipynb
# Run all cells. Requires: data/gold_2k/, Weights/
```

**Table II + Figures 1-2 + McNemar's test (Shtemaran benchmark):**
```bash
# Step 1: Run Gemini zero-shot baseline (requires API key)
python code/annotation/gemini_shtemaran_runner.py --api-key YOUR_GEMINI_KEY

# Step 2: Run evaluation notebook
jupyter notebook code/evaluation/eval_shtemaran_292.ipynb
# Run all cells. Requires: data/shtemaran/, Weights/, Gemini cache from Step 1
```

### Reproducing Model Training

Training notebooks are in `code/training/`. Each notebook contains all steps from data loading through final evaluation. Paths at the top of each notebook must be adjusted to match your directory structure.

**BiLSTM:** Run `train_bilstm_v3.ipynb` locally (CPU or MPS).  
**HyeBERT:** Run `train_hyebert_v3_matched.ipynb` with a CUDA GPU.  
**mBERT:** Run `mbert_optuna_colab.ipynb` on Google Colab with a T4 GPU.  
**Ensemble:** Run `ensemble_bilstm_mbert.ipynb` after BiLSTM and mBERT training.

### Reproducing the Annotation Pipeline

To re-run annotation from scratch:

1. Download the OSCAR 23.01 Armenian corpus from https://huggingface.co/datasets/oscar-corpus/OSCAR-2301 (language: `hy`)
2. Run the data pipeline notebooks (`code/data_pipeline/01-04`) to filter and sample 120K sentences
3. Run `code/annotation/worker.py` with a Gemini API key to annotate sentences using the prompt in `MASTER_GEMINI_PROMPT_v3_1.md`
4. Run `code/annotation/merge_results.py` to produce the final clean JSONL files

## Data Sources

- **OSCAR 23.01 (Armenian):** Web-crawled corpus, CC0 license. Abadji et al. (2022), Ortiz Suárez et al. (2019).
- **Gold 2K:** 2,008 sentences manually annotated by linguist A. Hovhannisyan, sampled from OSCAR.
- **Shtemaran 292:** 292 sentences from the Armenian grammar reference textbook, annotated by A. Hovhannisyan.
- **GloVe embeddings:** Stanford GloVe 300-dim Armenian vectors (Pennington et al., 2014).

## 4-Class Token Classification

Each word token receives one label:
- `O` — no action needed
- `COMMA_AFTER` — insert comma after this word
- `BUTH_AFTER` — insert buth (՝) after this word
- `REMOVE_COMMA` — delete the comma following this word

## Key Results

| Model | Macro-F1 (Gold 2K) | Macro-F1 (Shtemaran) |
|-------|--------------------:|---------------------:|
| BiLSTM | 0.4116 | 0.3661 |
| HyeBERT | — | 0.3260 |
| mBERT | 0.4655 | 0.5190 |
| Ensemble (α=0.45) | 0.4648 | **0.6745** |
| Gemini 2.5 Flash | — | 0.6997 |

## License

This repository is licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). You may use, adapt, and share this work for non-commercial purposes with attribution. Model weights derived from mBERT (Apache 2.0) and HyeBERT retain their original upstream licenses.
