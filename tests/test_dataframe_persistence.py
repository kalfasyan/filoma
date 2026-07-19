"""Tests for DataFrame.save_csv / save_parquet / load (persistence roundtrip).

Covers the ability to save a DataFrame to disk and load it back in a later
session — the underlying mechanism behind the `export_dataframe` /
`load_dataframe` agent/MCP tools (see tests/test_mcp_server.py for those).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import polars as pl
import pytest

from filoma.dataframe import DataFrame


@pytest.fixture
def sample_df():
    return DataFrame({"path": ["a.txt", "b.png", "c.md"], "size_bytes": [10, 200, 30]})


def test_save_and_load_parquet_roundtrip(sample_df, tmp_path):
    p = tmp_path / "data.parquet"
    sample_df.save_parquet(p)

    loaded = DataFrame.load(p)

    assert loaded.columns == sample_df.columns
    assert loaded._df.to_dicts() == sample_df._df.to_dicts()


def test_save_and_load_csv_roundtrip(sample_df, tmp_path):
    p = tmp_path / "data.csv"
    sample_df.save_csv(p)

    loaded = DataFrame.load(p)

    assert set(loaded.columns) == set(sample_df.columns)
    assert loaded._df["path"].to_list() == sample_df._df["path"].to_list()


def test_load_json(tmp_path):
    p = tmp_path / "data.json"
    pl.DataFrame({"path": ["a.txt", "b.txt"]}).write_json(str(p))

    loaded = DataFrame.load(p)

    assert loaded._df["path"].to_list() == ["a.txt", "b.txt"]


def test_load_infers_format_from_extension(sample_df, tmp_path):
    p = tmp_path / "data.parquet"
    sample_df.save_parquet(p)

    loaded = DataFrame.load(p)  # no explicit format
    assert len(loaded) == len(sample_df)


def test_load_explicit_format_overrides_extension(sample_df, tmp_path):
    # File has no extension at all — format must be given explicitly.
    p = tmp_path / "data_no_ext"
    sample_df.save_parquet(p)

    loaded = DataFrame.load(p, format="parquet")
    assert len(loaded) == len(sample_df)


def test_load_raises_on_missing_file(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        DataFrame.load(tmp_path / "does_not_exist.parquet")


def test_load_raises_on_unsupported_format(sample_df, tmp_path):
    p = tmp_path / "data.txt"
    p.write_text("not a real dataframe file")

    with pytest.raises(ValueError, match="Unsupported format"):
        DataFrame.load(p)


def test_load_records_lineage(sample_df, tmp_path):
    p = tmp_path / "data.parquet"
    sample_df.save_parquet(p)

    loaded = DataFrame.load(p)
    assert loaded.lineage[-1]["operation"] == "load"
    assert loaded.lineage[-1]["parameters"]["format"] == "parquet"


def test_load_preserves_list_columns(tmp_path):
    """Parquet round-trips nested/list columns (e.g. embedding vectors) exactly, unlike CSV."""
    df = DataFrame({"path": ["a.png", "b.png"]})
    df = df._df.with_columns(pl.Series("embedding", [[1.0, 2.0], [3.0, 4.0]]))
    original = DataFrame(df)

    p = tmp_path / "with_embeddings.parquet"
    original.save_parquet(p)

    loaded = DataFrame.load(p)
    assert loaded._df["embedding"].to_list() == [[1.0, 2.0], [3.0, 4.0]]
