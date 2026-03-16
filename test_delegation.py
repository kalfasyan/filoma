"""Test for delegation of directory profiling."""
from src.filoma.directories.directory_profiler import DirectoryProfiler, DirectoryProfilerConfig

config = DirectoryProfilerConfig()
profiler = DirectoryProfiler(config)
analysis = profiler.probe(".")

print(f"Path: {analysis.path}")
print(f"Parts: {analysis.parts}")
print(f"As Posix: {analysis.as_posix()}")
print(f"Total Files: {analysis.summary['total_files']}")
