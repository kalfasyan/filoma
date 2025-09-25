# ML Splits

Deterministic grouping-aware splits to avoid leakage.

Basic usage:
```python
from filoma import probe_to_df, ml
dfw = probe_to_df('.')  # filoma.DataFrame wrapper
# preferred: pass the filoma.DataFrame wrapper
train, val, test = ml.split_data(dfw, train_val_test=(70,15,15), feature='path_parts')
```

Group by filename tokens:
```python
# Preferred: use the DataFrame method which discovers filename tokens
# and returns a filoma.DataFrame (or use `inplace=True`).
df = df.add_filename_features(sep='_')
train, val, test = df.split_data(feature=('feat1',))
```

Use the `DataFrame.add_filename_features(...)` instance method to discover
filename tokens; it returns a `filoma.DataFrame` wrapper.

Group by path parts (e.g., parent folder):
```python
train, val, test = ml.split_data(dfw, feature='path_parts', path_parts=(-2,))
```

Return different types:
```python
train_f, val_f, test_f = ml.split_data(dfw, return_type='filoma')
```

Tips:
- Provide a seed to stabilize: `seed=42`.
- Ratios may slightly drift; warnings explain adjustments.
- Use `return_type='pandas'` if you prefer pandas downstream.

## Analyzing Your Splits

After creating splits, analyze their quality with the visualization module:

```python
import filoma.plot as plot

# Create analyzer for your splits
analyzer = plot.analyze_splits((train, val, test), split_names=['train', 'val', 'test'])

# Check balance and distribution quality
analyzer.balance()                    # Split size distributions
analyzer.distribution_analysis()      # Feature consistency across splits
analyzer.characteristics(['size'])    # File metadata analysis
```

**[Learn more about Split Visualization →](visualizations.md)**
