# d1-2B weights are not in this folder

This folder holds Liquid AI's d1-2B model code, config, tokenizer and `LICENSE` (LFM Open License v1.0), copied unchanged from the local snapshot (revision files in `SHA256SUMS.txt`). `model.safetensors` (3.57 GiB) is not included: it is over GitHub's 100 MB file limit and the board gets it from the supplied USB drive.

To run d1 from here, copy the weights next to this file, then verify:
```bash
cp /path/to/d1-2B/model.safetensors iq9-demo/models/d1-2B/
cd iq9-demo/models/d1-2B && shasum -a 256 -c SHA256SUMS.txt   # sha256sum -c on Linux
```
`iq9sim/d1svc.py` looks here first, then `~/models/d1-2B`, then `~/Models/LiquidAI/d1-2B`, and uses the first folder that contains `model.safetensors`. Loading is offline (`local_files_only`).
Needs `transformers==5.19.0`, torch, torchvision, pillow, numpy.
