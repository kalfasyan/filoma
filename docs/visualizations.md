# Visualizing ML Splits

Analyze and visualize ML data splits for data-centric workflows.

The `filoma.plot` module provides comprehensive visualization and analysis tools for evaluating ML splits created with `filoma.ml.split_data()`. Perfect for validating data quality and ensuring robust train/validation/test distributions.

## Quick Start

```python
import filoma
import filoma.plot as plot

# Create your splits as usual
df = filoma.probe_to_df('.')
train, val, test = df.split_data(train_val_test=(70, 20, 10), feature='path_parts')

# Analyze the splits
analyzer = plot.analyze_splits((train, val, test), split_names=['train', 'val', 'test'])

# Get comprehensive analysis
analyzer.balance()                    # Split size distributions
analyzer.distribution_analysis()      # Feature distribution consistency
analyzer.characteristics(['size'])    # File metadata analysis
```

## Installation

Visualization requires optional dependencies:

```bash
pip install 'filoma[viz]'
```

Without visualization dependencies, you'll get rich text summaries instead of interactive plots.

## Core Features

### Split Balance Analysis

Understand how your data is distributed across splits:

```python
# Basic balance check
balance_result = analyzer.balance()
print(f"Train: {balance_result['train']} files")
print(f"Val: {balance_result['val']} files") 
print(f"Test: {balance_result['test']} files")
```

**What it shows:**
- Bar charts and pie charts of split distributions
- Statistical balance assessment
- Percentage breakdowns with quality indicators

### Distribution Analysis

Detect feature distribution inconsistencies that could hurt generalization:

```python
# Analyze feature distributions across splits
# First set the feature to analyze
analyzer.feature = 'size_mb'  # or any column name
distribution_result = analyzer.distribution_analysis()
```

**What it detects:**
- Missing feature values in specific splits
- Feature values exclusive to one split
- Uneven feature coverage across splits
- Distribution quality assessment

!!! note "Not Data Leakage Detection"
    This analyzes distribution quality, not true data leakage. True leakage detection (temporal, target, group-based) is planned for future versions.

### File Characteristics

Analyze file metadata patterns across splits:

```python
# Analyze multiple characteristics
char_result = analyzer.characteristics(['size', 'extension', 'depth'])
```

**What it shows:**
- File size distributions (violin plots, box plots)
- Extension distributions (stacked bar charts)  
- Directory depth patterns
- Custom metadata analysis

### Complete Validation

Get a comprehensive quality report:

```python
# Full validation pipeline
validation_result = analyzer.validate()

for check, status in validation_result.items():
    emoji = "✅" if status.get("passed", False) else "⚠️"
    print(f"{emoji} {check}: {status.get('message', 'Unknown')}")
```

## Dual Mode Operation

### Interactive Mode (with matplotlib/seaborn)

When visualization dependencies are installed:
- **Interactive plots**: Full matplotlib/seaborn visualizations
- **Rich styling**: Professional-quality charts and graphs
- **Multiple plot types**: Bar charts, pie charts, heatmaps, violin plots

### Text Mode (fallback)

When visualization dependencies are missing:
- **Rich formatted tables**: Beautiful terminal output
- **Statistical summaries**: All key metrics still available
- **Graceful degradation**: No functionality loss

Check availability:
```python
status = plot.check_plotting_available()
if status['available']:
    print("📊 Interactive plots available!")
else:
    print(f"📋 Text mode (missing: {status['missing']})")
```

## Complete Example

```python
import filoma
import filoma.plot as plot

# 1. Scan directory and create DataFrame
df = filoma.probe_to_df('/path/to/dataset')

# 2. Add filename features for better splitting
df = df.add_filename_features(sep='_', include_parent=True)

# 3. Create ML splits
train, val, test = df.split_data(
    train_val_test=(70, 20, 10),
    feature='parent',  # Group by parent directory
    seed=42
)

# 4. Create analyzer
analyzer = plot.analyze_splits(
    splits=(train, val, test),
    split_names=['train', 'validation', 'test'],
    feature='parent',
    original_data=df.df
)

# 5. Comprehensive analysis
print("=== BALANCE ANALYSIS ===")
analyzer.balance()

print("\n=== DISTRIBUTION ANALYSIS ===") 
analyzer.distribution_analysis()

print("\n=== FILE CHARACTERISTICS ===")
analyzer.characteristics(['size', 'extension'])

print("\n=== VALIDATION SUMMARY ===")
validation = analyzer.validate()
```

## Advanced Usage

### Custom Feature Analysis

Analyze any DataFrame column:

```python
# Add custom features
df = df.df.with_columns([
    (pl.col('size') / 1000000).alias('size_mb'),
    pl.col('path').str.extract(r'(\d{4})', 1).alias('year')
])

# Analyze custom features
analyzer.feature = 'year'
analyzer.distribution_analysis()
```

### Multiple Characteristics

Analyze multiple file properties at once:

```python
analyzer.characteristics(['size', 'extension', 'depth', 'size_mb'])
```

### Programmatic Results

All methods return structured data for further analysis:

```python
balance = analyzer.balance(show_plot=False)  # Skip visualization
distribution = analyzer.distribution_analysis(show_plot=False)

# Use results programmatically
if distribution['has_distribution_issues']:
    print("⚠️ Distribution issues detected!")
    for split, missing in distribution['missing_values'].items():
        print(f"  {split}: missing {len(missing)} values")
```

## Integration with Existing Workflows

The plot module works seamlessly with existing filoma workflows:

```python
# From scanning...
df = filoma.probe_to_df('.')

# To ML splits...
train, val, test = filoma.ml.split_data(df, feature='path_parts')

# To visualization...
analyzer = filoma.plot.analyze_splits((train, val, test))
analyzer.balance()
```

## Tips

- **Install viz dependencies**: `pip install 'filoma[viz]'` for full functionality
- **Set features explicitly**: `analyzer.feature = 'column_name'` before distribution analysis
- **Use validation pipeline**: `analyzer.validate()` for comprehensive quality checks
- **Programmatic access**: Set `show_plot=False` to get data without plots
- **Multiple characteristics**: Analyze several file properties in one call

## Notebook Tutorial

For a complete interactive tutorial with real data and visualizations:

```python
# Coming soon: comprehensive notebook tutorial
```

The visualization module helps ensure your ML splits are balanced, representative, and free from distribution issues that could impact model generalization.