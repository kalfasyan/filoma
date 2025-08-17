"""
Generic command execution utility for external tools.

This module provides a safe and efficient way to execute external commands
with proper error handling, timeout support, and result processing.
"""

import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Union

from loguru import logger


class CommandRunner:
    """Generic command execution utility for external tools."""

    @staticmethod
    def check_command_available(command: str) -> bool:
        """
        Check if a command is available in PATH.

        Args:
            command: Command name to check (e.g., 'fd', 'find', 'ls')

        Returns:
            True if command is available, False otherwise
        """
        return shutil.which(command) is not None

    @staticmethod
    def run_command(
        cmd: List[str],
        cwd: Optional[Union[str, Path]] = None,
        capture_output: bool = True,
        timeout: Optional[float] = None,
        check: bool = True,
        text: bool = True,
        env: Optional[Dict[str, str]] = None,
    ) -> subprocess.CompletedProcess:
        """
        Run a command and return the result.

        Args:
            cmd: Command and arguments as a list
            cwd: Working directory to run command in
            capture_output: Whether to capture stdout/stderr
            timeout: Timeout in seconds (None for no timeout)
            check: Whether to raise exception on non-zero exit code
            text: Whether to decode output as text
            env: Environment variables (None to inherit from parent)

        Returns:
            CompletedProcess object with result

        Raises:
            subprocess.CalledProcessError: If check=True and command fails
            subprocess.TimeoutExpired: If timeout is exceeded
            FileNotFoundError: If command is not found
        """
        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=capture_output,
                timeout=timeout,
                check=check,
                text=text,
                env=env,
            )

            elapsed = time.time() - start_time

            return result

        except subprocess.CalledProcessError as e:
            elapsed = time.time() - start_time
            logger.error(f"Command failed after {elapsed:.3f}s: {' '.join(cmd)} (exit code {e.returncode})")
            raise
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out after {timeout}s: {' '.join(cmd)}")
            raise
        except FileNotFoundError:
            logger.error(f"Command not found: {cmd[0]}")
            raise

    @staticmethod
    def run_streaming(
        cmd: List[str],
        cwd: Optional[Union[str, Path]] = None,
        timeout: Optional[float] = None,
        text: bool = True,
        env: Optional[Dict[str, str]] = None,
    ) -> subprocess.Popen:
        """
        Run a command with streaming output support.

        Use this for commands that produce large amounts of output that you
        want to process line by line without loading everything into memory.

        Args:
            cmd: Command and arguments as a list
            cwd: Working directory to run command in
            timeout: Timeout in seconds (None for no timeout)
            text: Whether to decode output as text
            env: Environment variables (None to inherit from parent)

        Returns:
            Popen object for streaming access

        Example:
            >>> with CommandRunner.run_streaming(['fd', '.', '/usr']) as proc:
            ...     for line in proc.stdout:
            ...         print(line.strip())
        """
        logger.debug(f"Starting streaming command: {' '.join(cmd)}")

        try:
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=text,
                env=env,
            )

            return process

        except FileNotFoundError:
            logger.error(f"Command not found: {cmd[0]}")
            raise

    @staticmethod
    def get_command_version(command: str) -> Optional[str]:
        """
        Get the version of a command if available.

        Args:
            command: Command name

        Returns:
            Version string if available, None otherwise
        """
        if not CommandRunner.check_command_available(command):
            return None

        # Try common version flags
        version_flags = ["--version", "-V", "-v", "version"]

        for flag in version_flags:
            try:
                result = CommandRunner.run_command(
                    [command, flag],
                    capture_output=True,
                    timeout=5.0,
                    check=False,
                )

                if result.returncode == 0 and result.stdout.strip():
                    # Extract version from first line
                    first_line = result.stdout.strip().split("\n")[0]
                    return first_line

            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                continue

        return None
