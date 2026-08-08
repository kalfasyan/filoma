# Directory Scanning

Basic scan with pretty output:

```python
from filoma import probe
analysis = probe('.')
analysis.print_summary()  # Rich table with key metrics
```

Full detailed report:

```python
analysis.print_report()  # Includes extensions, common folders, empty folders
```

Access data programmatically:

```python
print(analysis.summary)  # Summary statistics dict
print(list(analysis.file_extensions.items())[:5])  # Top extensions
print(analysis.top_folders_by_file_count[:3])  # Largest folders
```

Limit depth & hide progress:

```python
analysis = probe('.', max_depth=3, show_progress=False)
```

Select backend explicitly (rarely needed):

```python
from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig
DirectoryProfiler(DirectoryProfilerConfig(search_backend='fd')).probe('.')
```

Choose the Rust traversal engine (default `auto` picks the dua-core parallel walker on local filesystems):

```python
DirectoryProfiler(DirectoryProfilerConfig(search_backend='rust', walker='dua-core'))
DirectoryProfiler(DirectoryProfilerConfig(search_backend='rust', walker='walkdir'))
```

Fast path only (paths without metadata):

```python
from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig
fast = DirectoryProfiler(DirectoryProfilerConfig(fast_path_only=True)).probe('.')
```

Network tuning example:

```python
DirectoryProfiler(DirectoryProfilerConfig(network_concurrency=32, network_timeout_ms=2000)).probe('/mnt/nfs')
```

Common flags:

- `max_depth`: limit recursion.
- `search_hidden`: include dotfiles.
- `follow_links`: follow symlinks (default `False` — symlinks are reported but not counted).
- `fast_path_only`: skip metadata.
- `walker`: `dua-core` / `walkdir` / `auto` (Rust engine selection).
- `walker_threads`: worker count for the dua-core engine.

Inspect raw structure (dict-like):

```python
print(analysis['summary'])
print(list(analysis['file_extensions'].items())[:5])
```
