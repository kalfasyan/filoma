"""Test the high-level convenience API as documented in README and docs.

This test module ensures that the user-facing API examples in documentation
actually work. It tests the convenience functions and methods that users
interact with, not just the low-level profiler objects.
"""

import tempfile
from pathlib import Path

import pytest

from filoma import probe, probe_file, probe_image, probe_to_df


@pytest.fixture
def sample_directory():
    """Create a temporary directory with sample files for testing."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)

        # Create directory structure
        (base / "src").mkdir()
        (base / "docs").mkdir()
        (base / "tests").mkdir()

        # Create sample files
        (base / "README.md").write_text("# Test Project\n\nSample readme.")
        (base / "src" / "main.py").write_text("print('hello')")
        (base / "src" / "utils.py").write_text("def helper(): pass")
        (base / "docs" / "guide.md").write_text("# Guide\n\nDocumentation")
        (base / "tests" / "test_main.py").write_text("def test_something(): pass")

        # Create a simple image file (just binary data for testing)
        (base / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        yield str(base)


class TestProbeFunction:
    """Test the probe() convenience function and DirectoryAnalysis methods."""

    def test_probe_returns_analysis_object(self, sample_directory):
        """Test that probe() returns a DirectoryAnalysis object."""
        analysis = probe(sample_directory)

        # Check that we get an analysis object with expected attributes
        assert hasattr(analysis, "summary")
        assert hasattr(analysis, "file_extensions")
        assert hasattr(analysis, "path")
        # Path may be resolved to absolute form on macOS (/private/var vs /var)
        assert Path(analysis.path).resolve() == Path(sample_directory).resolve()

    def test_analysis_summary_dict_access(self, sample_directory):
        """Test accessing summary statistics from analysis object."""
        analysis = probe(sample_directory)

        # Test dict-like access
        assert "total_files" in analysis.summary
        assert "total_folders" in analysis.summary
        assert isinstance(analysis.summary["total_files"], int)
        assert analysis.summary["total_files"] >= 6  # At least our test files

    def test_analysis_print_summary_no_args(self, sample_directory):
        """Test that analysis.print_summary() works without arguments.

        This is the main use case from documentation that was broken.
        """
        analysis = probe(sample_directory)

        # Should not raise an error
        try:
            analysis.print_summary()
        except TypeError as e:
            pytest.fail(f"analysis.print_summary() raised TypeError: {e}")

    def test_analysis_print_report_no_args(self, sample_directory):
        """Test that analysis.print_report() works without arguments.

        This is the full report version that was also broken.
        """
        analysis = probe(sample_directory)

        # Should not raise an error
        try:
            analysis.print_report()
        except TypeError as e:
            pytest.fail(f"analysis.print_report() raised TypeError: {e}")

    def test_analysis_file_extensions(self, sample_directory):
        """Test accessing file extension data from analysis."""
        analysis = probe(sample_directory)

        # Check file extensions dict
        assert ".md" in analysis.file_extensions
        assert ".py" in analysis.file_extensions
        assert ".png" in analysis.file_extensions

        # Verify counts
        assert analysis.file_extensions[".md"] >= 2  # README.md, guide.md
        assert analysis.file_extensions[".py"] >= 3  # main.py, utils.py, test_main.py


class TestProbeFileFunction:
    """Test the probe_file() convenience function."""

    def test_probe_file_basic(self, sample_directory):
        """Test basic file profiling."""
        readme_path = Path(sample_directory) / "README.md"
        file_info = probe_file(str(readme_path))

        # Check essential attributes exist
        assert hasattr(file_info, "path")
        assert hasattr(file_info, "size")
        assert hasattr(file_info, "modified")

        # Verify path
        assert Path(file_info.path).name == "README.md"

    def test_probe_file_size_attribute(self, sample_directory):
        """Test that file_info.size works (not size_str which doesn't exist)."""
        readme_path = Path(sample_directory) / "README.md"
        file_info = probe_file(str(readme_path))

        # size should exist and be an integer
        assert isinstance(file_info.size, int)
        assert file_info.size > 0

        # size_str should NOT exist (common documentation error)
        assert not hasattr(file_info, "size_str")

    def test_probe_file_as_dict(self, sample_directory):
        """Test converting file info to dictionary."""
        readme_path = Path(sample_directory) / "README.md"
        file_info = probe_file(str(readme_path))

        # Should be convertible to dict
        file_dict = file_info.as_dict()
        assert isinstance(file_dict, dict)
        assert "path" in file_dict
        assert "size" in file_dict


class TestProbeImageFunction:
    """Test the probe_image() convenience function."""

    def test_probe_image_basic(self, sample_directory):
        """Test basic image profiling."""
        image_path = Path(sample_directory) / "logo.png"

        try:
            img_info = probe_image(str(image_path))

            # Check essential attributes exist
            assert hasattr(img_info, "file_type")
            assert hasattr(img_info, "path")

            # Our fake PNG might not be a valid image, that's okay
            # We're testing that the API doesn't crash
            assert img_info.path is not None
        except Exception as e:
            # If PIL/Pillow isn't available or image is malformed, that's okay
            # We're just testing the API exists and doesn't crash badly
            if "cannot identify image file" not in str(e).lower():
                raise


class TestProbeToDfFunction:
    """Test the probe_to_df() convenience function."""

    def test_probe_to_df_basic(self, sample_directory):
        """Test basic DataFrame creation."""
        df = probe_to_df(sample_directory)

        # Should return a DataFrame wrapper
        assert hasattr(df, "df")  # Underlying Polars DataFrame
        assert hasattr(df, "head")  # Convenience methods

        # Check we got files
        assert len(df) > 0

    def test_probe_to_df_with_enrichment(self, sample_directory):
        """Test DataFrame creation with enrichment."""
        df = probe_to_df(sample_directory, enrich=True)

        # Should have enrichment columns
        columns = set(df.df.columns)
        assert "depth" in columns
        assert "parent" in columns
        assert "name" in columns

    def test_probe_to_df_without_enrichment(self, sample_directory):
        """Test DataFrame creation without enrichment."""
        df = probe_to_df(sample_directory, enrich=False)

        # Basic columns should exist
        assert "path" in df.df.columns
        assert len(df) > 0

    def test_probe_to_df_enrich_method(self, sample_directory):
        """Test the .enrich() method on DataFrame."""
        df = probe_to_df(sample_directory, enrich=False)

        # Should be able to enrich later
        df_enriched = df.enrich()

        # Check enrichment columns were added
        columns = set(df_enriched.df.columns)
        assert "depth" in columns or "parent" in columns


class TestReadmeExamples:
    """Test actual examples from README.md to ensure they work."""

    def test_readme_example_automatic_backend(self, sample_directory):
        """Test: Automatic multi-backend scanning example from README."""
        import filoma as flm

        # Example from README
        analysis = flm.probe(sample_directory)
        analysis.print_summary()  # Should not crash

        # Verify we can access the data
        assert analysis.summary["total_files"] > 0

    def test_readme_example_dataframe_enrichment(self, sample_directory):
        """Test: Polars DataFrame enrichment example from README."""
        import filoma as flm

        # Example from README
        df = flm.probe_to_df(sample_directory, enrich=True)
        assert len(df) > 0

    def test_readme_example_probe_file(self, sample_directory):
        """Test: Profile a single file example from README."""
        import filoma as flm

        readme_path = Path(sample_directory) / "README.md"

        # Example from README
        file_info = flm.probe_file(str(readme_path))
        print(f"Path: {file_info.path}")
        print(f"Size: {file_info.size} bytes")
        print(f"Modified: {file_info.modified}")

        # Verify attributes exist and work
        assert file_info.path
        assert file_info.size > 0
        assert file_info.modified is not None

    def test_readme_example_directory_analysis(self, sample_directory):
        """Test: Analyze directory example from README."""
        import filoma as flm

        # Example from README
        analysis = flm.probe(sample_directory)
        analysis.print_summary()  # Should show beautiful table

        # Verify data access
        assert "total_files" in analysis.summary


class TestMLIntegration:
    """Test ML-related functionality from high-level API."""

    def test_ml_split_data_basic(self, sample_directory):
        """Test basic ML data splitting."""
        from filoma import ml, probe_to_df

        df = probe_to_df(sample_directory)

        # Should be able to split without errors
        train, val, test = ml.split_data(df, train_val_test=(70, 15, 15), seed=42)

        # Verify we got data in all splits
        assert len(train) > 0
        assert len(val) >= 0  # Might be 0 for very small datasets
        assert len(test) >= 0

        # Total should roughly match original (minus directories if files_only=True)
        total_split = len(train) + len(val) + len(test)
        assert total_split > 0

    def test_ml_split_with_path_parts(self, sample_directory):
        """Test ML splitting with path_parts grouping."""
        from filoma import ml, probe_to_df

        df = probe_to_df(sample_directory)

        # Example from documentation
        train, val, test = ml.split_data(df, feature="path_parts", path_parts=(-2,), seed=42)

        # Should complete without errors
        assert len(train) + len(val) + len(test) > 0


class TestDocumentationConsistency:
    """Ensure documentation examples are consistent and work."""

    def test_probe_summary_access_patterns(self, sample_directory):
        """Test different ways to access summary data as shown in docs."""
        analysis = probe(sample_directory)

        # Dict-like access (scanning.md example)
        summary_dict = analysis.summary
        assert "total_files" in summary_dict

        # Direct access to extensions
        extensions = list(analysis.file_extensions.items())
        assert len(extensions) > 0

        # Access to top folders
        top_folders = analysis.top_folders_by_file_count
        assert isinstance(top_folders, list)

    def test_dataframe_workflow(self, sample_directory):
        """Test complete DataFrame workflow from docs."""
        # Get DataFrame
        df = probe_to_df(sample_directory)

        # Access underlying Polars df
        polars_df = df.df
        assert polars_df is not None

        # Use head() method
        head_result = df.head()
        assert head_result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
