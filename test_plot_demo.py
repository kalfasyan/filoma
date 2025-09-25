#!/usr/bin/env python3
"""Demo and test script for filoma plot functionality.

Tests all visualization methods and demonstrates the ML split analysis workflow.
"""

import sys
from pathlib import Path

import polars as pl

# Add the src directory to the path for testing
sys.path.insert(0, str(Path(__file__).parent / "src"))


def create_test_data():
    """Create sample data that mimics filoma's output structure."""
    # Sample file data with different characteristics
    sample_files = [
        {"path": "/data/train/image1.jpg", "size": 1024000, "extension": "jpg", "depth": 3},
        {"path": "/data/train/image2.png", "size": 2048000, "extension": "png", "depth": 3},
        {"path": "/data/train/doc1.txt", "size": 5000, "extension": "txt", "depth": 3},
        {"path": "/data/val/image3.jpg", "size": 1500000, "extension": "jpg", "depth": 3},
        {"path": "/data/val/doc2.pdf", "size": 100000, "extension": "pdf", "depth": 3},
        {"path": "/data/test/image4.png", "size": 1800000, "extension": "png", "depth": 3},
        {"path": "/data/test/image5.jpg", "size": 1200000, "extension": "jpg", "depth": 3},
        {"path": "/data/test/data.csv", "size": 50000, "extension": "csv", "depth": 3},
    ]

    # Convert to Polars DataFrame
    df = pl.DataFrame(sample_files)

    # Add split assignments
    train_mask = df["path"].str.contains("/train/")
    val_mask = df["path"].str.contains("/val/")
    test_mask = df["path"].str.contains("/test/")

    df = df.with_columns(
        [pl.when(train_mask).then(pl.lit("train")).when(val_mask).then(pl.lit("validation")).when(test_mask).then(pl.lit("test")).alias("split")]
    )

    # Add some numerical features for feature distribution analysis
    df = df.with_columns(
        [
            (pl.col("size") / 1000000).alias("size_mb"),  # Size in MB
            pl.when(pl.col("extension") == "jpg")
            .then(pl.lit(1.0))
            .when(pl.col("extension") == "png")
            .then(pl.lit(2.0))
            .when(pl.col("extension") == "txt")
            .then(pl.lit(0.1))
            .when(pl.col("extension") == "pdf")
            .then(pl.lit(0.5))
            .otherwise(pl.lit(1.5))
            .alias("feature_score"),
        ]
    )

    return df


def test_plot_import():
    """Test that plot module imports correctly."""
    print("🧪 Testing plot module import...")

    try:
        import filoma.plot as plot

        print("✅ Plot module imported successfully")

        # Check if plotting is available
        status = plot.check_plotting_available()
        available = status.get("available", False)
        if available:
            print("✅ Plotting dependencies available (matplotlib/seaborn)")
        else:
            print("⚠️  Plotting dependencies not available - text output only")

        return True, available
    except Exception as e:
        print(f"❌ Failed to import plot module: {e}")
        return False, False


def test_split_analyzer_creation():
    """Test SplitAnalyzer creation and basic functionality."""
    print("\n🧪 Testing SplitAnalyzer creation...")

    try:
        import filoma.plot as plot

        df = create_test_data()

        # Split the data into separate DataFrames
        train_df = df.filter(pl.col("split") == "train")
        val_df = df.filter(pl.col("split") == "validation")
        test_df = df.filter(pl.col("split") == "test")

        # Create tuple of splits
        splits = (train_df, val_df, test_df)
        split_names = ["train", "validation", "test"]

        # Create analyzer
        analyzer = plot.analyze_splits(splits, split_names=split_names, original_data=df)
        print("✅ SplitAnalyzer created successfully")

        # Test data access
        print(f"✅ Found splits: {analyzer.split_names}")

        return True, analyzer
    except Exception as e:
        print(f"❌ Failed to create SplitAnalyzer: {e}")
        return False, None


def test_balance_analysis(analyzer, plotting_available):
    """Test balance analysis functionality."""
    print("\n🧪 Testing balance analysis...")

    try:
        result = analyzer.balance()

        # Check result structure
        if "train" in result and "validation" in result and "test" in result:
            print("✅ Balance analysis returned expected splits")

            # Print counts
            for split, count in result.items():
                print(f"  {split}: {count} files")

        if plotting_available:
            print("📊 Balance visualization displayed")
        else:
            print("📋 Balance text summary provided")

        return True
    except Exception as e:
        print(f"❌ Balance analysis failed: {e}")
        return False


def test_feature_distribution(analyzer, plotting_available):
    """Test feature distribution analysis."""
    print("\n🧪 Testing feature distribution analysis...")

    try:
        # Create analyzer with feature specified
        analyzer.feature = "size_mb"  # Set the feature for analysis

        result = analyzer.feature_distribution()

        if isinstance(result, dict) and len(result) > 0:
            print("✅ Feature distribution analysis completed")

        if plotting_available:
            print("📊 Feature distribution visualization displayed")
        else:
            print("📋 Feature distribution text summary provided")

        return True
    except Exception as e:
        print(f"❌ Feature distribution analysis failed: {e}")
        return False


def test_distribution_analysis(analyzer, plotting_available):
    """Test distribution analysis functionality."""
    print("\n🧪 Testing distribution analysis...")

    try:
        result = analyzer.distribution_analysis()

        if isinstance(result, dict):
            print("✅ Distribution analysis completed")

        if plotting_available:
            print("📊 Distribution analysis visualization displayed")
        else:
            print("📋 Distribution analysis text summary provided")

        return True
    except Exception as e:
        print(f"❌ Distribution analysis failed: {e}")
        return False


def test_characteristics_analysis(analyzer, plotting_available):
    """Test file characteristics analysis."""
    print("\n🧪 Testing characteristics analysis...")

    try:
        result = analyzer.characteristics(["size", "extension"])

        if isinstance(result, dict) and len(result) > 0:
            print("✅ Characteristics analysis completed")

        if plotting_available:
            print("📊 Characteristics visualization displayed")
        else:
            print("📋 Characteristics text summary provided")

        return True
    except Exception as e:
        print(f"❌ Characteristics analysis failed: {e}")
        return False


def demonstrate_workflow():
    """Demonstrate the complete workflow."""
    print("\n" + "=" * 60)
    print("🚀 FILOMA PLOT FUNCTIONALITY DEMONSTRATION")
    print("=" * 60)

    # Test imports
    import_success, plotting_available = test_plot_import()
    if not import_success:
        return False

    # Test analyzer creation
    analyzer_success, analyzer = test_split_analyzer_creation()
    if not analyzer_success:
        return False

    # Test all functionality
    tests = [
        ("Balance Analysis", lambda: test_balance_analysis(analyzer, plotting_available)),
        ("Feature Distribution", lambda: test_feature_distribution(analyzer, plotting_available)),
        ("Distribution Analysis", lambda: test_distribution_analysis(analyzer, plotting_available)),
        ("Characteristics Analysis", lambda: test_characteristics_analysis(analyzer, plotting_available)),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")

    print(f"\n🎯 Overall: {passed}/{total} tests passed")

    if plotting_available:
        print("📊 Visualization mode: INTERACTIVE PLOTS")
    else:
        print("📋 Visualization mode: TEXT SUMMARIES")

    print("\n" + "=" * 60)
    print("🎉 DEMONSTRATION COMPLETE")
    print("=" * 60)

    return passed == total


if __name__ == "__main__":
    success = demonstrate_workflow()
    sys.exit(0 if success else 1)
