import numpy as np


class ImageProfiler:
    """
    Provides common analysis methods for image data loaded as numpy arrays.
    """
    def analyze(self, arr: np.ndarray) -> dict:
        report = {
            "shape": arr.shape,
            "dtype": str(arr.dtype),
            "min": float(np.nanmin(arr)) if arr.size > 0 else None,
            "max": float(np.nanmax(arr)) if arr.size > 0 else None,
            "mean": float(np.nanmean(arr)) if arr.size > 0 else None,
            "nans": int(np.isnan(arr).sum()),
            "infs": int(np.isinf(arr).sum()),
            "unique": int(np.unique(arr).size) if arr.size > 0 else 0,
        }
        return report
