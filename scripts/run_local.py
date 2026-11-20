"""Run the full Member 360 flow on the sample data and print a summary.

    python scripts/run_local.py [data/sample] [output]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from creditunion.pipeline import run

if __name__ == "__main__":
    data = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "sample"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "output"
    print(json.dumps(run(data, out), indent=2, default=str))
    print(f"\nwrote {', '.join(sorted(p.name for p in out.iterdir()))} to {out}/")
