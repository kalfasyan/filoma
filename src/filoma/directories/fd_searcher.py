"""
Direct interface to fd for search operations.

This module provides a user-friendly interface to fd's search capabilities,
designed for standalone use or integration with other filoma components.
"""

import subprocess
from pathlib import Path
from typing import List, Optional, Union

from loguru import logger

from ..core import FdIntegration


class FdSearcher:
    """Direct interface to fd for search operations."""

    def __init__(self):
        """Initialize the fd searcher."""
        self.fd = FdIntegration()

        if not self.fd.is_available():
            logger.warning("fd command not found. Install fd for enhanced search capabilities: https://github.com/sharkdp/fd#installation")

    def is_available(self) -> bool:
        """Check if fd is available for use."""
        return self.fd.is_available()

    def get_version(self) -> Optional[str]:
        """Get fd version information."""
        return self.fd.get_version()

    def find_files(
        self,
        pattern: str = "",
        directory: Union[str, Path] = ".",
        max_depth: Optional[int] = None,
        hidden: bool = False,
        case_sensitive: Optional[bool] = None,
        **fd_options,
    ) -> List[str]:
        r"""
        Find files matching pattern.

        Args:
            pattern: Search pattern (regex by default, glob if use_glob=True)
            directory: Directory to search in
            max_depth: Maximum depth to search
            hidden: Include hidden files
            case_sensitive: Force case sensitivity
            **fd_options: Additional fd options (e.g., use_glob=True for glob patterns)

        Returns:
            List of file paths

        Example:
            >>> searcher = FdSearcher()
            >>> python_files = searcher.find_files(r"\.py$", "/src")
            >>> config_files = searcher.find_files("*.{json,yaml}", use_glob=True)
        """
        try:
            return self.fd.search(
                pattern=pattern or ".",
                base_path=str(directory),
                file_types=["f"],
                max_depth=max_depth,
                search_hidden=hidden,
                case_sensitive=case_sensitive if case_sensitive is not None else True,
                **fd_options,  # Pass through additional fd options including use_glob
            )
        except Exception as e:
            logger.warning(f"FdSearcher.find_files failed for directory '{directory}': {e}")
            return []  # Return empty list instead of raising

    def find_directories(
        self, pattern: str = "", directory: Union[str, Path] = ".", max_depth: Optional[int] = None, hidden: bool = False, **fd_options
    ) -> List[str]:
        """
        Find directories matching pattern.

        Args:
            pattern: Search pattern (regex by default, glob if use_glob=True)
            directory: Directory to search in
            max_depth: Maximum depth to search
            hidden: Include hidden directories
            **fd_options: Additional fd options (e.g., use_glob=True for glob patterns)

        Returns:
            List of directory paths
        """
        try:
            return self.fd.search(
                pattern=pattern or ".",
                base_path=str(directory),
                file_types=["d"],
                max_depth=max_depth,
                search_hidden=hidden,
                **fd_options,  # Pass through additional fd options
            )
        except Exception as e:
            logger.warning(f"FdSearcher.find_directories failed for directory '{directory}': {e}")
            return []  # Return empty list instead of raising

    def find_by_extension(
        self, extensions: Union[str, List[str]], directory: Union[str, Path] = ".", max_depth: Optional[int] = None, **fd_options
    ) -> List[str]:
        """
        Find files by extension(s).

        Args:
            extensions: File extension(s) to search for (with or without dots)
            directory: Directory to search in
            max_depth: Maximum depth to search
            **fd_options: Additional fd options

        Returns:
            List of file paths

        Example:
            >>> searcher = FdSearcher()
            >>> code_files = searcher.find_by_extension([".py", ".rs", ".js"])
        """
        # Normalize extensions (ensure they don't start with dots for fd)
        if isinstance(extensions, str):
            extensions = [extensions]

        normalized_extensions = []
        for ext in extensions:
            ext = ext.strip()
            if ext.startswith("."):
                ext = ext[1:]  # Remove leading dot for fd
            normalized_extensions.append(ext)

        # Build glob patterns for the extensions
        patterns = []
        for ext in normalized_extensions:
            patterns.append(f"*.{ext}")

        # Use glob mode to search for all patterns
        all_files = []
        try:
            for pattern in patterns:
                files = self.fd.search(
                    pattern=pattern,
                    base_path=str(directory),
                    file_types=["f"],
                    max_depth=max_depth,
                    use_glob=True,
                )
                all_files.extend(files)

            return list(set(all_files))  # Remove duplicates
        except Exception as e:
            logger.warning(f"FdSearcher.find_by_extension failed for directory '{directory}': {e}")
            return []  # Return empty list instead of raising

    def find_recent_files(
        self, directory: Union[str, Path] = ".", changed_within: str = "1d", extension: Optional[Union[str, List[str]]] = None, **fd_options
    ) -> List[str]:
        """
        Find recently modified files.

        Args:
            directory: Directory to search in
            changed_within: Time period (e.g., '1d', '2h', '30min')
            extension: Optional file extension filter
            **fd_options: Additional fd options

        Returns:
            List of file paths

        Example:
            >>> searcher = FdSearcher()
            >>> recent_python = searcher.find_recent_files(
            ...     changed_within="1h", extension="py"
            ... )
        """
        if extension:
            fd_options["extension"] = extension

        return self.fd.find_recent_files(root_path=directory, changed_within=changed_within, **fd_options)

    def find_large_files(self, directory: Union[str, Path] = ".", min_size: str = "1M", max_depth: Optional[int] = None, **fd_options) -> List[str]:
        """
        Find large files.

        Args:
            directory: Directory to search in
            min_size: Minimum file size (e.g., '1M', '100k', '1G')
            max_depth: Maximum depth to search
            **fd_options: Additional fd options

        Returns:
            List of file paths

        Example:
            >>> searcher = FdSearcher()
            >>> large_files = searcher.find_large_files(min_size="10M")
        """
        return self.fd.search(root_path=directory, file_type="f", size=f"+{min_size}", max_depth=max_depth, **fd_options)

    def find_empty_directories(self, directory: Union[str, Path] = ".", **fd_options) -> List[str]:
        """
        Find empty directories.

        Args:
            directory: Directory to search in
            **fd_options: Additional fd options

        Returns:
            List of empty directory paths
        """
        return self.fd.find_empty_directories(root_path=directory, **fd_options)

    def count_files(self, pattern: str = "", directory: Union[str, Path] = ".", **fd_options) -> int:
        """
        Count files matching criteria without returning the full list.

        Args:
            pattern: Search pattern
            directory: Directory to search in
            **fd_options: Additional fd options

        Returns:
            Number of matching files
        """
        return self.fd.count_files(pattern=pattern or None, root_path=directory, **fd_options)

    def execute_on_results(
        self, pattern: str, command: List[str], directory: Union[str, Path] = ".", parallel: bool = True, **fd_options
    ) -> subprocess.CompletedProcess:
        r"""
        Execute command on search results using fd's built-in execution.

        Args:
            pattern: Search pattern
            command: Command and arguments to execute
            directory: Directory to search in
            parallel: Whether to run commands in parallel
            **fd_options: Additional fd options

        Returns:
            CompletedProcess object

        Example:
            >>> searcher = FdSearcher()
            >>> # Delete all .tmp files
            >>> searcher.execute_on_results(
            ...     r"\.tmp$", ["rm"], parallel=False
            ... )
        """
        if not self.fd.is_available():
            raise RuntimeError("fd command not available")

        from ..core import CommandRunner

        cmd = ["fd", pattern, str(directory)]

        # Add fd options
        for key, value in fd_options.items():
            key_arg = f"--{key.replace('_', '-')}"
            if isinstance(value, bool) and value:
                cmd.append(key_arg)
            elif not isinstance(value, bool):
                cmd.extend([key_arg, str(value)])

        # Add execution options
        if parallel:
            cmd.append("--exec")
        else:
            cmd.extend(["--exec", "--threads", "1"])

        cmd.extend(command)

        return CommandRunner.run_command(cmd, capture_output=True, text=True)

    def get_stats(self, directory: Union[str, Path] = ".") -> dict:
        """
        Get basic statistics about a directory using fd.

        Args:
            directory: Directory to analyze

        Returns:
            Dictionary with basic stats

        Example:
            >>> searcher = FdSearcher()
            >>> stats = searcher.get_stats("/project")
            >>> print(f"Files: {stats['file_count']}")
        """
        if not self.fd.is_available():
            return {"file_count": 0, "directory_count": 0, "error": "fd not available"}

        try:
            file_count = self.fd.count_files(root_path=directory, file_type="f")
            dir_count = self.fd.count_files(root_path=directory, file_type="d")

            return {
                "file_count": file_count,
                "directory_count": dir_count,
                "total_items": file_count + dir_count,
            }

        except Exception as e:
            logger.error(f"Failed to get directory stats: {e}")
            return {"file_count": 0, "directory_count": 0, "error": str(e)}
