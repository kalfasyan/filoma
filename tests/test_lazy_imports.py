import json
import subprocess
import sys

# Heavy / agentic dependencies that must NOT be loaded just by ``import filoma``.
# Roadmap reference: docs/roadmap/adoption.md §2.5 ("Lazy imports").
_AGENTIC_HEAVY_DEPS = (
    "pydantic_ai",
    "mcp",
    "mistralai",
    "google",
    "google.generativeai",
    "openai",
)
_DATA_HEAVY_DEPS = ("polars", "polars.internals", "PIL", "PIL.Image")


def run_python(code: str):
    """Run a short python snippet in a fresh interpreter and return stdout/stderr."""
    cmd = [sys.executable, "-c", code]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def _present_after(import_stmt: str, names: tuple) -> dict:
    """Return ``{name: bool}`` indicating which names are in ``sys.modules`` after ``import_stmt``."""
    code = f"""
import sys, json
{import_stmt}
names = {list(names)!r}
print(json.dumps({{n: n in sys.modules for n in names}}))
"""
    rc, out, err = run_python(code)
    assert rc == 0, f"{import_stmt!r} failed: {err}"
    return json.loads(out)


def test_import_filoma_does_not_load_heavy_deps():
    """``import filoma`` must stay cheap: no Polars/PIL or agentic stack pulled in."""
    present = _present_after("import filoma", _DATA_HEAVY_DEPS + _AGENTIC_HEAVY_DEPS)

    # Data-heavy modules
    assert not present.get("polars"), "polars should not be imported on filoma import"
    assert not present.get("PIL"), "PIL should not be imported on filoma import"

    # Agentic stack — see docs/roadmap/adoption.md §2.5
    for dep in _AGENTIC_HEAVY_DEPS:
        assert not present.get(dep), f"{dep!r} should not be imported on `import filoma`"


def test_import_filoma_filaraki_subpackage_stays_lazy():
    """Importing the ``filoma.filaraki`` *subpackage* should still not pull in pydantic-ai/mcp.

    Only calling ``get_agent()`` (which triggers ``from .agent import ...``)
    should drag the heavy agent stack in.
    """
    present = _present_after("import filoma.filaraki", _AGENTIC_HEAVY_DEPS)
    for dep in _AGENTIC_HEAVY_DEPS:
        assert not present.get(dep), f"{dep!r} should not be imported by `import filoma.filaraki`"


def test_get_agent_loads_pydantic_ai():
    """Importing ``filoma.filaraki.agent`` *does* pull in pydantic-ai.

    This proves the lazy boundary in the previous test has teeth: the heavy
    deps live behind ``filoma.filaraki.agent``, not behind the bare package.
    """
    present = _present_after(
        "from filoma.filaraki.agent import FilarakiAgent  # noqa: F401",
        ("pydantic_ai",),
    )
    assert present.get("pydantic_ai"), "pydantic_ai should load when filoma.filaraki.agent is imported"


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
