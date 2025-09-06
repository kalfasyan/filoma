"""
High-level interface to fd command-line tool.

This module provides a Python interface to fd, the fast file finder,
allowing filoma to leverage fd's speed and rich filtering capabilities
for file and directory discovery.
"""

import subprocess
from pathlib import Path
from typing import List, Optional, Union

from loguru import logger

from .command_runner import CommandRunner


class FdIntegration:
    """High-level interface to fd command-line tool."""

    def __init__(self):
        """Initialize fd integration and check availability."""
        # Prefer a sanity-checked fd: ensure that invoking `fd --version` returns usable output.
        self.version = CommandRunner.get_command_version("fd")
        self.available = bool(self.version)

        if not self.available:
            logger.warning("fd command not found or not usable in PATH")

    def is_available(self) -> bool:
        """Check if fd is available for use."""
        return self.available

    def get_version(self) -> Optional[str]:
        """Get fd version string."""
        return self.version

    def find(
        self,
        pattern: str = ".",
        path: str = ".",
        max_depth: Optional[int] = None,
        file_types: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        case_sensitive: bool = True,
        follow_links: bool = False,
        search_hidden: bool = False,
        no_ignore: bool = False,
        max_results: Optional[int] = None,
        absolute_paths: bool = False,
        use_glob: bool = False,
        threads: Optional[int] = None,
        **kwargs,
    ) -> List[str]:
        """
        Search for files/directories using fd.

        Args:
            pattern: Search pattern (regex by default, glob if use_glob=True)
            path: Root directory to search in (default: current directory)
            max_depth: Maximum search depth
            file_types: Filter by type ('f'=file, 'd'=directory, 'l'=symlink, etc.)
            exclude_patterns: Patterns to exclude
            case_sensitive: Force case-sensitive search
            follow_links: Follow symbolic links
            search_hidden: Include hidden files/directories
            max_results: Maximum number of results to return
            absolute_paths: Return absolute paths
            use_glob: Use glob patterns instead of regex

        Returns:
            List of file paths (strings)

        Raises:
            RuntimeError: If fd is not available
            subprocess.CalledProcessError: If fd command fails
            subprocess.TimeoutExpired: If fd command times out
        """
        if not self.available:
            raise RuntimeError("fd command not available")

        # Validate path exists
        path_obj = Path(path)
        if not path_obj.exists():
            logger.warning(f"Path does not exist: {path}")
            return []  # Return empty list instead of failing

        if not path_obj.is_dir():
            logger.warning(f"Path is not a directory: {path}")
            return []

        cmd = ["fd"]

        # Handle glob vs regex patterns
        if use_glob:
            cmd.append("--glob")

        # Add pattern - use "." (match all) if no pattern provided or pattern is "."
        if pattern and pattern != ".":
            cmd.append(pattern)
        else:
            # When searching within a directory without a specific pattern, use "." to match all
            cmd.append(".")

        # Add search path if provided
        if path and path != ".":
            cmd.append(str(path))

        # Handle flexible kwargs commonly used by higher-level helpers
        # extensions / extension -> -e
        extensions = kwargs.pop("extension", None) or kwargs.pop("extensions", None)
        if extensions:
            if isinstance(extensions, (list, tuple)):
                for ext in extensions:
                    cmd.extend(["-e", str(ext)])
            else:
                cmd.extend(["-e", str(extensions)])

        # file_type / file_types -> -t
        ft = kwargs.pop("file_type", None) or kwargs.pop("file_types", None) or file_types
        if ft:
            if isinstance(ft, (list, tuple)):
                for t in ft:
                    cmd.extend(["-t", str(t)])
            else:
                cmd.extend(["-t", str(ft)])

        # changed_within -> --changed-within
        changed_within = kwargs.pop("changed_within", None)
        if changed_within:
            cmd.extend(["--changed-within", str(changed_within)])

        # Build command arguments

        if max_depth is not None:
            cmd.extend(["--max-depth", str(max_depth)])

        if search_hidden:
            cmd.append("--hidden")

        # Allow caller to disable fd's ignore-file behavior to match raw traversal
        if no_ignore:
            cmd.append("--no-ignore")

        if absolute_paths:
            cmd.append("--absolute-path")

        if follow_links:
            cmd.append("--follow")

        if exclude_patterns:
            for pattern_exclude in exclude_patterns:
                cmd.extend(["--exclude", pattern_exclude])

        if not case_sensitive:
            cmd.append("--ignore-case")

        if max_results is not None:
            cmd.extend(["--max-results", str(max_results)])

        # Threads control: let fd decide by default, but allow override
        if threads is not None:
            cmd.extend(["--threads", str(threads)])

        try:
            result = CommandRunner.run_command(cmd)

            # Split output into lines and filter empty lines
            paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]

            logger.debug(f"fd found {len(paths)} results")
            return paths

        except subprocess.CalledProcessError as e:
            logger.error(f"fd command failed: {e}")
            if hasattr(e, "stderr") and e.stderr:
                logger.error(f"stderr: {e.stderr}")
            raise

    def search_streaming(self, pattern: Optional[str] = None, path: Optional[Union[str, Path]] = None, **kwargs) -> subprocess.Popen:
        """
        Search for files using fd with streaming output.

        This is useful for very large result sets where you want to process
        results as they come in rather than loading everything into memory.

        Args:
            pattern: Search pattern
            path: Root directory to search in
            **kwargs: Same arguments as search()

        Returns:
            Popen object for streaming access

        Example:
            >>> fd = FdIntegration()
            >>> with fd.search_streaming(".py") as proc:
            ...     for line in proc.stdout:
            ...         path = line.strip()
            ...         if path:
            ...             print(path)
        """
        if not self.available:
            raise RuntimeError("fd command not available")

        # Remove arguments not compatible with streaming
        kwargs.pop("max_results", None)  # Not compatible with streaming
        kwargs.pop("timeout", None)  # Handled at process level

        # Build command using most of the logic from search()
        cmd = ["fd"]

        use_glob = kwargs.pop("use_glob", False)
        if use_glob:
            cmd.append("--glob")

        if pattern:
            cmd.append(pattern)

        if path:
            cmd.append(str(path))

        # Pass through threads if provided
        threads = kwargs.pop("threads", None)
        if threads is not None:
            cmd.extend(["--threads", str(threads)])

        # Forward other common kwargs: changed_within, extensions, file_type
        changed_within = kwargs.pop("changed_within", None)
        if changed_within:
            cmd.extend(["--changed-within", str(changed_within)])

        extensions = kwargs.pop("extension", None) or kwargs.pop("extensions", None)
        if extensions:
            if isinstance(extensions, (list, tuple)):
                for ext in extensions:
                    cmd.extend(["-e", str(ext)])
            else:
                cmd.extend(["-e", str(extensions)])

        return CommandRunner.run_streaming(cmd, text=True)

    def find_by_extension(self, extensions: Union[str, List[str]], path: Union[str, Path] = ".", **kwargs) -> List[str]:
        """
        Find files by extension(s).

        Args:
            extensions: File extension(s) to search for
            path: Root directory to search in
            **kwargs: Additional arguments passed to search()

        Returns:
            List of file paths
        """
        return self.find(
            extension=extensions,
            path=path,
            file_type="f",  # Only files
            **kwargs,
        )

    def find_recent_files(self, path: Union[str, Path] = ".", changed_within: str = "1d", **kwargs) -> List[str]:
        """
        Find recently modified files.

        Args:
            path: Root directory to search in
            changed_within: Time period (e.g., '1d', '2h', '30min')
            **kwargs: Additional arguments passed to search()

        Returns:
            List of file paths
        """
        return self.find(
            path=path,
            changed_within=changed_within,
            file_type="f",  # Only files
            **kwargs,
        )

    def find_empty_directories(self, path: Union[str, Path] = ".", **kwargs) -> List[str]:
        """
        Find empty directories.

        Args:
            path: Root directory to search in
            **kwargs: Additional arguments passed to search()

        Returns:
            List of directory paths
        """
        return self.find(
            path=path,
            file_type="e",  # Empty
            **kwargs,
        )

    def count_files(self, pattern: Optional[str] = None, path: Optional[Union[str, Path]] = None, **kwargs) -> int:
        """
        Count files matching criteria without returning the full list.

        This is more memory-efficient for large result sets.

        Args:
            pattern: Search pattern
            path: Root directory to search in
            **kwargs: Additional arguments passed to search()

        Returns:
            Number of matching files
        """
        # Use streaming approach to count without loading all results
        try:
            with self.search_streaming(pattern=pattern, path=path, **kwargs) as proc:
                count = 0
                for line in proc.stdout:
                    if line.strip():
                        count += 1

                proc.wait()
                return count

        except Exception:
            # Fallback to regular search if streaming fails
            results = self.find(pattern=pattern, path=path, **kwargs)
            return len(results)
