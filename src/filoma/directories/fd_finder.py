"""Direct interface to fd for search operations.

This module provides a user-friendly interface to fd's search capabilities,
designed for standalone use or integration with other filoma components.

When the ``fd`` binary is not available on PATH, the finder transparently
falls back to a pure-Python implementation built on top of :func:`os.walk`,
so callers always get usable results (just slower and with reduced
``.gitignore`` semantics).
"""

import fnmatch
import os
import re
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Union

from loguru import logger

from ..core import FdIntegration

try:
    from ..dataframe import DataFrame as FilomaDataFrame

    _HAS_DF = True
except Exception:
    FilomaDataFrame = None
    _HAS_DF = False


# Directories commonly excluded by ``.gitignore``-aware tools. Used by the
# Python fallback when ``no_ignore`` is False (the default).
_DEFAULT_IGNORE_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "target",
        "dist",
        "build",
        ".next",
        ".nuxt",
        ".cache",
        ".idea",
        ".vscode",
    }
)


class FdFinder:
    """Direct interface to fd for search operations.

    When ``fd`` is unavailable on PATH, methods fall back to a pure-Python
    implementation using :func:`os.walk`. The fallback honors ``max_depth``,
    ``hidden`` and ``case_sensitive``, and skips a default set of cache /
    VCS directories unless ``no_ignore=True`` is passed.
    """

    def __init__(self):
        """Initialize the fd searcher."""
        self.fd = FdIntegration()

        if not self.fd.is_available():
            logger.warning(
                "fd command not found. Falling back to a pure-Python scanner. "
                "Install fd for faster, gitignore-aware search: "
                "https://github.com/sharkdp/fd#installation"
            )

    def is_available(self) -> bool:
        """Check if fd is available for use."""
        return self.fd.is_available()

    def get_version(self) -> Optional[str]:
        """Get fd version information."""
        return self.fd.get_version()

    # ------------------------------------------------------------------
    # Pure-Python fallback (used when the ``fd`` binary is unavailable)
    # ------------------------------------------------------------------

    @staticmethod
    def _walk_python(
        path: Union[str, Path],
        max_depth: Optional[int] = None,
        hidden: bool = False,
        no_ignore: bool = False,
        yield_files: bool = True,
        yield_dirs: bool = False,
    ):
        """Yield (full_path, is_dir) tuples using :func:`os.walk`.

        Honors ``max_depth`` (1 = top level only), skips entries beginning
        with ``.`` unless ``hidden=True``, and skips a default set of cache /
        VCS directories unless ``no_ignore=True``.
        """
        root = Path(path)
        try:
            root_str = str(root.resolve())
        except OSError:
            root_str = str(root)

        if not root.is_dir():
            return

        for current, dirs, files in os.walk(root_str, followlinks=False):
            rel = os.path.relpath(current, root_str)
            depth = 0 if rel in (".", "") else rel.count(os.sep) + 1

            # Filter directories in-place to control descent and visibility.
            if not hidden:
                dirs[:] = [d for d in dirs if not d.startswith(".")]
            if not no_ignore:
                dirs[:] = [d for d in dirs if d not in _DEFAULT_IGNORE_DIR_NAMES]

            if max_depth is not None and depth >= max_depth:
                # Yield current-level dirs/files but don't descend further.
                pruned_dirs = list(dirs)
                dirs.clear()
            else:
                pruned_dirs = dirs

            if yield_dirs and depth > 0:
                # ``current`` itself is a directory at depth ``depth``.
                yield current, True

            if yield_dirs and (max_depth is None or depth < max_depth):
                # When we've cleared dirs above we still want to yield them.
                for d in pruned_dirs:
                    yield os.path.join(current, d), True

            if yield_files:
                for f in files:
                    if not hidden and f.startswith("."):
                        continue
                    yield os.path.join(current, f), False

    @staticmethod
    def _compile_pattern(pattern: str, use_glob: bool, case_sensitive: bool):
        """Compile a search pattern into a callable that takes a basename."""
        if not pattern or pattern == ".":
            return lambda _name: True

        if use_glob:
            translated = fnmatch.translate(pattern)
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                regex = re.compile(translated, flags)
            except re.error as exc:
                logger.warning(f"Invalid glob pattern '{pattern}': {exc}")
                return lambda _name: False
            return lambda name: bool(regex.match(name))

        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            regex = re.compile(pattern, flags)
        except re.error as exc:
            logger.warning(f"Invalid regex pattern '{pattern}': {exc}")
            return lambda _name: False
        return lambda name: bool(regex.search(name))

    @classmethod
    def _python_find(
        cls,
        pattern: str,
        path: Union[str, Path],
        file_types: Optional[List[str]] = None,
        max_depth: Optional[int] = None,
        hidden: bool = False,
        case_sensitive: bool = True,
        no_ignore: bool = False,
        use_glob: bool = False,
    ) -> List[str]:
        """Pure-Python fallback for :meth:`FdIntegration.find`."""
        if not Path(path).exists():
            logger.warning(f"Path does not exist: {path}")
            return []

        types = set(file_types or ["f"])
        match = cls._compile_pattern(pattern, use_glob=use_glob, case_sensitive=case_sensitive)

        results: List[str] = []
        start = time.time()
        for entry, is_dir in cls._walk_python(
            path,
            max_depth=max_depth,
            hidden=hidden,
            no_ignore=no_ignore,
            yield_files="f" in types,
            yield_dirs="d" in types,
        ):
            name = os.path.basename(entry)
            if match(name):
                results.append(entry)
        elapsed = time.time() - start
        logger.debug(
            f"Python fallback scan of '{path}' returned {len(results)} entries "
            f"in {elapsed:.2f}s (pattern='{pattern}', types={sorted(types)})"
        )
        return results

    def find_files(
        self,
        pattern: str = "",
        path: Union[str, Path] = ".",
        max_depth: Optional[int] = None,
        hidden: bool = False,
        case_sensitive: Optional[bool] = None,
        threads: Optional[int] = None,
        **fd_options,
    ) -> List[str]:
        r"""Find files matching pattern.

        Args:
        ----
            pattern: Search pattern (regex by default, glob if use_glob=True).
            path: Directory to search in.
            max_depth: Maximum depth to search.
            hidden: Include hidden files.
            case_sensitive: Force case sensitivity.
            threads: Optional number of worker threads to use for the search.
            **fd_options: Additional fd options (e.g., use_glob=True for glob patterns).

        Returns:
        -------
            List of file paths.

        Example:
        -------
            >>> searcher = FdFinder()
            >>> python_files = searcher.find_files(r"\.py$", "/src")
            >>> config_files = searcher.find_files("*.{json,yaml}", use_glob=True)

        """
        if not self.fd.is_available():
            return self._python_find(
                pattern=pattern,
                path=path,
                file_types=["f"],
                max_depth=max_depth,
                hidden=hidden,
                case_sensitive=case_sensitive if case_sensitive is not None else True,
                no_ignore=bool(fd_options.get("no_ignore", False)),
                use_glob=bool(fd_options.get("use_glob", False)),
            )
        try:
            return self.fd.find(
                pattern=pattern or ".",
                path=str(path),
                file_types=["f"],
                max_depth=max_depth,
                search_hidden=hidden,
                case_sensitive=case_sensitive if case_sensitive is not None else True,
                threads=threads,
                **fd_options,  # Pass through additional fd options including use_glob
            )
        except Exception as e:
            logger.warning(f"FdFinder.find_files failed for path '{path}': {e}")
            return []  # Return empty list instead of raising

    def to_dataframe(
        self,
        pattern: str = "",
        path: Union[str, Path] = ".",
        threads: Optional[int] = None,
        **fd_options,
    ):
        """Run an fd search and return a `filoma.DataFrame` of results.

        If the DataFrame feature isn't available (polars missing), return a list of paths.
        """
        paths = self.find_files(pattern=pattern, path=path, threads=threads, **fd_options)
        if _HAS_DF and FilomaDataFrame is not None:
            return FilomaDataFrame(paths)
        return paths

    def find_directories(
        self,
        pattern: str = "",
        path: Union[str, Path] = ".",
        max_depth: Optional[int] = None,
        hidden: bool = False,
        **fd_options,
    ) -> List[str]:
        """Find directories matching pattern.

        Args:
        ----
            pattern: Search pattern (regex by default, glob if use_glob=True)
            path: Directory to search in
            max_depth: Maximum depth to search
            hidden: Include hidden directories
            **fd_options: Additional fd options (e.g., use_glob=True for glob patterns)

        Returns:
        -------
            List of directory paths

        """
        if not self.fd.is_available():
            return self._python_find(
                pattern=pattern,
                path=path,
                file_types=["d"],
                max_depth=max_depth,
                hidden=hidden,
                case_sensitive=bool(fd_options.get("case_sensitive", True)),
                no_ignore=bool(fd_options.get("no_ignore", False)),
                use_glob=bool(fd_options.get("use_glob", False)),
            )
        try:
            return self.fd.find(
                pattern=pattern or ".",
                path=str(path),
                file_types=["d"],
                max_depth=max_depth,
                search_hidden=hidden,
                threads=fd_options.pop("threads", None),
                **fd_options,  # Pass through additional fd options
            )
        except Exception as e:
            logger.warning(f"FdFinder.find_directories failed for path '{path}': {e}")
            return []  # Return empty list instead of raising

    def find_by_extension(
        self,
        extensions: Union[str, List[str]],
        path: Union[str, Path] = ".",
        max_depth: Optional[int] = None,
        **fd_options,
    ) -> List[str]:
        """Find files by extension(s).

        Args:
        ----
            extensions: File extension(s) to search for (with or without dots)
            path: Directory to search in
            max_depth: Maximum depth to search
            **fd_options: Additional fd options

        Returns:
        -------
            List of file paths

        Example:
        -------
            >>> searcher = FdFinder()
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

        # Pure-Python fallback when fd is missing.
        if not self.fd.is_available():
            hidden = bool(fd_options.get("hidden", False))
            no_ignore = bool(fd_options.get("no_ignore", False))
            case_sensitive = bool(fd_options.get("case_sensitive", True))
            all_files: List[str] = []
            for pattern in patterns:
                all_files.extend(
                    self._python_find(
                        pattern=pattern,
                        path=path,
                        file_types=["f"],
                        max_depth=max_depth,
                        hidden=hidden,
                        case_sensitive=case_sensitive,
                        no_ignore=no_ignore,
                        use_glob=True,
                    )
                )
            return list(set(all_files))

        # Use glob mode to search for all patterns
        all_files = []
        try:
            for pattern in patterns:
                files = self.fd.find(
                    pattern=pattern,
                    path=str(path),
                    file_types=["f"],
                    max_depth=max_depth,
                    use_glob=True,
                    threads=fd_options.pop("threads", None),
                )
                all_files.extend(files)

            return list(set(all_files))  # Remove duplicates
        except Exception as e:
            logger.warning(f"FdFinder.find_by_extension failed for path '{path}': {e}")
            return []  # Return empty list instead of raising

    def find_recent_files(
        self,
        path: Union[str, Path] = ".",
        changed_within: str = "1d",
        extension: Optional[Union[str, List[str]]] = None,
        **fd_options,
    ) -> List[str]:
        """Find recently modified files.

        Args:
        ----
            path: Directory to search in
            changed_within: Time period (e.g., '1d', '2h', '30min')
            extension: Optional file extension filter
            **fd_options: Additional fd options

        Returns:
        -------
            List of file paths

        Example:
        -------
            >>> searcher = FdFinder()
            >>> recent_python = searcher.find_recent_files(
            ...     changed_within="1h", extension="py"
            ... )

        """
        if extension:
            fd_options["extension"] = extension

        if not self.fd.is_available():
            try:
                window_seconds = _parse_duration_string(changed_within)
            except ValueError as exc:
                logger.warning(
                    f"FdFinder.find_recent_files: invalid changed_within '{changed_within}': {exc}"
                )
                return []
            cutoff = time.time() - window_seconds
            hidden = bool(fd_options.get("hidden", False))
            no_ignore = bool(fd_options.get("no_ignore", False))
            max_depth = fd_options.get("max_depth")
            ext_filter = None
            if extension:
                exts = [extension] if isinstance(extension, str) else list(extension)
                ext_filter = {("." + e.lstrip(".").lower()) for e in exts}
            results: List[str] = []
            for entry, _is_dir in self._walk_python(
                path,
                max_depth=max_depth,
                hidden=hidden,
                no_ignore=no_ignore,
                yield_files=True,
                yield_dirs=False,
            ):
                if ext_filter is not None:
                    if Path(entry).suffix.lower() not in ext_filter:
                        continue
                try:
                    if os.path.getmtime(entry) >= cutoff:
                        results.append(entry)
                except OSError:
                    continue
            return results

        try:
            return self.fd.find_recent_files(path=path, changed_within=changed_within, **fd_options)
        except Exception as e:
            logger.warning(f"FdFinder.find_recent_files failed for path '{path}': {e}")
            return []

    def find_large_files(
        self,
        path: Union[str, Path] = ".",
        min_size: str = "1M",
        max_depth: Optional[int] = None,
        **fd_options,
    ) -> List[str]:
        """Find large files.

        Args:
        ----
            path: Directory to search in.
            min_size: Minimum file size (e.g., '1M', '100k', '1G').
            max_depth: Maximum depth to search.
            **fd_options: Additional fd options.

        Returns:
        -------
            List of file paths.

        Example:
        -------
            >>> searcher = FdFinder()
            >>> large_files = searcher.find_large_files(min_size="10M")

        """
        if not self.fd.is_available():
            try:
                threshold = _parse_size_string(min_size)
            except ValueError as exc:
                logger.warning(f"FdFinder.find_large_files: invalid min_size '{min_size}': {exc}")
                return []
            hidden = bool(fd_options.get("hidden", False))
            no_ignore = bool(fd_options.get("no_ignore", False))
            results: List[str] = []
            for entry, _is_dir in self._walk_python(
                path,
                max_depth=max_depth,
                hidden=hidden,
                no_ignore=no_ignore,
                yield_files=True,
                yield_dirs=False,
            ):
                try:
                    if os.path.getsize(entry) >= threshold:
                        results.append(entry)
                except OSError:
                    continue
            return results
        try:
            return self.fd.find(
                path=path,
                file_type="f",
                size=f"+{min_size}",
                max_depth=max_depth,
                **fd_options,
            )
        except Exception as e:
            logger.warning(f"FdFinder.find_large_files failed for path '{path}': {e}")
            return []

    def find_empty_directories(self, path: Union[str, Path] = ".", **fd_options) -> List[str]:
        """Find empty directories.

        Args:
        ----
            path: Directory to search in.
            **fd_options: Additional fd options.

        Returns:
        -------
            List of empty directory paths.

        """
        if not self.fd.is_available():
            hidden = bool(fd_options.get("hidden", False))
            no_ignore = bool(fd_options.get("no_ignore", False))
            results: List[str] = []
            root = Path(path)
            if not root.is_dir():
                return results
            try:
                root_str = str(root.resolve())
            except OSError:
                root_str = str(root)
            for current, dirs, files in os.walk(root_str, followlinks=False):
                if not hidden:
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                if not no_ignore:
                    dirs[:] = [d for d in dirs if d not in _DEFAULT_IGNORE_DIR_NAMES]
                visible_files = files if hidden else [f for f in files if not f.startswith(".")]
                if not dirs and not visible_files and current != root_str:
                    results.append(current)
            return results
        try:
            return self.fd.find_empty_directories(path=path, **fd_options)
        except Exception as e:
            logger.warning(f"FdFinder.find_empty_directories failed for path '{path}': {e}")
            return []

    def count_files(self, pattern: str = "", path: Union[str, Path] = ".", **fd_options) -> int:
        """Count files matching criteria without returning the full list.

        Args:
        ----
            pattern: Search pattern.
            path: Directory to search in.
            **fd_options: Additional fd options.

        Returns:
        -------
            Number of matching files.

        """
        if not self.fd.is_available():
            return len(
                self._python_find(
                    pattern=pattern,
                    path=path,
                    file_types=["f"],
                    max_depth=fd_options.get("max_depth"),
                    hidden=bool(fd_options.get("hidden", False)),
                    case_sensitive=bool(fd_options.get("case_sensitive", True)),
                    no_ignore=bool(fd_options.get("no_ignore", False)),
                    use_glob=bool(fd_options.get("use_glob", False)),
                )
            )
        try:
            return self.fd.count_files(pattern=pattern or None, path=path, **fd_options)
        except Exception as e:
            logger.warning(f"FdFinder.count_files failed for path '{path}': {e}")
            return 0

    def execute_on_results(
        self,
        pattern: str,
        command: List[str],
        path: Union[str, Path] = ".",
        parallel: bool = True,
        **fd_options,
    ) -> subprocess.CompletedProcess:
        r"""Execute command on search results using fd's built-in execution.

        Args:
        ----
            pattern: Search pattern.
            command: Command and arguments to execute.
            path: Directory to search in.
            parallel: Whether to run commands in parallel.
            **fd_options: Additional fd options.

        Returns:
        -------
            CompletedProcess object.

        Example:
        -------
            >>> searcher = FdFinder()
            >>> # Delete all .tmp files
            >>> searcher.execute_on_results(
            ...     r"\.tmp$", ["rm"], parallel=False
            ... )

        """
        if not self.fd.is_available():
            raise RuntimeError("fd command not available")

        from ..core import CommandRunner

        cmd = ["fd", pattern, str(path)]

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

    def get_stats(self, path: Union[str, Path] = ".") -> dict:
        """Get basic statistics about a directory using fd.

        Args:
        ----
            path: Directory to probe

        Returns:
        -------
            Dictionary with basic stats

        Example:
        -------
            >>> searcher = FdFinder()
            >>> stats = searcher.get_stats("/project")
            >>> print(f"Files: {stats['file_count']}")

        """
        if not self.fd.is_available():
            file_count = 0
            dir_count = 0
            for _entry, is_dir in self._walk_python(
                path,
                yield_files=True,
                yield_dirs=True,
            ):
                if is_dir:
                    dir_count += 1
                else:
                    file_count += 1
            return {
                "file_count": file_count,
                "directory_count": dir_count,
                "total_items": file_count + dir_count,
                "backend": "python",
            }

        try:
            file_count = self.fd.count_files(path=path, file_type="f")
            dir_count = self.fd.count_files(path=path, file_type="d")

            return {
                "file_count": file_count,
                "directory_count": dir_count,
                "total_items": file_count + dir_count,
            }

        except Exception as e:
            logger.error(f"Failed to get directory stats for path '{path}': {e}")
            return {"file_count": 0, "directory_count": 0, "error": str(e)}


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


_SIZE_SUFFIXES = {
    "": 1,
    "b": 1,
    "k": 1024,
    "kb": 1024,
    "kib": 1024,
    "m": 1024**2,
    "mb": 1024**2,
    "mib": 1024**2,
    "g": 1024**3,
    "gb": 1024**3,
    "gib": 1024**3,
    "t": 1024**4,
    "tb": 1024**4,
    "tib": 1024**4,
}


def _parse_size_string(size: str) -> int:
    """Parse a size string like ``'1M'`` or ``'500k'`` into bytes.

    Mirrors the size shorthand accepted by ``fd``'s ``--size`` flag closely
    enough for the Python fallback to behave the same way for common inputs.
    """
    if size is None:
        raise ValueError("size must be a non-empty string")
    text = str(size).strip().lower()
    if not text:
        raise ValueError("size must be a non-empty string")
    # Strip optional leading sign expected by fd's `+`/`-` size syntax.
    if text[0] in "+-":
        text = text[1:]
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([a-z]*)", text)
    if not match:
        raise ValueError(f"unrecognized size string: {size!r}")
    number = float(match.group(1))
    suffix = match.group(2)
    if suffix not in _SIZE_SUFFIXES:
        raise ValueError(f"unsupported size suffix: {suffix!r}")
    return int(number * _SIZE_SUFFIXES[suffix])


_DURATION_SUFFIXES = {
    "s": 1,
    "sec": 1,
    "secs": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "hour": 3600,
    "hours": 3600,
    "d": 86400,
    "day": 86400,
    "days": 86400,
    "w": 86400 * 7,
    "week": 86400 * 7,
    "weeks": 86400 * 7,
}


def _parse_duration_string(duration: str) -> float:
    """Parse a duration string like ``'1d'``, ``'2h'``, ``'30min'`` into seconds.

    Mirrors the time shorthand accepted by ``fd``'s ``--changed-within`` flag.
    """
    if duration is None:
        raise ValueError("duration must be a non-empty string")
    text = str(duration).strip().lower()
    if not text:
        raise ValueError("duration must be a non-empty string")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([a-z]*)", text)
    if not match:
        raise ValueError(f"unrecognized duration string: {duration!r}")
    number = float(match.group(1))
    suffix = match.group(2) or "s"
    if suffix not in _DURATION_SUFFIXES:
        raise ValueError(f"unsupported duration suffix: {suffix!r}")
    return number * _DURATION_SUFFIXES[suffix]
