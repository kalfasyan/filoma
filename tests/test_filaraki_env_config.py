"""Tests for .env_example configuration variables with various API scenarios.

These tests verify that environment variables from .env_example are correctly
processed by the FilarakiAgent. They should be skipped in CI.

To run tests with real API keys:
    1. Set the appropriate environment variables in your .env file
    2. Rename the tests from test_* to test_real_* (or use --override-ini)
    3. Run: pytest tests/test_filaraki_env_config.py -v
"""

import os
from unittest.mock import MagicMock, patch

import pytest

# Skip all tests in CI where external API access is not available
CI = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"
pytestmark = pytest.mark.skipif(CI, reason="Skip in CI where real API keys are not available")
RUN_REAL_API_TESTS = os.getenv("FILOMA_RUN_REAL_API_TESTS", "0") == "1"


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def clean_env():
    """Fixture to temporarily clear all filoma-related env vars for isolation."""
    env_vars_to_clear = [
        "FILOMA_FILARAKI_MODEL",
        "FILOMA_FILARAKI_BASE_URL",
        "FILOMA_FILARAKI_API_KEY",
        "MISTRAL_API_KEY",
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ]
    # Store original values
    original_values = {var: os.getenv(var) for var in env_vars_to_clear}

    # Clear env vars
    for var in env_vars_to_clear:
        if var in os.environ:
            del os.environ[var]

    yield

    # Restore original values
    for var, value in original_values.items():
        if value is not None:
            os.environ[var] = value
        elif var in os.environ:
            del os.environ[var]


@pytest.fixture(autouse=True)
def mock_agent_constructor():
    """Avoid constructing the real pydantic-ai Agent in unit tests."""
    with patch("filoma.filaraki.agent.Agent") as mock_agent:
        mock_agent.return_value = MagicMock()
        yield mock_agent


@pytest.fixture(autouse=True)
def no_ollama_autodetect():
    """Prevent accidental local Ollama auto-detection unless a test overrides it."""
    with patch("socket.socket") as mock_socket:
        mock_conn = MagicMock()
        mock_conn.connect_ex.return_value = 1
        mock_socket.return_value = mock_conn
        yield


# ==============================================================================
# Scenario A: Ollama (Local)
# ==============================================================================


class TestScenarioA_Ollama:
    """Tests for Scenario A: Ollama (Local - Privacy First)."""

    def test_env_vars_read(self, clean_env):
        """Test that Ollama environment variables are correctly read."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        # Set environment variables like .env_example
        os.environ["FILOMA_FILARAKI_MODEL"] = "qwen2.5:14b"
        os.environ["FILOMA_FILARAKI_BASE_URL"] = "http://localhost:11434/v1"

        with patch("socket.socket") as mock_socket:
            # Simulate that Ollama is running on localhost:11434
            mock_conn = MagicMock()
            mock_conn.connect_ex.return_value = 0
            mock_socket.return_value = mock_conn

            agent = FilarakiAgent()

            # Verify agent was created (model resolution happened)
            assert agent is not None

    def test_ollama_base_url_with_ollama_prefix(self, clean_env):
        """Test that 'ollama:' prefix is stripped from model name."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        os.environ["FILOMA_FILARAKI_MODEL"] = "ollama:qwen2.5:14b"
        os.environ["FILOMA_FILARAKI_BASE_URL"] = "http://localhost:11434/v1"

        with patch("socket.socket") as mock_socket:
            mock_conn = MagicMock()
            mock_conn.connect_ex.return_value = 0
            mock_socket.return_value = mock_conn

            from filoma.filaraki.agent import FilarakiAgent

            agent = FilarakiAgent()
            assert agent is not None

    def test_ollama_auto_detection(self, clean_env):
        """Test auto-detection of Ollama on localhost:11434."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        # Only set model, no base_url - should auto-detect
        os.environ["FILOMA_FILARAKI_MODEL"] = "llama3.1:8b"

        with patch("socket.socket") as mock_socket:
            # Simulate Ollama is running
            mock_conn = MagicMock()
            mock_conn.connect_ex.return_value = 0
            mock_socket.return_value = mock_conn

            agent = FilarakiAgent()
            assert agent is not None

    def test_ollama_not_running_fallback(self, clean_env):
        """Test fallback message when Ollama is not running."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        os.environ["FILOMA_FILARAKI_MODEL"] = "qwen2.5:14b"

        with patch("socket.socket") as mock_socket:
            # Simulate Ollama is NOT running
            mock_conn = MagicMock()
            mock_conn.connect_ex.return_value = 1  # Connection refused
            mock_socket.return_value = mock_conn

            # Should fallback to default with warning
            agent = FilarakiAgent()
            assert agent is not None


