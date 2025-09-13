# ML Splits

Deterministic grouping-aware splits to avoid leakage.

Basic usage:
```python
from filoma import probe_to_df, ml
pl_df = probe_to_df('.')
train, val, test = ml.split_data(pl_df, train_val_test=(70,15,15), feature='path_parts')
```

Group by filename tokens:
```python
pl_df = ml.add_filename_features(pl_df, sep='_')
train, val, test = ml.split_data(pl_df, feature=('token1',))
```

Group by path parts (e.g., parent folder):
```python
train, val, test = ml.split_data(pl_df, feature='path_parts', path_parts=(-2,))
```

Return different types:
```python
train_f, val_f, test_f = ml.split_data(pl_df, return_type='filoma')
```

Tips:
- Provide a seed to stabilize: `seed=42`.
- Ratios may slightly drift; warnings explain adjustments.
- Use `return_type='pandas'` if you prefer pandas downstream.
