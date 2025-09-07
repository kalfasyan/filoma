import json
import subprocess
import sys


def run_python(code: str):
    """Run a short python snippet in a fresh interpreter and return stdout/stderr."""
    cmd = [sys.executable, "-c", code]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def test_import_filoma_does_not_load_heavy_deps():
    # This test runs a fresh Python interpreter to avoid leakage from the test runner
    code = """
import sys
import importlib
import json
try:
    import filoma
except Exception as e:
    print(json.dumps({'error': str(e)}))
    raise
# Report whether heavy optional modules are present in sys.modules
present = {k: k in sys.modules for k in ('polars', 'polars.internals', 'PIL', 'PIL.Image')}
print(json.dumps(present))
"""

    rc, out, err = run_python(code)
    assert rc == 0, f"import filoma failed: {err}"
    present = json.loads(out)

    # Ensure optional heavy deps are NOT imported just by `import filoma`
    assert not present.get("polars", False), "polars should not be imported on filoma import"
    assert not present.get("PIL", False), "PIL should not be imported on filoma import"


def test_probe_to_df_triggers_polars_import():
    # Calling probe_to_df will attempt to build a Polars DataFrame; ensure polars then appears
    code = """
import sys
import json
from filoma import probe_to_df
# Use a benign path that will not error but will import polars when building df
import tempfile
p = tempfile.mkdtemp()
# Run probe_to_df in a try/except to ensure we can still inspect sys.modules
try:
    probe_to_df(p, to_pandas=False, enrich=False)
except Exception:
    pass
present = {k: k in sys.modules for k in ('polars', 'PIL')}
print(json.dumps(present))
"""

    rc, out, err = run_python(code)
    assert rc == 0, f"running probe_to_df snippet failed: {err}"
    present = json.loads(out)
    assert present.get("polars", False), "polars should be imported when probe_to_df is used"