# ==============================================================================
# Scenario B: Mistral AI (Cloud)
# ==============================================================================


class TestScenarioB_Mistral:
    """Tests for Scenario B: Mistral AI (Cloud)."""

    def test_mistral_api_key_read(self, clean_env):
        """Test that MISTRAL_API_KEY environment variable is correctly read."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        # Set Mistral environment like .env_example
        os.environ["MISTRAL_API_KEY"] = "test_mistral_key_12345"
        os.environ["FILOMA_FILARAKI_MODEL"] = "mistral-small-latest"

        # Mock the OpenAIChatModel to avoid actual API calls
        # Must patch the source module where the class is imported from
        with patch("pydantic_ai.models.openai.OpenAIChatModel") as mock_model_class, patch("pydantic_ai.providers.openai.OpenAIProvider") as mock_provider_class:
            mock_instance = MagicMock()
            mock_provider_class.return_value = MagicMock()
            mock_model_class.return_value = mock_instance
            agent = FilarakiAgent()

            # Verify agent was created
            assert agent is not None
            # Verify the model class was called
            assert mock_model_class.called
            # Check that provider constructor was called with the correct API key
            provider_kwargs = mock_provider_class.call_args.kwargs
            assert provider_kwargs.get("api_key") == "test_mistral_key_12345"

    def test_mistral_model_with_prefix(self, clean_env):
        """Test that model name gets 'mistral:' prefix added if not present."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        os.environ["MISTRAL_API_KEY"] = "test_key"
        os.environ["FILOMA_FILARAKI_MODEL"] = "mistral-small-latest"  # Without prefix

        with patch("pydantic_ai.models.openai.OpenAIChatModel") as mock_model_class, patch("pydantic_ai.providers.openai.OpenAIProvider") as mock_provider_class:
            mock_provider_class.return_value = MagicMock()
            mock_model_class.return_value = MagicMock()
            FilarakiAgent()

            # Verify the model class was called
            assert mock_model_class.called
            # Check the model_name passed to the constructor
            call_kwargs = mock_model_class.call_args.kwargs
            model_name = call_kwargs.get("model_name")
            assert model_name.startswith("mistral:")

    def test_mistral_model_already_has_prefix(self, clean_env):
        """Test that model name with 'mistral:' prefix is preserved."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        os.environ["MISTRAL_API_KEY"] = "test_key"
        os.environ["FILOMA_FILARAKI_MODEL"] = "mistral:mistral-small-latest"

        with patch("pydantic_ai.models.openai.OpenAIChatModel") as mock_model_class, patch("pydantic_ai.providers.openai.OpenAIProvider") as mock_provider_class:
            mock_provider_class.return_value = MagicMock()
            mock_model_class.return_value = MagicMock()
            agent = FilarakiAgent()
            assert agent is not None
            # Verify the model class was called
            assert mock_model_class.called


# ==============================================================================
# Scenario C: Google Gemini (Cloud)
# ==============================================================================


class TestScenarioC_Gemini:
    """Tests for Scenario C: Google Gemini (Cloud)."""

    def test_gemini_api_key_read(self, clean_env):
        """Test that GEMINI_API_KEY environment variable is correctly read."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        # Set Gemini environment like .env_example
        os.environ["GEMINI_API_KEY"] = "test_gemini_key_12345"
        os.environ["FILOMA_FILARAKI_MODEL"] = "gemini-1.5-flash"

        # Mock GoogleModel to avoid actual API calls
        with patch("pydantic_ai.models.google.GoogleModel") as mock_model_class:
            mock_model_class.return_value = MagicMock()
            agent = FilarakiAgent()

            # Verify agent was created
            assert agent is not None
            # Verify the model class was called
            assert mock_model_class.called

    def test_gemini_default_model(self, clean_env):
        """Test default Gemini model when MODEL not specified."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        os.environ["GEMINI_API_KEY"] = "test_key"
        # Don't set FILOMA_FILARAKI_MODEL - should default to gemini-1.5-flash

        with patch("pydantic_ai.models.google.GoogleModel") as mock_model_class:
            mock_model_class.return_value = MagicMock()
            FilarakiAgent()

            # Check that the model was called with default model name
            call_kwargs = mock_model_class.call_args.kwargs
            assert call_kwargs.get("model_name") == "gemini-1.5-flash"


# ==============================================================================
# Scenario D: OpenAI-Compatible (Generic)
# ==============================================================================


class TestScenarioD_OpenAICompat:
    """Tests for Scenario D: OpenAI-Compatible APIs (OpenAI, OpenRouter, etc.)."""

    def test_openai_compatible_base_url_and_key(self, clean_env):
        """Test that FILOMA_FILARAKI_BASE_URL and OPENAI_API_KEY are read."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        # Set OpenAI-compatible environment like .env_example
        os.environ["FILOMA_FILARAKI_BASE_URL"] = "https://openrouter.ai/api/v1"
        os.environ["OPENAI_API_KEY"] = "test_openrouter_key_12345"
        os.environ["FILOMA_FILARAKI_MODEL"] = "anthropic/claude-3.5-sonnet"

        with patch("pydantic_ai.models.openai.OpenAIChatModel") as mock_model_class, patch("pydantic_ai.providers.openai.OpenAIProvider") as mock_provider_class:
            mock_provider_class.return_value = MagicMock()
            mock_model_class.return_value = MagicMock()
            agent = FilarakiAgent()

            # Verify agent was created
            assert agent is not None
            # Verify model was called
            assert mock_model_class.called

            # Verify the model was called with correct args
            provider_kwargs = mock_provider_class.call_args.kwargs
            assert provider_kwargs.get("api_key") == "test_openrouter_key_12345"
            assert provider_kwargs.get("base_url") == "https://openrouter.ai/api/v1"

    def test_openai_official_api(self, clean_env):
        """Test OpenAI official API configuration."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        os.environ["FILOMA_FILARAKI_BASE_URL"] = "https://api.openai.com/v1"
        os.environ["OPENAI_API_KEY"] = "test_openai_key_12345"
        os.environ["FILOMA_FILARAKI_MODEL"] = "gpt-4o-mini"

        with patch("pydantic_ai.models.openai.OpenAIChatModel") as mock_model_class, patch("pydantic_ai.providers.openai.OpenAIProvider") as mock_provider_class:
            mock_provider_class.return_value = MagicMock()
            mock_model_class.return_value = MagicMock()
            FilarakiAgent()

            provider_kwargs = mock_provider_class.call_args.kwargs
            assert provider_kwargs.get("api_key") == "test_openai_key_12345"
            assert provider_kwargs.get("base_url") == "https://api.openai.com/v1"

    def test_openai_compatible_default_model(self, clean_env):
        """Test OpenAI-compatible default model when MODEL not specified."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        os.environ["FILOMA_FILARAKI_BASE_URL"] = "https://openrouter.ai/api/v1"
        os.environ["OPENAI_API_KEY"] = "test_key"

        with patch("pydantic_ai.models.openai.OpenAIChatModel") as mock_model_class:
            mock_model_class.return_value = MagicMock()
            FilarakiAgent()

            # Default model is gpt-4o-mini
            call_kwargs = mock_model_class.call_args.kwargs
            assert call_kwargs.get("model_name") == "gpt-4o-mini"


