#!/usr/bin/env python3
"""
Test script for parallel directory/file profiling (originally in scripts/).
"""

import time
from pathlib import Path

from filoma.directories import DirectoryProfiler


def test_parallel():
    print("Testing parallel directory profiling...")
    profiler = DirectoryProfiler(use_rust=True, use_parallel=True, show_progress=True)
    test_dir = Path.cwd()
    start = time.time()
    result = profiler.probe(str(test_dir), max_depth=2)
    profiler.print_summary(result)
    print(f"Elapsed: {time.time() - start:.2f}s")


if __name__ == "__main__":
    test_parallel()
