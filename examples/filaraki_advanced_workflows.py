"""Examples of advanced Filoma Filaraki workflows using the new orchestrator tools."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from loguru import logger

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from filoma.filaraki import get_agent


async def main():
    """Run examples of the new Filoma Filaraki orchestrator tools."""
    # Configure loguru for clean output
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )

    # Check for configuration
    has_mistral = bool(os.getenv("MISTRAL_API_KEY"))
    has_custom = bool(os.getenv("FILOMA_FILARAKI_MODEL"))

    if not (has_mistral or has_custom):
        logger.warning("--- Filoma Filaraki Advanced Workflows: Setup Required ---")
        logger.info("To run this example, please create a .env file (see .env_example) or set one of the following environment variables:")
        logger.info("\n1. Cloud (Mistral - Recommended Default):")
        logger.info("   export MISTRAL_API_KEY='your-key'")
        logger.info("\n2. Local (Ollama):")
        logger.info("   export FILOMA_FILARAKI_MODEL='llama3.1:8b'")
        logger.info("   export FILOMA_FILARAKI_BASE_URL='http://localhost:11434/v1'")
        logger.info("\nSee docs/guides/filaraki.md for more details.")
        return

    # Create a temporary test directory with some sample files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create some test files
        (temp_path / "document1.txt").write_text("This is a test document with some content.")
        (temp_path / "document2.txt").write_text("This is another test document with different content.")
        (temp_path / "image1.jpg").write_bytes(b"\x00" * 100)  # Dummy JPEG-like file
        (temp_path / "image2.png").write_bytes(b"\x00" * 50)  # Dummy PNG-like file
        (temp_path / "empty_file.bin").write_bytes(b"")  # Zero-byte file
        (temp_path / "large_file.dat").write_bytes(b"x" * 1000)  # Larger file

        # Create a subdirectory
        subdir = temp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("This is a nested file.")

        # Initialize the agent
        agent = get_agent()

        logger.info("--- Filoma Filaraki Advanced Workflows ---")
        logger.info(f"Using model: {agent.model}")
        logger.info(f"Working with test directory: {temp_path}")

        # Example 1: Corrupted File Audit
        logger.info("\n--- Example 1: Corrupted File Audit ---")
        try:
            response = await agent.run(f"Run a corrupted file audit on {temp_path} and provide a structured report")
            logger.info(f"Agent response: {response}")
        except Exception as e:
            logger.error(f"Error: {e}")

        # Example 2: Dataset Hygiene Report
        logger.info("\n--- Example 2: Dataset Hygiene Report ---")
        try:
            response = await agent.run(f"Generate a dataset hygiene report for {temp_path}")
            logger.info(f"Agent response: {response}")
        except Exception as e:
            logger.error(f"Error: {e}")

        # Example 3: Migration Readiness Assessment
        logger.info("\n--- Example 3: Migration Readiness Assessment ---")
        try:
            response = await agent.run(f"Assess the migration readiness of {temp_path}")
            logger.info(f"Agent response: {response}")
        except Exception as e:
            logger.error(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
