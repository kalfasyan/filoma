
# filoma

[![PyPI version](https://badge.fury.io/py/filoma.svg)](https://badge.fury.io/py/filoma) ![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-blueviolet) ![Contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat) [![Tests](https://github.com/kalfasyan/filoma/actions/workflows/ci.yml/badge.svg)](https://github.com/kalfasyan/filoma/actions/workflows/ci.yml)

`filoma` is a modular Python tool for profiling files, analyzing directory structures, and inspecting image data (e.g., .tif, .png, .npy, .zarr). It provides detailed reports on filename patterns, inconsistencies, file counts, empty folders, file system metadata, and image data statistics. The project is designed for easy expansion, testing, CI/CD, Dockerization, and database integration.

## Features
- **Directory analysis**: Comprehensive directory tree analysis including file counts, folder patterns, empty directories, extension analysis, size statistics, and depth distribution
- **Image analysis**: Analyze .tif, .png, .npy, .zarr files for metadata, stats (min, max, mean, NaNs, etc.), and irregularities
- **File profiling**: System metadata (size, permissions, owner, group, timestamps, symlink targets, etc.)
- Modular, extensible codebase
- CLI entry point (planned)
- Ready for testing, CI/CD, Docker, and database integration

## Simple Examples

### Directory Analysis
```python
from filoma.dir import DirectoryAnalyzer

analyzer = DirectoryAnalyzer()
result = analyzer.analyze("/path/to/directory", max_depth=3)

# Print comprehensive report with rich formatting
analyzer.print_full_report(result)

# Or access specific data
print(f"Total files: {result['summary']['total_files']}")
print(f"Total folders: {result['summary']['total_folders']}")
print(f"Empty folders: {result['summary']['empty_folder_count']}")
print(f"File extensions: {result['file_extensions']}")
print(f"Common folder names: {result['common_folder_names']}")
```

### File Profiling
```python
from filoma.fileinfo import FileProfiler
profiler = FileProfiler()
report = profiler.profile("/path/to/file.txt")
profiler.print_report(report)  # Rich table output in your terminal
# Output: (Rich table with file metadata and access rights)
```

### Image Analysis
```python
from filoma.img import PngChecker
checker = PngChecker()
report = checker.check("/path/to/image.png")
print(report)
# Output: {'shape': ..., 'dtype': ..., 'min': ..., 'max': ..., 'nans': ..., ...}
```

## Directory Analysis Features

The `DirectoryAnalyzer` provides comprehensive analysis of directory structures:

- **Statistics**: Total files, folders, size calculations, and depth distribution
- **File Extension Analysis**: Count and percentage breakdown of file types
- **Folder Patterns**: Identification of common folder naming patterns
- **Empty Directory Detection**: Find directories with no files or subdirectories
- **Depth Control**: Limit analysis depth with `max_depth` parameter
- **Rich Output**: Beautiful terminal reports with tables and formatting

### Analysis Output Structure
```python
{
    "root_path": "/analyzed/path",
    "summary": {
        "total_files": 150,
        "total_folders": 25,
        "total_size_bytes": 1048576,
        "total_size_mb": 1.0,
        "avg_files_per_folder": 6.0,
        "max_depth": 3,
        "empty_folder_count": 2
    },
    "file_extensions": {".py": 45, ".txt": 30, ".md": 10},
    "common_folder_names": {"src": 3, "tests": 2, "docs": 1},
    "empty_folders": ["/path/to/empty1", "/path/to/empty2"],
    "top_folders_by_file_count": [("/path/with/most/files", 25)],
    "depth_distribution": {0: 1, 1: 5, 2: 12, 3: 7}
}
```

## Project Structure
- `src/filoma/dir/` — Directory analysis and structure profiling
- `src/filoma/img/` — Image checkers and analysis
- `src/filoma/fileinfo/` — File profiling (system metadata)
- `tests/` — Unit tests for all modules

## Future TODO
- CLI tool for all features
- More image format support and advanced checks
- Database integration for storing reports
- Dockerization and deployment guides
- CI/CD workflows and badges

---
`filoma` is under active development. Contributions and suggestions are welcome!