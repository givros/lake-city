"""Read-only pixel comparisons for the focused promotion regression."""
import json
from pathlib import Path
import numpy as np
from PIL import Image

base = Path(__file__).resolve().parents[2] / 'renders' / 'vehicle-promotion'
report_path = Path(__file__).resolve().parents[1] / 'vehicle_promotion_validation.json'
report = json.loads(report_path.read_text())
pairs = []
for region in ('downtown', 'lake'):
    reference = np.asarray(Image.open(base / (region + '-frozen.png')).convert('RGB')).astype(np.int16)
    for suffix in ('repeat', 'all-source'):
        image = np.asarray(Image.open(base / (region + '-frozen-' + suffix + '.png')).convert('RGB')).astype(np.int16)
        delta = np.abs(image - reference)
        pairs.append({'region': region, 'comparison': suffix, 'changedPixels': int(np.any(delta > 0, axis=2).sum()), 'maximumChannelDifference': int(delta.max())})
passed = all(p['changedPixels'] == 0 for p in pairs)
report['checks']['frozenPixelStability'] = {'status': 'passed' if passed else 'failed', 'scope': 'Two affected representative street poses, repeated and compared against all-source frustum-culling-disabled renders; simulation paused', 'pairs': pairs}
a = np.asarray(Image.open(base / 'downtown-live-a.png').convert('RGB')).astype(np.int16)
b = np.asarray(Image.open(base / 'downtown-live-b.png').convert('RGB')).astype(np.int16)
changed = int(np.any(np.abs(a-b) > 5, axis=2).sum())
report['checks']['visibleMotionPixels'] = {'status': 'passed' if changed > 0 else 'failed', 'seconds': 1, 'camera': 'Identical downtown street pose', 'changedPixelsOver5': changed}
report_path.write_text(json.dumps(report, indent=2) + '\n')
assert passed, pairs
assert changed > 0
print(json.dumps({'pairs': pairs, 'motionChangedPixelsOver5': changed}))
