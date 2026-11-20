import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SAMPLE = ROOT / "data" / "sample"


@pytest.fixture(scope="session")
def run_output(tmp_path_factory):
    from creditunion.pipeline import run

    out = tmp_path_factory.mktemp("out")
    return run(SAMPLE, out), out
