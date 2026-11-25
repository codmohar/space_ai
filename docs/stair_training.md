# STAIR L3 / L4 Training Guide (Colab / Kaggle Free GPU)

MISSIONWISE implements STAIR retrieval in explicit, honestly labelled levels:
- **L1:** Hierarchical ToC/section index (`document_sections` with `is_leaf`) + `BM25ToCSectionSelector`.
- **L2 (Active in Phase 2):** ToC + query prompt → JSON of validated top-k leaf section IDs (`STAIRInspiredSectionSelector`).
- **L3 / L4 (Optional GPU Training):** Fine-tuned LoRA adapter over a small open instruct model with constrained decoding restricting outputs to valid leaf IDs (`FineTunedSTAIRSectionSelector`).

The main application **never blocks** on L3/L4 training.

## Step 1: Generate & Export Training Pairs
```bash
python scripts/generate_training_data.py --questions-per-leaf 2 --export-jsonl data/stair_pairs.jsonl
```
All generated pairs default to `reviewed = False` in `stair_training_pairs` with a deterministic 70/15/15 `train/val/test` split.

## Step 2: Train LoRA on Free Colab T4 / Kaggle P100 (16GB VRAM)
```bash
pip install torch transformers peft bitsandbytes datasets accelerate
python scripts/train_stair.py \
  --dataset data/stair_pairs.jsonl \
  --base-model Qwen/Qwen2.5-1.5B-Instruct \
  --output-dir models/stair_lora \
  --epochs 3 \
  --load-in-4bit
```

## Step 3: Enable L3 Adapter in MISSIONWISE
1. Place the saved `models/stair_lora/` directory inside the backend container or workspace.
2. Set in `.env`:
   ```env
   SECTION_SELECTOR_MODE=stair_l3
   STAIR_LORA_ADAPTER_PATH=/app/models/stair_lora
   ```
3. Run `scripts/evaluate_retrieval.py` to measure `Recall@1/3/5`, `MRR`, `nDCG@5`, and `invalid_section_rate` against L1/L2 baselines.
