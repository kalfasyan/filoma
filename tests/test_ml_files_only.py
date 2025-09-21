"""
Tests for the files_only parameter in split_data function.
"""

import sys
import tempfile
from pathlib import Path

import polars as pl

sys.path.insert(0, "src")

from filoma import DataFrame
from filoma.ml import split_data


def test_files_only_parameter():
    """Test that files_only parameter correctly filters directories."""

    # Create test data with both files and directories
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create directory structure: train/class1/, valid/class1/, test/class1/
        for split in ["train", "valid", "test"]:
            split_dir = temp_path / split / "class1"
            split_dir.mkdir(parents=True)

            # Create files in each split
            for i in range(3):
                (split_dir / f"file_{i}.txt").write_text(f"content {i}")

        # Create DataFrame that includes both files and directories
        all_paths = list(temp_path.rglob("*"))
        file_paths = [p for p in all_paths if p.is_file()]

        df_data = {"path": [str(p) for p in all_paths if p != temp_path], "is_file": [p.is_file() for p in all_paths if p != temp_path]}
        df = pl.DataFrame(df_data)

        # Test with files_only=True (default)
        train, val, test = split_data(
            df,
            feature="path_parts",
            path_parts=(-3,),  # Split folder level
            split_mapping={"train": "train", "valid": "val", "test": "test"},
            files_only=True,
            verbose=False,
        )

        total_files_only = len(train) + len(val) + len(test)
        assert total_files_only == len(file_paths), f"Expected {len(file_paths)} files, got {total_files_only}"

        # Test with files_only=False
        train2, val2, test2 = split_data(
            df,
            feature="path_parts",
            path_parts=(-3,),  # Split folder level
            split_mapping={"train": "train", "valid": "val", "test": "test"},
            files_only=False,
            verbose=False,
        )

        total_all_items = len(train2) + len(val2) + len(test2)
        expected_mapped_items = len([p for p in all_paths if p != temp_path and p.parts[-3] in ["train", "valid", "test"]])
        assert total_all_items == expected_mapped_items


def test_files_only_with_no_is_file_column():
    """Test that files_only parameter is ignored when no is_file column exists."""

    # Create test DataFrame without is_file column
    df_data = {"path": ["/train/file1.txt", "/valid/file2.txt", "/test/file3.txt"], "other_col": ["a", "b", "c"]}
    df = pl.DataFrame(df_data)

    # Both should give same result when no is_file column
    train1, val1, test1 = split_data(
        df, feature="path_parts", path_parts=(-2,), split_mapping={"train": "train", "valid": "val", "test": "test"}, files_only=True, verbose=False
    )

    train2, val2, test2 = split_data(
        df, feature="path_parts", path_parts=(-2,), split_mapping={"train": "train", "valid": "val", "test": "test"}, files_only=False, verbose=False
    )

    assert len(train1) == len(train2)
    assert len(val1) == len(val2)
    assert len(test1) == len(test2)


def test_dataframe_wrapper_files_only():
    """Test that DataFrame wrapper passes through files_only parameter."""

    # Create test data
    df_data = {
        "path": ["/train/class1/file1.txt", "/train/class1/", "/valid/class1/file2.txt", "/valid/class1/"],
        "is_file": [True, False, True, False],
    }
    polars_df = pl.DataFrame(df_data)
    filoma_df = DataFrame(polars_df)

    # Test files_only=True
    train, val, test = filoma_df.split_data(
        feature="path_parts", path_parts=(-3,), split_mapping={"train": "train", "valid": "val"}, files_only=True, verbose=False
    )

    total_split = len(train) + len(val) + len(test)
    assert total_split == 2  # Only the 2 files should be included


if __name__ == "__main__":
    test_files_only_parameter()
    test_files_only_with_no_is_file_column()
    test_dataframe_wrapper_files_only()
    print("✅ All files_only tests passed!")
