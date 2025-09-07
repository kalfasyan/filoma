# Directory Scanning

Basic scan:
```python
from filoma import probe
analysis = probe('.')
analysis.print_summary()
```

Report:
```python
analysis.print_report()
```

Limit depth & hide progress:
```python
analysis = probe('.', max_depth=3, show_progress=False)
```

Select backend explicitly (rarely needed):
```python
from filoma.directories import DirectoryProfiler
DirectoryProfiler(search_backend='fd').probe('.')
```

Fast path only (paths without metadata):
```python
from filoma.directories import DirectoryProfiler
fast = DirectoryProfiler(fast_path_only=True).probe('.')
```

Network tuning example:
```python
DirectoryProfiler(network_concurrency=32, network_timeout_ms=2000).probe('/mnt/nfs')
```

Common flags:
- `max_depth`: limit recursion.
- `search_hidden`: include dotfiles.
- `follow_links`: follow symlinks.
- `fast_path_only`: skip metadata.

Inspect raw structure (dict-like):
```python
print(analysis['summary'])
print(list(analysis['file_extensions'].items())[:5])
```
