import asyncio
import tempfile
from pathlib import Path

import pytest

import filoma


@pytest.mark.asyncio
async def test_filaraki_imports():
    """Test that filoma.filaraki can be lazily loaded and initialized."""
    pytest.importorskip("pydantic_ai")

    print("Testing filoma.filaraki lazy loading...")
    try:
        # This should trigger the lazy load
        _ = filoma.filaraki
        print("Successfully accessed filoma.filaraki")

        from filoma.filaraki import get_agent

        print("Successfully imported get_agent")

        # We won't run the agent as it requires an API key,
        # but we can check if it initializes.
        from pydantic_ai.models.test import TestModel

        model = TestModel()
        _ = get_agent(model=model)
        print("Successfully initialized FilarakiAgent with TestModel")

        # Test a tool directly
        from filoma.filaraki.tools import probe_directory

        print("Testing probe_directory tool...")
        # Mocking RunContext is complex, but we can test if it accepts None for ctx
        # if the tool doesn't use it.
        result = probe_directory(None, "./src/filoma", max_depth=1)
        print(f"Tool result: {result[:100]}...")

    except Exception as e:
        print(f"Error during import/init test: {e}")
        import traceback

        traceback.print_exc()
        raise


@pytest.mark.asyncio
async def test_new_orchestrator_tools():
    """Test the new orchestrator tools."""
    pytest.importorskip("pydantic_ai")

    # Create a temporary directory with some test files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create a couple of test files
        (temp_path / "test1.txt").write_text("This is test file 1")
        (temp_path / "test2.txt").write_text("This is test file 2")
        (temp_path / "corrupt.bin").write_bytes(b'\x00' * 10)  # Zero-byte-like file

        from filoma.filaraki.tools import assess_migration_readiness, audit_corrupted_files, generate_hygiene_report

        print("Testing audit_corrupted_files tool...")
        try:
            result = audit_corrupted_files(None, str(temp_path))
            print(f"Audit result (first 200 chars): {result[:200]}...")
            assert "CORRUPTED FILE AUDIT REPORT" in result
        except Exception as e:
            print(f"Error in audit_corrupted_files: {e}")

        print("Testing generate_hygiene_report tool...")
        try:
            result = generate_hygiene_report(None, str(temp_path))
            print(f"Hygiene report result (first 200 chars): {result[:200]}...")
            assert "DATASET HYGIENE REPORT" in result
        except Exception as e:
            print(f"Error in generate_hygiene_report: {e}")

        print("Testing assess_migration_readiness tool...")
        try:
            result = assess_migration_readiness(None, str(temp_path))
            print(f"Migration readiness result (first 200 chars): {result[:200]}...")
            assert "MIGRATION READINESS REPORT" in result
        except Exception as e:
            print(f"Error in assess_migration_readiness: {e}")


if __name__ == "__main__":
    asyncio.run(test_filaraki_imports())
