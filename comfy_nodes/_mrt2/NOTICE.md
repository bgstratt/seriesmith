# Magenta RealTime 2, PyTorch port

The `.py` files and `codec_shapes.json` here are the PyTorch port of Google's Magenta
RealTime 2, copied from the Hugging Face repo `magenta-community/magenta-realtime-2` at
revision `92087988d05d0fe38b11f021f0b0d00a75afb86b` (2026-06-23; `magenta-realtime-2-small`
carries the same code). `__init__.py` and this file are seriesmith's.

Changed by seriesmith (2026-11-10), so the port loads only from local folders and carries no
code seriesmith doesn't run: `aoti.py` is removed, and with it `export_aoti`, `load_aoti` and
`load_compiled` in `modeling_magenta_rt2.py` and the imports that bundled modules for
`trust_remote_code`; `musiccoca.py` and `processing_musiccoca.py` take a local folder only (their
Hugging Face downloads are removed); `load_processor` takes a folder; `resampy` is a plain import;
`layers.dot_product_attention` multiplies instead of calling matmul when there is one key (the same
numbers: torch 2.15's own kernel for a batched outer product fails on it).
Otherwise unchanged (line endings aside).

Copyright 2026 Google LLC. Licensed under the Apache License, Version 2.0
(http://www.apache.org/licenses/LICENSE-2.0), as each file's header says.

The weights are not here: the Features window downloads them into ComfyUI's models folder
(`magenta-community/magenta-realtime-2` or `-small`, and
`magenta-community/magenta-rt-musiccoca-torch`). Google's Magenta RealTime 2 weights are
licensed CC BY 4.0: credit "Magenta RealTime 2 by Google" where the music is used.

seriesmith loads the model class directly from a local folder (comfy_nodes/mrt2.py) and gives
MusicCoCa a local folder, so nothing here downloads.
