"""Profiling must work where the Unix user database (grp, pwd) is missing, as on Windows."""

import subprocess
import sys
import textwrap


def test_file_profiler_imports_and_reports_owner_without_grp_and_pwd(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("hello")

    script = textwrap.dedent(
        f"""
        import sys
        # Setting a module to None makes `import` raise ImportError, as on Windows.
        sys.modules["grp"] = None
        sys.modules["pwd"] = None

        from filoma.files import FileProfiler

        report = FileProfiler().probe({str(target)!r})
        assert report["owner"] is None, report["owner"]
        assert report["group"] is None, report["group"]
        """
    )
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)

    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
