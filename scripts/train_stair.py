"""LoRA fine-tuning & constrained leaf-ID decoding script for STAIR L3/L4.

Designed to run standalone on a free Colab T4 (16GB) or Kaggle P100 GPU.
The main MISSIONWISE web app never blocks on this script; when a trained LoRA
adapter is placed at STAIR_LORA_ADAPTER_PATH, FineTunedSTAIRSectionSelector
automatically picks it up.

See docs/stair_training.md for full Colab/Kaggle instructions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


def format_stair_prompt(query: str, toc_sections: Sequence[dict[str, Any]]) -> str:
    """Format hierarchical ToC + query into instruction prompt for LoRA fine-tuning."""
    lines = []
    for sec in toc_sections[:250]:
        indent = "  " * max(0, int(sec.get("level", 1)) - 1)
        sid = sec["id"]
        path = sec.get("section_path", "")
        title = sec.get("title", "")
        p_start = sec.get("page_start", 1)
        p_end = sec.get("page_end", p_start)
        if sec.get("is_leaf", True):
            lines.append(f"{indent}- [LEAF id={sid}] §{path} {title} (pp.{p_start}-{p_end})")
        else:
            lines.append(f"{indent}- [NODE] §{path} {title} (pp.{p_start}-{p_end})")

    return (
        "### System:\n"
        "Select up to 3 valid [LEAF id=...] UUIDs from the Table of Contents that answer the query. "
        "Output JSON: {\"selected_ids\": [\"<uuid>\"]}.\n\n"
        f"### Table of Contents:\n" + "\n".join(lines) + "\n\n"
        f"### Query:\n{query.strip()}\n\n"
        "### Response:\n"
    )


class ValidLeafIDTrieConstraint:
    """Prefix-trie constrained decoding helper restricting IDs to valid ToC leaf UUIDs.

    Wraps valid leaf IDs into token-sequence prefixes so a HuggingFace LogitsProcessor
    can mask out invalid UUID tokens during generation (STAIR L4 constrained decoding).
    """

    def __init__(self, tokenizer: Any, valid_leaf_ids: Sequence[str]) -> None:
        self.tokenizer = tokenizer
        self.valid_leaf_ids = list(dict.fromkeys(valid_leaf_ids))
        self.allowed_token_sequences = [
            tokenizer.encode(lid, add_special_tokens=False) for lid in self.valid_leaf_ids
        ]

    def build_logits_processor(self, prompt_length: int):
        import torch
        from transformers import LogitsProcessor

        sequences = self.allowed_token_sequences
        eos_id = self.tokenizer.eos_token_id

        class _ConstrainedLeafProcessor(LogitsProcessor):
            def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor) -> torch.FloatTensor:
                gen_tokens = input_ids[0, prompt_length:].tolist()
                # When inside a UUID span, constrain next token to valid trie continuations
                matching_next: set[int] = set()
                for seq in sequences:
                    if len(gen_tokens) < len(seq) and seq[: len(gen_tokens)] == gen_tokens:
                        matching_next.add(seq[len(gen_tokens)])
                if matching_next:
                    mask = torch.full_like(scores, float("-inf"))
                    for tok_id in matching_next:
                        mask[:, tok_id] = 0.0
                    if eos_id is not None and len(gen_tokens) > 0:
                        mask[:, eos_id] = 0.0
                    return scores + mask
                return scores

        return _ConstrainedLeafProcessor()


def predict_leaf_sections_with_lora(
    adapter_path: str,
    query: str,
    toc_rows: Sequence[Any],
    top_k: int = 3,
    base_model: str = "Qwen/Qwen2.5-1.5B-Instruct",
) -> list[str]:
    """Run constrained LoRA inference if transformers + peft + torch are installed."""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, LogitsProcessorList

    sections_payload = [
        {
            "id": str(sec.id),
            "level": sec.level,
            "is_leaf": sec.is_leaf,
            "section_path": sec.section_path,
            "title": sec.title,
            "page_start": sec.page_start,
            "page_end": sec.page_end,
        }
        for sec, _doc in toc_rows
    ]
    valid_leaf_ids = [s["id"] for s in sections_payload if s["is_leaf"]]
    prompt = format_stair_prompt(query, sections_payload)

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    model = AutoModelForCausalLM.from_pretrained(base_model, torch_dtype=torch.float16, device_map="auto")
    model = PeftModel.from_pretrained(model, adapter_path)
    model.eval()

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    constraint = ValidLeafIDTrieConstraint(tokenizer, valid_leaf_ids)
    processors = LogitsProcessorList([constraint.build_logits_processor(inputs["input_ids"].shape[1])])

    with torch.no_grad():
        out_ids = model.generate(
            **inputs,
            max_new_tokens=96,
            do_sample=False,
            logits_processor=processors,
        )
    decoded = tokenizer.decode(out_ids[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True)
    try:
        parsed = json.loads(decoded)
        return [str(x) for x in parsed.get("selected_ids", [])][:top_k]
    except json.JSONDecodeError:
        return [lid for lid in valid_leaf_ids if lid in decoded][:top_k]


def train_lora(
    dataset_jsonl: Path,
    output_dir: Path,
    base_model: str,
    epochs: int,
    batch_size: int,
    lr: float,
    load_in_4bit: bool,
) -> None:
    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )

    records = [
        json.loads(line)
        for line in dataset_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    train_records = [r for r in records if r.get("split", "train") == "train"]
    if not train_records:
        raise ValueError(f"No train-split records found in {dataset_jsonl}")

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    texts = []
    for rec in train_records:
        prompt = format_stair_prompt(rec["query"], rec["toc_snapshot"]["sections"])
        target = json.dumps({"selected_ids": [rec["target_section_id"]]})
        texts.append(prompt + target + tokenizer.eos_token)

    ds = Dataset.from_dict({"text": texts})

    def tokenize_fn(batch):
        return tokenizer(batch["text"], truncation=True, max_length=2048)

    tokenized_ds = ds.map(tokenize_fn, batched=True, remove_columns=["text"])

    bnb_config = None
    if load_in_4bit:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )

    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=bnb_config,
        device_map="auto",
    )
    if load_in_4bit:
        model = prepare_model_for_kbit_training(model)

    lora_cfg = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()

    output_dir.mkdir(parents=True, exist_ok=True)
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=4,
        learning_rate=lr,
        fp16=True,
        logging_steps=10,
        save_strategy="epoch",
        report_to="none",
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_ds,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
    )
    trainer.train()
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    print(f"Saved STAIR LoRA adapter to {output_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fine-tune STAIR L3/L4 LoRA section selector.")
    parser.add_argument("--dataset", type=Path, required=True, help="JSONL from generate_training_data.py")
    parser.add_argument("--output-dir", type=Path, default=Path("./models/stair_lora"))
    parser.add_argument("--base-model", type=str, default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--load-in-4bit", action="store_true", default=True)
    args = parser.parse_args()

    train_lora(
        dataset_jsonl=args.dataset,
        output_dir=args.output_dir,
        base_model=args.base_model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        load_in_4bit=args.load_in_4bit,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
