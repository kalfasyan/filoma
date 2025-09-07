# File & Image Profiling

Single file:
```python
from filoma import probe_file
info = probe_file('README.md')
print(info.size, info.modified)
```

Image:
```python
from filoma import probe_image
img = probe_image('images/logo.png')
print(img.file_type, getattr(img, 'shape', None))
```

Numpy array:
```python
import numpy as np
from filoma import probe_image
arr = np.zeros((64,64), dtype=np.uint8)
rep = probe_image(arr)
print(rep.mean, rep.max)
```

Disable hash for speed:
```python
probe_file('big.bin', compute_hash=False)
```

Batch profile selected files via DataFrame:
```python
from filoma import probe_to_df
pl_df = probe_to_df('.')  # returns polars.DataFrame
from filoma.dataframe import DataFrame
wrapper = DataFrame(pl_df).filter_by_extension('.py').add_file_stats_cols()
```

What you get (file dataclass key fields):
- path, size, owner, group, mode_str, created, modified, is_file, is_dir, sha256 (optional), inode

ImageReport common fields:
- path, file_type, shape, dtype, min, max, mean, nans, infs
