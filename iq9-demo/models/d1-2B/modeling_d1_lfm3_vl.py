"""`AutoModel.from_pretrained(repo, trust_remote_code=True)`: LFM3-VL with the System One API (`modeling_d1`)."""

from __future__ import annotations

from .lfm3 import Lfm3SystemOne
from .native_lfm3_vl import Lfm3VlForConditionalGeneration


class D1Model(Lfm3SystemOne, Lfm3VlForConditionalGeneration):
    compiled_parts = ("vision_tower", "multi_modal_projector")
