import asyncio

import pytest

import filoma


@pytest.mark.asyncio
async def test_brain_imports():
    """Test that filoma.brain can be lazily loaded and initialized."""
    pytest.importorskip("pydantic_ai")

    print("Testing filoma.brain lazy loading...")
    try:
        # This should trigger the lazy load
        _ = filoma.brain
        print("Successfully accessed filoma.brain")

        from filoma.brain import get_agent

        print("Successfully imported get_agent")

        # We won't run the agent as it requires an API key,
        # but we can check if it initializes.
        from pydantic_ai.models.test import TestModel

        model = TestModel()
        _ = get_agent(model=model)
        print("Successfully initialized FilomaAgent with TestModel")

        # Test a tool directly
        from filoma.brain.tools import probe_directory

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


if __name__ == "__main__":
    asyncio.run(test_brain_imports())
