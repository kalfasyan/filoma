This page documents the duplicate-detection and near-duplicate matching utilities available in `filoma`. Use these helpers to evaluate dataset quality, find exact duplicates, and detect near-duplicates in text and images.

### Duplicate Detection

`filoma` provides robust tools for identifying duplicate files based on content hash or metadata.

```python
import filoma

# Find exact duplicates in a directory
df = filoma.probe_to_df(".")
duplicates = df.find_duplicates(by="sha256")
print(duplicates)
```

### Near-Duplicate Detection

For images and text, `filoma` can help identify similar content that isn't an exact byte-for-byte match.

- **Image Hashing**: Detect visually similar images.
- **Text Normalization**: Compare text files after removing whitespace or other noise.

Refer to the [Cookbook](../tutorials/cookbook.md) for more examples.
