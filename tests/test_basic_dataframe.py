#!/usr/bin/env python3
"""
Simple test to verify DataFrame functionality works.
"""

import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_basic_functionality():
    """Test basic DataFrame functionality."""
    try:
        from filoma import DataFrame
        from filoma.directories.directory_profiler import DirectoryProfiler

        print("✅ Imports successful")

        # Test DirectoryProfiler with DataFrame
        profiler = DirectoryProfiler(
            use_rust=False,
            build_dataframe=True
        )

        print(f"✅ DataFrame enabled: {profiler.is_dataframe_enabled()}")

        # Test standalone DataFrame
        test_paths = ["/tmp/file1.txt", "/tmp/file2.py"]
        df = DataFrame(test_paths)

        print(f"✅ Standalone DataFrame created: {len(df)} rows")

        # Test DataFrame methods
        df_with_components = df.add_path_components()
        print(f"✅ Path components added: {df_with_components.df.columns}")

        py_files = df.filter_by_extension('.py')
        print(f"✅ Filtering works: {len(py_files)} Python files")

        print("\n🎉 All tests passed!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_basic_functionality()