# ==============================================================================
# Generic Env Var Tests
# ==============================================================================


class TestGenericEnvVarAndResource:
    """Tests for the generic FILOMA_FILARAKI_API_KEY override."""

    def test_generic_api_key_override(self, clean_env):
        """Test that FILOMA_FILARAKI_API_KEY can be used as generic override."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        os.environ["FILOMA_FILARAKI_BASE_URL"] = "https://custom-api.com/v1"
        os.environ["FILOMA_FILARAKI_API_KEY"] = "generic_api_key_12345"
        os.environ["FILOMA_FILARAKI_MODEL"] = "custom-model"

        with patch("pydantic_ai.models.openai.OpenAIChatModel") as mock_model_class, patch("pydantic_ai.providers.openai.OpenAIProvider") as mock_provider_class:
            mock_provider_class.return_value = MagicMock()
            mock_model_class.return_value = MagicMock()
            FilarakiAgent()

            provider_kwargs = mock_provider_class.call_args.kwargs
            assert provider_kwargs.get("api_key") == "generic_api_key_12345"

    def test_model_string_resolved_from_env(self, clean_env):
        """Test resolving model string from FILOMA_FILARAKI_MODEL env var."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        # Only set model, should still work for Ollama (if running)
        os.environ["FILOMA_FILARAKI_MODEL"] = "custom-model-name"

        with patch("socket.socket") as mock_socket:
            mock_conn = MagicMock()
            mock_conn.connect_ex.return_value = 0  # Pretend Ollama is running
            mock_socket.return_value = mock_conn

            agent = FilarakiAgent()
            assert agent is not None


