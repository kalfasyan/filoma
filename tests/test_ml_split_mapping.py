import polars as pl
import pytest
from loguru import logger

from filoma import ml


def test_split_mapping_basic_functionality():
    """Test basic split_mapping functionality with folder names."""
    # Create test data with paths in different folders
    paths = [
        "/data/training/image_001.jpg",
        "/data/training/image_002.jpg",
        "/data/training/image_003.jpg",
        "/data/validation/image_004.jpg",
        "/data/validation/image_005.jpg",
        "/data/testing/image_006.jpg",
        "/data/testing/image_007.jpg",
        "/data/testing/image_008.jpg",
    ]
    df = pl.DataFrame({"path": paths})

    # Test split_mapping with folder names
    train, val, test = ml.split_data(
        df,
        feature="path_parts",
        path_parts=(-2,),  # Parent folder
        split_mapping={"training": "train", "validation": "val", "testing": "test"},
        path_col="path",
    )

    # Verify all training paths go to train
    train_paths = set(train["path"].to_list())
    expected_train = {p for p in paths if "/training/" in p}
    assert train_paths == expected_train

    # Verify all validation paths go to val
    val_paths = set(val["path"].to_list())
    expected_val = {p for p in paths if "/validation/" in p}
    assert val_paths == expected_val

    # Verify all testing paths go to test
    test_paths = set(test["path"].to_list())
    expected_test = {p for p in paths if "/testing/" in p}
    assert test_paths == expected_test

    # Verify no overlap
    assert train_paths.isdisjoint(val_paths)
    assert train_paths.isdisjoint(test_paths)
    assert val_paths.isdisjoint(test_paths)

    # Verify all paths are accounted for
    all_split_paths = train_paths | val_paths | test_paths
    assert all_split_paths == set(paths)


def test_split_mapping_with_unmapped_features():
    """Test that unmapped features are excluded with warning."""
    paths = [
        "/data/train/file1.txt",
        "/data/val/file2.txt",
        "/data/test/file3.txt",
        "/data/unknown/file4.txt",  # This won't be mapped
        "/data/extra/file5.txt",  # This won't be mapped either
    ]
    df = pl.DataFrame({"path": paths})

    # Capture warnings
    messages = []
    sink_id = logger.add(lambda m: messages.append(str(m)), level="WARNING")

    try:
        train, val, test = ml.split_data(
            df,
            feature="path_parts",
            path_parts=(-2,),
            split_mapping={
                "train": "train",
                "val": "val",
                "test": "test",
                # 'unknown' and 'extra' are deliberately not mapped
            },
            path_col="path",
        )
    finally:
        logger.remove(sink_id)

    # Check that warning was logged for unmapped features
    warning_messages = [m for m in messages if "split_mapping" in m and "not found in mapping" in m]
    assert len(warning_messages) > 0

    # Verify mapped paths are correctly assigned
    all_result_paths = set(train["path"].to_list()) | set(val["path"].to_list()) | set(test["path"].to_list())
    expected_mapped = {p for p in paths if any(folder in p for folder in ["/train/", "/val/", "/test/"])}
    assert all_result_paths == expected_mapped

    # Verify unmapped paths are excluded
    assert "/data/unknown/file4.txt" not in all_result_paths
    assert "/data/extra/file5.txt" not in all_result_paths


def test_split_mapping_invalid_split_values():
    """Test error handling for invalid split mapping values."""
    paths = ["/data/train/file1.txt", "/data/invalid/file2.txt"]
    df = pl.DataFrame({"path": paths})

    with pytest.raises(ValueError, match="split_mapping values must be 'train', 'val', or 'test'"):
        ml.split_data(
            df,
            feature="path_parts",
            path_parts=(-2,),
            split_mapping={
                "train": "train",
                "invalid": "invalid_split",  # Invalid split name
            },
            path_col="path",
        )


def test_split_mapping_with_filename_tokens():
    """Test split_mapping with filename token features."""
    paths = [
        "/data/subject_train_001.txt",
        "/data/subject_train_002.txt",
        "/data/subject_val_001.txt",
        "/data/subject_test_001.txt",
        "/data/subject_test_002.txt",
    ]
    df = pl.DataFrame({"path": paths})

    # First add filename features
    from filoma.dataframe import DataFrame as FDataFrame

    df_with_features = FDataFrame(df).add_filename_features(sep="_")

    # Split using the second token (train/val/test) - which is 'feat2'
    train, val, test = df_with_features.split_data(
        feature=("feat2",),  # Second token contains train/val/test
        split_mapping={"train": "train", "val": "val", "test": "test"},
    )

    # Verify correct assignment based on filename tokens
    train_paths = set(train.df["path"].to_list())
    val_paths = set(val.df["path"].to_list())
    test_paths = set(test.df["path"].to_list())

    assert all("_train_" in p for p in train_paths)
    assert all("_val_" in p for p in val_paths)
    assert all("_test_" in p for p in test_paths)


def test_split_mapping_single_split():
    """Test that split_mapping works even when all data maps to one split."""
    paths = [
        "/data/train/file1.txt",
        "/data/train/file2.txt",
        "/data/train/file3.txt",
    ]
    df = pl.DataFrame({"path": paths})

    train, val, test = ml.split_data(df, feature="path_parts", path_parts=(-2,), split_mapping={"train": "train"}, path_col="path")

    # All data should go to train
    assert len(train) == 3
    assert len(val) == 0
    assert len(test) == 0
    assert set(train["path"].to_list()) == set(paths)


def test_split_mapping_with_different_path_structures():
    """Test split_mapping with various path structures and indices."""
    # Test with different path depths and structures
    paths = [
        "project/data/training/set1/file1.txt",  # -3 index for 'training'
        "project/data/training/set2/file2.txt",
        "project/data/validation/set1/file3.txt",  # -3 index for 'validation'
        "other/folder/testing/subdir/file4.txt",  # -3 index for 'testing'
    ]
    df = pl.DataFrame({"path": paths})

    train, val, test = ml.split_data(
        df,
        feature="path_parts",
        path_parts=(-3,),  # Third from end to get training/validation/testing
        split_mapping={"training": "train", "validation": "val", "testing": "test"},
        path_col="path",
    )

    # Verify paths are correctly assigned
    assert len(train) == 2  # 2 training files
    assert len(val) == 1  # 1 validation file
    assert len(test) == 1  # 1 testing file

    train_paths = train["path"].to_list()
    assert all("/training/" in p for p in train_paths)
    assert "/validation/" in val["path"].to_list()[0]
    assert "/testing/" in test["path"].to_list()[0]


def test_split_mapping_ignores_train_val_test_ratios():
    """Test that split_mapping ignores train_val_test ratios."""
    paths = ["/data/train/file1.txt", "/data/val/file2.txt"]
    df = pl.DataFrame({"path": paths})

    # Use extreme ratios that would normally create different splits
    train, val, test = ml.split_data(
        df,
        train_val_test=(99, 0.5, 0.5),  # These should be ignored
        feature="path_parts",
        path_parts=(-2,),
        split_mapping={"train": "train", "val": "val"},
        path_col="path",
    )

    # Ratios should be ignored, mapping should take precedence
    assert len(train) == 1
    assert len(val) == 1
    assert len(test) == 0
