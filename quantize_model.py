"""Make a smaller (quantized) copy of whisper-large-v3-turbo for VoiceFlow.

./.venv/bin/python quantize_model.py 8   -> models/whisper-turbo-q8
./.venv/bin/python quantize_model.py 4   -> models/whisper-turbo-q4
Uses the fp16 model in the Hugging Face cache, downloading it (1.6 GB) if it is not there.

--tidy  delete that 1.6 GB download afterwards, but only if this run downloaded it
        (if it was already on the Mac, other tools may be using it, so it is kept).
"""
import json
import shutil
import sys
from pathlib import Path

import slim  # noqa: F401  (must come before mlx_whisper is imported)
import mlx.core as mx
import mlx.nn as nn
from huggingface_hub import snapshot_download, try_to_load_from_cache
from mlx.utils import tree_flatten
from mlx_whisper.load_models import load_model

REPO = "mlx-community/whisper-large-v3-turbo"
bits = int(sys.argv[1])
tidy = "--tidy" in sys.argv
was_cached = isinstance(try_to_load_from_cache(REPO, "weights.safetensors"), str)
src = Path(snapshot_download(REPO))
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
if tidy and not was_cached:
    repo_dir = src.parent.parent  # .../hub/models--mlx-community--whisper-large-v3-turbo
    if repo_dir.name == "models--" + REPO.replace("/", "--"):
        del model
        shutil.rmtree(repo_dir, ignore_errors=True)
        print("removed the 1.6 GB download", repo_dir)
elif tidy:
    print("kept the fp16 model that was already in the Hugging Face cache")