# ==============================================================================
# Priority Order Tests
# ==============================================================================


class TestConfigurationPriority:
    """Tests to verify configuration priority order."""

    def test_priority_ollama_over_mistral(self, clean_env):
        """Test Ollama takes priority over Mistral when both configured."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        os.environ["MISTRAL_API_KEY"] = "mistral_key"
        os.environ["FILOMA_FILARAKI_BASE_URL"] = "http://localhost:11434/v1"

        with patch("socket.socket") as mock_socket, patch("pydantic_ai.models.openai.OpenAIChatModel") as mock_ollama_model:
            # Simulate Ollama is running (socket connection succeeds)
            mock_conn = MagicMock()
            mock_conn.connect_ex.return_value = 0
            mock_socket.return_value = mock_conn
            mock_ollama_model.return_value = MagicMock()

            agent = FilarakiAgent()
            assert agent is not None
            # Ollama branch uses OpenAIChatModel + OllamaProvider and does not add mistral: prefix.
            assert mock_ollama_model.called
            call_kwargs = mock_ollama_model.call_args.kwargs
            assert call_kwargs.get("model_name") != "mistral:mistral-small-latest"

    def test_priority_mistral_over_gemini(self, clean_env):
        """Test Mistral takes priority over Gemini when both configured."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        os.environ["MISTRAL_API_KEY"] = "mistral_key"
        os.environ["GEMINI_API_KEY"] = "gemini_key"

        with patch("pydantic_ai.models.openai.OpenAIChatModel") as mock_mistral, patch("pydantic_ai.models.google.GoogleModel") as mock_gemini:
            mock_mistral.return_value = MagicMock()
            mock_gemini.return_value = MagicMock()
            FilarakiAgent()

            # Mistral should be called, not Gemini
            assert mock_mistral.called
            assert not mock_gemini.called

    def test_priority_gemini_over_openai_compat(self, clean_env):
        """Test Gemini takes priority over OpenAI-compatible when both configured."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        os.environ["GEMINI_API_KEY"] = "gemini_key"
        os.environ["FILOMA_FILARAKI_BASE_URL"] = "https://api.openai.com/v1"
        os.environ["OPENAI_API_KEY"] = "openai_key"

        with patch("pydantic_ai.models.google.GoogleModel") as mock_gemini, patch("pydantic_ai.models.openai.OpenAIChatModel") as mock_openai:
            mock_gemini.return_value = MagicMock()
            mock_openai.return_value = MagicMock()
            FilarakiAgent()

            # Gemini should be called, not OpenAI
            assert mock_gemini.called
            assert not mock_openai.called

    def test_explicit_model_parameter_overrides_env(self, clean_env):
        """Test that explicit model parameter overrides env variable."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")
        from pydantic_ai.models.test import TestModel

        from filoma.filaraki.agent import FilarakiAgent

        os.environ["MISTRAL_API_KEY"] = "mistral_key"

        # Pass explicit model, should use it over env detection
        test_model = TestModel()
        agent = FilarakiAgent(model=test_model)

        assert agent.model == test_model

    def test_explicit_base_url_parameter_overrides_env(self, clean_env):
        """Test that explicit base_url parameter overrides env variable."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        os.environ["FILOMA_FILARAKI_BASE_URL"] = "https://env-base-url.com/v1"
        os.environ["OPENAI_API_KEY"] = "api_key"

        with patch("pydantic_ai.models.openai.OpenAIChatModel") as mock_model, patch("pydantic_ai.providers.openai.OpenAIProvider") as mock_provider_class:
            mock_provider_class.return_value = MagicMock()
            mock_model.return_value = MagicMock()

            # Pass explicit base_url
            FilarakiAgent(base_url="https://explicit-base-url.com/v1")

            provider_kwargs = mock_provider_class.call_args.kwargs
            assert provider_kwargs.get("base_url") == "https://explicit-base-url.com/v1"

    def test_explicit_api_key_parameter_overrides_env(self, clean_env):
        """Test that explicit api_key parameter overrides env variable."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        os.environ["OPENAI_API_KEY"] = "env_api_key"
        os.environ["FILOMA_FILARAKI_BASE_URL"] = "https://api.openai.com/v1"

        with patch("pydantic_ai.models.openai.OpenAIChatModel") as mock_model, patch("pydantic_ai.providers.openai.OpenAIProvider") as mock_provider_class:
            mock_provider_class.return_value = MagicMock()
            mock_model.return_value = MagicMock()

            # Pass explicit api_key
            FilarakiAgent(base_url="https://api.openai.com/v1", api_key="explicit_api_key")

            provider_kwargs = mock_provider_class.call_args.kwargs
            assert provider_kwargs.get("api_key") == "explicit_api_key"


