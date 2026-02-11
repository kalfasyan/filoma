"""POC for filoma brain."""

import asyncio
import os
import sys

from loguru import logger

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from filoma.brain import get_agent


async def main():
    """Run the Filoma Brain POC."""
    # Configure loguru for clean output
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )

    # Check for configuration
    has_mistral = bool(os.getenv("MISTRAL_API_KEY"))
    has_custom = bool(os.getenv("FILOMA_BRAIN_MODEL"))

    if not (has_mistral or has_custom):
        logger.warning("--- Filoma Brain POC: Setup Required ---")
        logger.info("To run this POC, please create a .env file (see .env_example) or set one of the following environment variables:")
        logger.info("\n1. Cloud (Mistral - Recommended Default):")
        logger.info("   export MISTRAL_API_KEY='your-key'")
        logger.info("\n2. Local (Ollama):")
        logger.info("   export FILOMA_BRAIN_MODEL='llama3.1:8b'")
        logger.info("   export FILOMA_BRAIN_BASE_URL='http://localhost:11434/v1'")
        logger.info("\nSee docs/guides/brain.md for more details.")
        return

    # Initialize the agent.
    # It will automatically pick up the best available configuration from .env or environment.
    agent = get_agent()

    logger.info("--- Filoma Brain POC ---")
    logger.info(f"Using model: {agent.model}")

    # Example 1: Summarize a directory
    path = "./src/filoma"
    logger.info(f"Asking: What can you tell me about the files in {path}?")
    try:
        response = await agent.run(f"Summarize the file distribution in {path}")
        logger.info(f"Agent response: {response}")
    except Exception as e:
        logger.error(f"Error: {e}")

    # Example 2: Find duplicates
    path = "./tests"
    logger.info(f"Asking: Are there any duplicate files in {path}?")
    try:
        response = await agent.run(f"Check for duplicates in {path}")
        logger.info(f"Agent response: {response}")
    except Exception as e:
        logger.error(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
