# Interactive CLI

Filoma provides a powerful interactive command-line interface that combines filesystem exploration with data analysis capabilities. Navigate directories with arrow keys, probe files and folders, and analyze the results—all within a beautiful terminal interface.

## Overview

The CLI is built using modern Python tools for an exceptional user experience:

- **[Typer](https://typer.tiangolo.com/)**: Modern CLI framework with automatic help generation
- **[questionary](https://github.com/tmbo/questionary)**: Interactive prompts with arrow-key navigation
- **[Rich](https://rich.readthedocs.io/)**: Beautiful terminal formatting, tables, and progress bars

## Getting Started

### Launch the CLI

```bash
# Start in current directory
filoma

# Start in specific directory
filoma /path/to/analyze

# Show help
filoma --help
```

### Navigation

- **Arrow keys**: Navigate menus
- **Enter**: Select option
- **Ctrl+C**: Exit anytime

## Features

### 🗂️ File Browser

Navigate your filesystem with an intuitive interface:

- **Directory Navigation**: Enter folders, go to parent directory
- **File Type Icons**: Visual indicators for different file types (🖼️ images, 💻 code, 📄 documents)
- **Smart Sorting**: Directories first, then files, alphabetically sorted

### 🔍 Probe Operations

Analyze files and directories with multiple probe options:

- **Auto Probe**: Automatically detects and uses the best probe method
- **Probe as File**: General file analysis using `probe_file()`
- **Probe as Image**: Specialized image analysis using `probe_image()`
- **Probe to DataFrame**: Directory analysis with `probe_to_df()` for data exploration

### 📊 DataFrame Analysis

When you use "Probe to DataFrame", unlock powerful data analysis capabilities:

#### Core DataFrame Operations
- **DataFrame Info**: Shape, column types, memory usage
- **Head Display**: View first N rows with customizable count
- **Column Overview**: All columns with types and sample values
- **Basic Statistics**: Descriptive statistics for numeric columns

#### Advanced Column Analysis
- **Value Counts**: Frequency distribution of column values
- **Unique Values**: List of unique values (with count)
- **Column Statistics**: Mean, std, min, max for numeric data
- **Null Analysis**: Missing value counts and percentages

#### Data Exploration
- **Interactive Filtering**: Filter by column values with live preview
- **Search Functionality**: Find specific values across columns
- **Sample Data**: Preview column contents before analysis

#### Export Options
- **CSV Export**: Standard comma-separated format
- **JSON Export**: Structured JSON format
- **Parquet Export**: High-performance columnar format

## Example Workflow

Here's a typical analysis session:

### 1. Launch and Navigate

```bash
filoma ~/projects/my-data
```

The CLI opens showing your directory contents with file type icons.

### 2. Explore Directory Structure

```
📁 .. (Parent Directory)
📁 datasets/
📁 images/
💻 analysis.py
📄 README.md
📊 results.csv
```

Use arrow keys to navigate. Select `datasets/` → choose "Enter directory".

### 3. Probe for Analysis

Select the directory you want to analyze → choose "🔍 Probe to DataFrame".

A spinner shows the analysis progress, then results appear:

```
✅ Probe Results for datasets
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Property      ┃ Value                     ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Total Files   │ 1,247                     │
│ Total Size    │ 2.34 GB                   │
│ File Types    │ 12                        │
│ Directories   │ 8                         │
└───────────────┴───────────────────────────┘
```

### 4. Interactive DataFrame Analysis

The DataFrame analysis menu automatically appears:

```
📊 DataFrame Analysis for datasets
Shape: 1,247 rows × 8 columns

What would you like to do with this DataFrame?
> 📊 Show DataFrame Info
  👀 Show Head (first 10 rows)
  📋 Show Columns
  📈 Column Analysis
  🔍 Basic Statistics
  🔎 Search/Filter
  💾 Export Options
  🔙 Back to File Browser
```

### 5. Explore Your Data

**View column information:**
```
📋 DataFrame Columns
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Column        ┃ Type       ┃ Sample Values                        ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ path          │ String     │ /datasets/file1.txt, /datasets/...  │
│ size_bytes    │ Int64      │ 1024, 2048, 4096                    │
│ file_type     │ String     │ .txt, .csv, .json                    │
│ modified_date │ String     │ 2024-01-15, 2024-01-16, ...         │
└───────────────┴────────────┴──────────────────────────────────────┘
```

**Analyze specific columns:**
Select "📈 Column Analysis" → choose `file_type` → "📊 Value Counts":

```
Value counts for 'file_type':
.txt    456
.csv    234
.json   187
.py     156
.md     89
...
```

### 6. Export Results

Select "💾 Export Options" → "📄 Export to CSV" → enter filename:

```
✅ Successfully exported to: datasets_analysis.csv
```

## Tips and Tricks

### Efficient Navigation
- Use the parent directory option (`📁 ..`) to quickly move up the tree
- File type icons help identify content at a glance
- The current directory is always shown in the welcome panel

### DataFrame Analysis
- Start with "📊 Show DataFrame Info" for a quick overview
- Use "👀 Show Head" to understand your data structure
- "📈 Column Analysis" → "📊 Value Counts" reveals data distributions
- Export results for further analysis in other tools

### Performance
- Large directories are analyzed with progress bars
- DataFrame operations are optimized for speed
- Filtering shows live previews without affecting the original data

## Integration with Python API

The CLI uses the same underlying functions as the Python API:

```python
import filoma

# CLI "Auto Probe" uses:
result = filoma.probe("/path/to/analyze")

# CLI "Probe to DataFrame" uses:
df_result = filoma.probe_to_df("/path/to/analyze")

# Access the DataFrame:
df = df_result.df
```

This means you can seamlessly move between interactive exploration and programmatic analysis.

---

The interactive CLI makes filesystem analysis accessible and enjoyable, whether you're doing quick exploration or deep data analysis. Its intuitive interface and powerful features make it perfect for both newcomers and advanced users.