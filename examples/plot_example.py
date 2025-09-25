"""Simple example demonstrating filoma plot functionality.

This script shows how to use filoma's plotting capabilities to analyze ML splits.
"""

import sys

sys.path.insert(0, "src")

import polars as pl

import filoma.plot as plot


def main():
    """Demonstrate filoma plot functionality with sample data."""
    print("🎯 Filoma Plot Functionality Example")
    print("=" * 50)

    # Create sample data
    sample_files = [
        {"path": "/data/train/image_001.jpg", "size": 1024000, "extension": "jpg"},
        {"path": "/data/train/image_002.png", "size": 1536000, "extension": "png"},
        {"path": "/data/train/doc_001.txt", "size": 5000, "extension": "txt"},
        {"path": "/data/val/image_003.jpg", "size": 1200000, "extension": "jpg"},
        {"path": "/data/val/doc_002.txt", "size": 7500, "extension": "txt"},
        {"path": "/data/test/image_004.png", "size": 1800000, "extension": "png"},
        {"path": "/data/test/doc_003.txt", "size": 6200, "extension": "txt"},
    ]

    # Convert to DataFrame and add size in MB
    df = pl.DataFrame(sample_files)
    df = df.with_columns([(pl.col("size") / 1000000).alias("size_mb")])

    print(f"📁 Sample dataset: {len(df)} files")
    print(df.head(3))

    # Create splits
    train_df = df.filter(pl.col("path").str.contains("/train/"))
    val_df = df.filter(pl.col("path").str.contains("/val/"))
    test_df = df.filter(pl.col("path").str.contains("/test/"))

    print(f"📊 Split sizes: {[len(train_df), len(val_df), len(test_df)]}")

    # Create analyzer
    analyzer = plot.analyze_splits((train_df, val_df, test_df), split_names=["train", "val", "test"])
    analyzer.feature = "size_mb"

    print("\n✅ Split analyzer created!")

    # 1. Split balance visualization
    print("\n" + "=" * 30)
    print("📊 BALANCE ANALYSIS")
    print("=" * 30)
    analyzer.balance()

    # 2. Feature distribution analysis
    print("\n" + "=" * 30)
    print("📈 DISTRIBUTION ANALYSIS")
    print("=" * 30)
    analyzer.distribution_analysis()

    # 3. File characteristics
    print("\n" + "=" * 30)
    print("📋 FILE CHARACTERISTICS")
    print("=" * 30)
    analyzer.characteristics(["size", "extension"])

    # 4. Complete validation
    print("\n" + "=" * 30)
    print("🎯 VALIDATION SUMMARY")
    print("=" * 30)
    validation_result = analyzer.validate()

    for check, status in validation_result.items():
        if check == "summary":
            continue  # Skip the summary dict
        elif check == "issues":
            if isinstance(status, list) and status:  # If there are issues
                for issue in status:
                    print(f"⚠️ Issue: {issue}")
            elif not status:  # Empty list means no issues
                print("✅ No issues found")
        elif isinstance(status, bool):
            # For boolean flags like 'balance_ok', 'distribution_issues'
            if check.endswith("_ok"):
                emoji = "✅" if status else "⚠️"
                status_text = "Passed" if status else "Failed"
            else:  # For flags like 'distribution_issues' where True = problems exist
                emoji = "⚠️" if status else "✅"
                status_text = "Issues Found" if status else "No Issues"

            check_name = check.replace("_", " ").title()
            print(f"{emoji} {check_name}: {status_text}")

    print("\n🎉 Analysis complete!")

    # Check if plotting was available
    plot_status = plot.check_plotting_available()
    if plot_status["available"]:
        print("📊 Interactive plots were displayed")
    else:
        print("📋 Text summaries provided (install 'filoma[viz]' for plots)")


if __name__ == "__main__":
    main()
