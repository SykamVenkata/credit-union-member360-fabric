"""Print the PII-safe copilot brief and chat messages for one member (run run_local.py first).

    python scripts/brief.py M000042 "Member asks about lowering their car payment"
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from creditunion.copilot import build_messages, member_brief

if __name__ == "__main__":
    m360 = pd.read_csv(ROOT / "output" / "member_360.csv")
    gid = sys.argv[1] if len(sys.argv) > 1 else m360.sort_values("churn_score").golden_id.iloc[-1]
    row = m360.set_index("golden_id").loc[gid].to_dict() | {"golden_id": gid}
    brief = member_brief(row, row.get("churn_score"), row.get("next_best_product") or None)
    question = sys.argv[2] if len(sys.argv) > 2 else "What should I mention to this member today?"
    print(json.dumps(build_messages(brief, question), indent=2))
