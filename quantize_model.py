"""Make a smaller (quantized) copy of whisper-large-v3-turbo for VoiceFlow.

./.venv/bin/python quantize_model.py 8   -> models/whisper-turbo-q8
./.venv/bin/python quantize_model.py 4   -> models/whisper-turbo-q4
Uses the fp16 model already in the Hugging Face cache; nothing is downloaded.
"""
import json
import sys
from pathlib import Path

import mlx.core as mx
import mlx.nn as nn
from huggingface_hub import snapshot_download
from mlx.utils import tree_flatten
from mlx_whisper.load_models import load_model

bits = int(sys.argv[1])
src = Path(snapshot_download("mlx-community/whisper-large-v3-turbo"))
out = Path(__file__).resolve().parent / "models" / f"whisper-turbo-q{bits}"
out.mkdir(parents=True, exist_ok=True)

model = load_model(str(src), dtype=mx.float16)
pred = lambda p, m: isinstance(m, (nn.Linear, nn.Embedding)) and m.weight.shape[-1] % 64 == 0
nn.quantize(model, group_size=64, bits=bits, class_predicate=pred)
mx.save_safetensors(str(out / "weights.safetensors"), dict(tree_flatten(model.parameters())))
config = json.loads((src / "config.json").read_text())
config["quantization"] = {"group_size": 64, "bits": bits}
(out / "config.json").write_text(json.dumps(config, indent=2))
print("saved", out)
