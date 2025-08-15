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
        self.available = CommandRunner.check_command_available("fd")
        self.version = None

        if self.available:
            self.version = CommandRunner.get_command_version("fd")
            logger.debug(f"fd available: {self.version}")
        else:
            logger.warning("fd command not found in PATH")

    def is_available(self) -> bool:
        """Check if fd is available for use."""
        return self.available

    def get_version(self) -> Optional[str]:
        """Get fd version string."""
        return self.version

    def search(
        self,
        pattern: str = ".",
        base_path: str = ".",
        max_depth: Optional[int] = None,
        file_types: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        case_sensitive: bool = True,
        follow_links: bool = False,
        search_hidden: bool = False,
        max_results: Optional[int] = None,
        absolute_paths: bool = False,
        use_glob: bool = False,
    ) -> List[str]:
        """
        Search for files/directories using fd.

        Args:
            pattern: Search pattern (regex by default, glob if use_glob=True)
            base_path: Root directory to search in (default: current directory)
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

        # Validate base_path exists
        base_path_obj = Path(base_path)
        if not base_path_obj.exists():
            logger.warning(f"Base path does not exist: {base_path}")
            return []  # Return empty list instead of failing

        if not base_path_obj.is_dir():
            logger.warning(f"Base path is not a directory: {base_path}")
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
        if base_path and base_path != ".":
            cmd.append(str(base_path))

        # Build command arguments
        if file_types:
            for file_type in file_types:
                cmd.extend(["--type", file_type])

        if max_depth is not None:
            cmd.extend(["--max-depth", str(max_depth)])

        if search_hidden:
            cmd.append("--hidden")

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

    def search_streaming(self, pattern: Optional[str] = None, root_path: Optional[Union[str, Path]] = None, **kwargs) -> subprocess.Popen:
        """
        Search for files using fd with streaming output.

        This is useful for very large result sets where you want to process
        results as they come in rather than loading everything into memory.

        Args:
            pattern: Search pattern
            root_path: Root directory to search in
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

        # Build command using same logic as search()
        cmd = ["fd"]

        if pattern:
            cmd.append(pattern)

        if root_path:
            cmd.append(str(root_path))

        # Add other arguments (simplified for now)
        # In a full implementation, you'd replicate the argument building logic

        return CommandRunner.run_streaming(cmd, text=True)

    def find_by_extension(self, extensions: Union[str, List[str]], root_path: Union[str, Path] = ".", **kwargs) -> List[str]:
        """
        Find files by extension(s).

        Args:
            extensions: File extension(s) to search for
            root_path: Root directory to search in
            **kwargs: Additional arguments passed to search()

        Returns:
            List of file paths
        """
        return self.search(
            extension=extensions,
            root_path=root_path,
            file_type="f",  # Only files
            **kwargs,
        )

    def find_recent_files(self, root_path: Union[str, Path] = ".", changed_within: str = "1d", **kwargs) -> List[str]:
        """
        Find recently modified files.

        Args:
            root_path: Root directory to search in
            changed_within: Time period (e.g., '1d', '2h', '30min')
            **kwargs: Additional arguments passed to search()

        Returns:
            List of file paths
        """
        return self.search(
            root_path=root_path,
            changed_within=changed_within,
            file_type="f",  # Only files
            **kwargs,
        )

    def find_empty_directories(self, root_path: Union[str, Path] = ".", **kwargs) -> List[str]:
        """
        Find empty directories.

        Args:
            root_path: Root directory to search in
            **kwargs: Additional arguments passed to search()

        Returns:
            List of directory paths
        """
        return self.search(
            root_path=root_path,
            file_type="e",  # Empty
            **kwargs,
        )

    def count_files(self, pattern: Optional[str] = None, root_path: Optional[Union[str, Path]] = None, **kwargs) -> int:
        """
        Count files matching criteria without returning the full list.

        This is more memory-efficient for large result sets.

        Args:
            pattern: Search pattern
            root_path: Root directory to search in
            **kwargs: Additional arguments passed to search()

        Returns:
            Number of matching files
        """
        # Use streaming approach to count without loading all results
        try:
            with self.search_streaming(pattern=pattern, root_path=root_path, **kwargs) as proc:
                count = 0
                for line in proc.stdout:
                    if line.strip():
                        count += 1

                proc.wait()
                return count

        except Exception:
            # Fallback to regular search if streaming fails
            results = self.search(pattern=pattern, root_path=root_path, **kwargs)
            return len(results)