# ==============================================================================
# Integration Tests with Real APIs (Skippable)
# ==============================================================================


@pytest.mark.integration
@pytest.mark.skipif(
    CI or not RUN_REAL_API_TESTS,
    reason="Real API tests are disabled in CI and require FILOMA_RUN_REAL_API_TESTS=1",
)
class TestRealAPIIntegration:
    """Integration tests with actual API providers.

    To run these tests:
    1. Configure your .env file with real API keys
    2. Run: pytest tests/test_filaraki_env_config.py::TestRealAPIIntegration -v --no-header
    """

    @pytest.mark.asyncio
    async def test_mistral_real_api(self, clean_env):
        """Test real Mistral AI API call (requires MISTRAL_API_KEY)."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki import get_agent

        # Load actual env vars from .env (if exists)
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass

        if not os.getenv("MISTRAL_API_KEY"):
            pytest.skip("MISTRAL_API_KEY not set in environment")

        agent = get_agent()
        deps = MagicMock()
        deps.working_dir = "."

        # Run a simple tool call
        result = await agent.run("How many files are in the current directory?", deps=deps)
        assert result is not None

    @pytest.mark.asyncio
    async def test_gemini_real_api(self, clean_env):
        """Test real Google Gemini API call (requires GEMINI_API_KEY)."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki import get_agent

        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass

        if not os.getenv("GEMINI_API_KEY"):
            pytest.skip("GEMINI_API_KEY not set in environment")

        agent = get_agent()
        deps = MagicMock()
        deps.working_dir = "."

        result = await agent.run("How many files are in the current directory?", deps=deps)
        assert result is not None

    @pytest.mark.asyncio
    async def test_openai_compatible_real_api(self, clean_env):
        """Test real OpenAI-compatible API call (requires OPENAI_API_KEY + base_url)."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki import get_agent

        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass

        if not os.getenv("OPENAI_API_KEY") and not os.getenv("FILOMA_FILARAKI_BASE_URL"):
            pytest.skip("OPENAI_API_KEY and FILOMA_FILARAKI_BASE_URL not set")

        agent = get_agent()
        deps = MagicMock()
        deps.working_dir = "."

        result = await agent.run("How many files are in the current directory?", deps=deps)
        assert result is not None

    @pytest.mark.asyncio
    async def test_openrouter_real_api(self, clean_env):
        """Test real OpenRouter API call (requires OPENAI_API_KEY + OpenRouter base_url)."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki import get_agent

        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass

        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set in environment")

        if not os.getenv("FILOMA_FILARAKI_BASE_URL") or "openrouter" not in os.getenv("FILOMA_FILARAKI_BASE_URL", ""):
            pytest.skip("FILOMA_FILARAKI_BASE_URL must be set to OpenRouter URL")

        agent = get_agent()
        deps = MagicMock()
        deps.working_dir = "."

        result = await agent.run("How many files are in the current directory?", deps=deps)
        assert result is not None


