"""Count the parameters in a .safetensors file and show what they cost in memory.

Reads only the file's JSON header (tensor names, dtypes, shapes) - fast and exact.

    python scripts/inspect_weights.py path/to/model.safetensors
"""

from __future__ import annotations

import json
import struct
import sys
from collections import Counter
from math import prod
from pathlib import Path

BYTES = {"F64": 8, "F32": 4, "F16": 2, "BF16": 2, "I64": 8, "I32": 4, "I16": 2, "I8": 1, "U8": 1, "BOOL": 1}


def main() -> None:
    path = Path(sys.argv[1]).expanduser()
    with path.open("rb") as f:
        (n,) = struct.unpack("<Q", f.read(8))
        header = json.loads(f.read(n))
    header.pop("__metadata__", None)
    params = 0
    dtypes: Counter[str] = Counter()
    for t in header.values():
        count = prod(t["shape"])
        params += count
        dtypes[t["dtype"]] += count
    dtype, _ = dtypes.most_common(1)[0]
    size = path.stat().st_size
    print(f"params:   {params:,}")
    print(f"dtype:    {dtype}  ({BYTES.get(dtype, '?')} bytes each)")
    print(f"on disk:  {size / 1e9:.2f} GB")
    print(f"per param: {size / params:.2f} bytes")


if __name__ == "__main__":
    main()
