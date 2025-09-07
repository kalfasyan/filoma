# ML Splits

Deterministic grouping-aware splits to avoid leakage.

Basic usage:
```python
from filoma import probe_to_df, ml
pl_df = probe_to_df('.')
train, val, test = ml.auto_split(pl_df, train_val_test=(70,15,15))
```

Group by filename tokens:
```python
pl_df = ml.discover_filename_features(pl_df, sep='_')
train, val, test = ml.auto_split(pl_df, how='tokens')
```

Group by path parts (e.g., parent folder):
```python
train, val, test = ml.auto_split(pl_df, how='parts', parts=(-2,))
```

Return different types:
```python
train_f, val_f, test_f = ml.auto_split(pl_df, return_type='filoma')
```

Tips:
- Provide a seed to stabilize: `seed=42`.
- Ratios may slightly drift; warnings explain adjustments.
- Use `return_type='pandas'` if you prefer pandas downstream.