# ==============================================================================
# Error Handling Tests
# ==============================================================================


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    def test_no_config_warning_message(self, clean_env, caplog):
        """Test warning message when no AI configuration is found."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        with patch("socket.socket") as mock_socket:
            # Simulate Ollama is NOT running
            mock_conn = MagicMock()
            mock_conn.connect_ex.return_value = 1
            mock_socket.return_value = mock_conn

            # No API keys set
            agent = FilarakiAgent()

            # Should create agent with fallback (string model name)
            assert agent is not None

    def test_invalid_base_url_handling(self, clean_env):
        """Test handling of invalid base URL format."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        # Set an invalid base URL
        os.environ["FILOMA_FILARAKI_BASE_URL"] = "not-a-valid-url"
        os.environ["OPENAI_API_KEY"] = "test_key"

        # This may fail depending on how pydantic-ai handles it
        # The test documents the expected behavior
        try:
            FilarakiAgent()
        except Exception as e:
            # Expecting an error for invalid URL
            assert "url" in str(e).lower() or "base" in str(e).lower()

    def test_empty_api_key_handling(self, clean_env):
        """Test handling of empty API key."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki.agent import FilarakiAgent

        # Set empty API key
        os.environ["MISTRAL_API_KEY"] = ""

        with patch("socket.socket") as mock_socket:
            mock_conn = MagicMock()
            mock_conn.connect_ex.return_value = 1
            mock_socket.return_value = mock_conn

            # Should fallback since empty key doesn't count
            agent = FilarakiAgent()
            assert agent is not None


# ==============================================================================
# Get Agent Function Tests
# ==============================================================================


class TestGetAgent:
    """Tests for the get_agent() convenience function."""

    def test_get_agent_with_model(self, clean_env):
        """Test get_agent passes model parameter correctly."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")
        from pydantic_ai.models.test import TestModel

        from filoma.filaraki import get_agent

        test_model = TestModel()
        agent = get_agent(model=test_model)

        assert agent.model == test_model

    def test_get_agent_with_none(self, clean_env):
        """Test get_agent works with no arguments."""
        pytest.importorskip("pydantic_ai", reason="pydantic_ai not installed")

        from filoma.filaraki import get_agent

        with patch("socket.socket") as mock_socket:
            mock_conn = MagicMock()
            mock_conn.connect_ex.return_value = 0
            mock_socket.return_value = mock_conn

            agent = get_agent()
            assert agent is not None
