
# filoma

`filoma` is a modular Python tool for profiling files, analyzing directory structures, and inspecting image data (e.g., .tif, .png, .npy, .zarr). It provides detailed reports on filename patterns, inconsistencies, file counts, empty folders, file system metadata, and image data statistics. The project is designed for easy expansion, testing, CI/CD, Dockerization, and database integration.

## Features
- **Directory analysis**: Filename pattern extraction, reporting, statistics, empty folder detection
- **Image analysis**: Analyze .tif, .png, .npy, .zarr files for metadata, stats (min, max, mean, NaNs, etc.), and irregularities
- **File profiling**: System metadata (size, permissions, owner, group, timestamps, symlink targets, etc.)
- Modular, extensible codebase
- CLI entry point (planned)
- Ready for testing, CI/CD, Docker, and database integration

## Simple Examples


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

## Project Structure
- `src/filoma/img/` — Image checkers and analysis
- `src/filoma/fileprof/` — File profiling (system metadata)
- `tests/` — Unit tests for all modules

## Future TODO
- CLI tool for all features
- Directory pattern and statistics module
- More image format support and advanced checks
- Database integration for storing reports
- Dockerization and deployment guides
- CI/CD workflows and badges

---
`filoma` is under active development. Contributions and suggestions are welcome!