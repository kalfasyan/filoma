import logging

import polars as pl
from loguru import logger

from filoma.ml import split_data


def _bind_loguru_to_logging():
    # Ensure loguru messages propagate to the standard logging system so pytest.caplog can capture them
    class InterceptHandler(logging.Handler):
        def emit(self, record):
            logging.getLogger(record.name).handle(record)

    logging.basicConfig(level=logging.INFO)
    logger.remove()
    logger.add(InterceptHandler(), level="INFO")


def test_validate_counts_warns(caplog):
    _bind_loguru_to_logging()

    # Construct a dataframe with path-derived feature (parent folder) causing
    # uneven distribution of unique features across splits
    df = pl.DataFrame(
        {
            "path": [
                "a/class1/file1.txt",
                "a/class1/file2.txt",
                "b/class2/file3.txt",
                "c/class3/file4.txt",
            ]
        }
    )

    # Use path_parts selecting the folder (index -2) to form feature values
    with caplog.at_level(logging.WARNING):
        train, val, test = split_data(df, train_val_test=(50, 25, 25), feature="path_parts", path_parts=(-2,), validate_counts=True)

    # Ensure a warning mentioning 'unique feature values' or 'unique feature' was emitted
    warnings = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("unique feature" in str(w).lower() or "unique feature values" in str(w).lower() for w in warnings)
