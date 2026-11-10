# LoRA fine-tuning

OmniVoice's full fine-tuning and evaluation pipeline is an upstream research
workflow. This directory contains starting configs for the upstream LoRA
trainer, wired into the `Makefile`.

## 1. Prepare tokenized data

Follow the upstream data preparation and LoRA guides:

- <https://github.com/k2-fsa/OmniVoice/blob/master/docs/data_preparation.md>
- <https://github.com/k2-fsa/OmniVoice/blob/master/docs/lora_finetuning.md>

Place the tokenized manifests and configs inside the Docker data volume, for
example:

```bash
docker cp training/. omnivoice-studio-engine-1:/data/training/
docker cp my-tokens/. omnivoice-studio-engine-1:/data/finetune/tokens/
```

Edit `training/data_config.json` so `manifest_path` points at your tokenized
manifests. Edit `training/train_config_lora.json` for steps, LoRA rank, learning
rate, and checkpoint cadence.

## 2. Train

Use the GPU stack:

```bash
make train-lora ACCEL=gpu \
  TRAIN_CONFIG=/data/training/train_config_lora.json \
  DATA_CONFIG=/data/training/data_config.json \
  OUTPUT_DIR=/data/loras/my-voice \
  NUM_PROCESSES=1
```

The trainer runs in a one-off engine container, so stop the inference engine
first if VRAM is tight:

```bash
make down
make train-lora ACCEL=gpu ...
make up-gpu
```

## 3. Use the adapter

Point the engine at a checkpoint directory containing `adapter_config.json`:

```dotenv
OMNIVOICE_LORA_ADAPTER=/data/loras/my-voice/checkpoint-500
```

Restart with `make restart`, then the adapter is merged into the model in memory.
Alternatively, merge it permanently:

```bash
make merge-lora \
  ADAPTER=/data/loras/my-voice/checkpoint-500 \
  OUTPUT=/data/loras/my-voice/merged
```

Set `OMNIVOICE_MODEL=/data/loras/my-voice/merged` and restart.

## Notes

- Training requires a GPU and a prepared tokenized dataset; it is not exposed in
  the Studio UI.
- The inference studio supports LoRA adapter loading and merging.
- Check the upstream license and consent requirements before fine-tuning a
  person's voice.
