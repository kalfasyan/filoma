"""Tests for DirectoryProfilerConfig validation logic."""

import pytest

from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig


class TestSearchBackendValidation:
    """Test that search_backend parameter correctly enables backends."""

    def test_search_backend_fd_with_threads(self, monkeypatch):
        """Setting search_backend='fd' should allow threads parameter."""
        monkeypatch.setattr("filoma.directories.directory_profiler.FD_AVAILABLE", True)

        # This should NOT raise an error
        config = DirectoryProfilerConfig(
            search_backend="fd",
            threads=4,
            show_progress=False,
        )
        profiler = DirectoryProfiler(config)
        assert profiler.use_fd is True
        assert profiler.threads == 4

    def test_search_backend_rust_rejects_threads(self):
        """Setting search_backend='rust' should reject threads parameter."""
        with pytest.raises(ValueError, match="threads.*only applies"):
            DirectoryProfilerConfig(
                search_backend="rust",
                threads=4,
            )

    def test_search_backend_auto_with_defaults(self):
        """search_backend='auto' with default params should work."""
        # This should NOT raise an error
        config = DirectoryProfilerConfig(
            search_backend="auto",
            show_progress=True,
        )
        # Should not raise during initialization
        assert config.search_backend == "auto"

    def test_use_fd_true_with_threads(self, monkeypatch):
        """Explicit use_fd=True should allow threads parameter."""
        monkeypatch.setattr("filoma.directories.directory_profiler.FD_AVAILABLE", True)

        config = DirectoryProfilerConfig(
            use_fd=True,
            threads=8,
            show_progress=False,
        )
        profiler = DirectoryProfiler(config)
        assert profiler.use_fd is True
        assert profiler.threads == 8


class TestNetworkParameterValidation:
    """Test validation of network-related parameters."""

    def test_default_network_params_without_async(self):
        """Default network parameters should be allowed without use_async."""
        # This should NOT raise an error (using defaults)
        config = DirectoryProfilerConfig(
            search_backend="auto",
            use_async=False,
            # Not setting network params - they use defaults
        )
        assert config.network_concurrency == 192
        assert config.network_timeout_ms == 20000
        assert config.network_retries == 0

    def test_custom_network_params_without_async_raises(self):
        """Custom network parameters should raise error without use_async=True."""
        with pytest.raises(ValueError, match="Network tuning parameters only apply"):
            DirectoryProfilerConfig(
                use_async=False,
                network_concurrency=32,  # Custom value
            )

    def test_custom_network_params_with_async(self, monkeypatch):
        """Custom network parameters should work with use_async=True."""
        monkeypatch.setattr("filoma.directories.directory_profiler.RUST_AVAILABLE", True)
        monkeypatch.setattr("filoma.directories.directory_profiler.RUST_ASYNC_AVAILABLE", True)

        config = DirectoryProfilerConfig(
            use_async=True,
            network_concurrency=32,
            network_timeout_ms=1000,
            network_retries=2,
            show_progress=False,
        )
        profiler = DirectoryProfiler(config)
        assert profiler.network_concurrency == 32
        assert profiler.network_timeout_ms == 1000
        assert profiler.network_retries == 2

    def test_search_backend_fd_with_default_network_params(self, monkeypatch):
        """search_backend='fd' should work with default network params."""
        monkeypatch.setattr("filoma.directories.directory_profiler.FD_AVAILABLE", True)

        # This should NOT raise (defaults are fine)
        config = DirectoryProfilerConfig(
            search_backend="fd",
            show_progress=False,
        )
        profiler = DirectoryProfiler(config)
        assert profiler.use_fd is True


class TestInvalidSearchBackend:
    """Test validation of search_backend values."""

    def test_invalid_search_backend_raises(self):
        """Invalid search_backend value should raise ValueError."""
        with pytest.raises(ValueError, match="search_backend must be one of"):
            DirectoryProfilerConfig(search_backend="invalid")


class TestCommonUseCases:
    """Test common real-world usage patterns."""

    def test_simple_auto_backend(self):
        """Most basic usage - just search_backend='auto'."""
        config = DirectoryProfilerConfig(
            search_backend="auto",
        )
        # Should not raise
        assert config.search_backend == "auto"

    def test_fd_backend_with_threads_and_progress(self, monkeypatch):
        """Common fd usage pattern."""
        monkeypatch.setattr("filoma.directories.directory_profiler.FD_AVAILABLE", True)

        config = DirectoryProfilerConfig(
            search_backend="fd",
            threads=4,
            show_progress=True,
        )
        profiler = DirectoryProfiler(config)
        assert profiler.use_fd is True
        assert profiler.threads == 4

    def test_async_for_network_storage(self, monkeypatch):
        """Common async usage for network filesystems."""
        monkeypatch.setattr("filoma.directories.directory_profiler.RUST_AVAILABLE", True)
        monkeypatch.setattr("filoma.directories.directory_profiler.RUST_ASYNC_AVAILABLE", True)

        config = DirectoryProfilerConfig(
            use_async=True,
            network_concurrency=64,
            network_timeout_ms=5000,
            show_progress=True,
        )
        profiler = DirectoryProfiler(config)
        assert profiler.use_async is True
        assert profiler.network_concurrency == 64

    def test_rust_parallel_local_storage(self, monkeypatch):
        """Common rust parallel usage for local storage."""
        monkeypatch.setattr("filoma.directories.directory_profiler.RUST_AVAILABLE", True)
        monkeypatch.setattr("filoma.directories.directory_profiler.RUST_PARALLEL_AVAILABLE", True)

        config = DirectoryProfilerConfig(
            search_backend="rust",
            use_parallel=True,
            parallel_threshold=500,
            show_progress=False,
        )
        profiler = DirectoryProfiler(config)
        assert profiler.use_rust is True
        assert profiler.use_parallel is True
