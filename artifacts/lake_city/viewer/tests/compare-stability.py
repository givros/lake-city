"""Compare captured pixels without resampling or modifying the evidence images."""
import json
from pathlib import Path

import numpy as np
from PIL import Image

root = Path(__file__).resolve().parents[2] / "renders" / "stability"
results = {}
for tag in ("baseline-first-frame", "after-pass-isolation", "final-moving-camera", "city-life"):
    directory = root / tag
    result = {"allSourceComparisons": [], "repeatComparisons": []}
    for image in sorted(directory.glob("*.png")):
        kind = "allSourceComparisons" if image.stem.endswith("-all-source") else "repeatComparisons" if image.stem.endswith("-repeat") else None
        if kind is None:
            continue
        reference = directory / (image.name.replace("-all-source", "").replace("-repeat", ""))
        a = np.asarray(Image.open(reference).convert("RGB")).astype(np.int16)
        b = np.asarray(Image.open(image).convert("RGB")).astype(np.int16)
        delta = np.abs(a - b)
        maximum = delta.max(axis=2)
        result[kind].append({"image": reference.name,
                             "changedPixels": int((maximum > 0).sum()),
                             "changedPixelsOver5": int((maximum > 5).sum()),
                             "changedPixelsOver30": int((maximum > 30).sum()),
                             "meanAbsoluteChannelDifference": float(delta.mean())})
    results[tag] = result

(root / "pixel_comparisons.json").write_text(json.dumps(results, indent=2) + "\n")
final = results["city-life"]
assert len(final["allSourceComparisons"]) == 16
assert len(final["repeatComparisons"]) == 48
assert all(pair["changedPixels"] == 0 for pairs in final.values() for pair in pairs)
print("Passed: 16 full-source references and 48 repeated poses match every pixel.")
