import datetime
import grp
import os
import pwd
import stat
from pathlib import Path

from rich.console import Console
from rich.table import Table


class FileProfiler:
    """
    Profiles a file for system metadata: size, permissions, owner, group, timestamps, etc.
    Uses lstat to correctly identify symlinks, and also checks the target type if symlink.
    Also reports current user's access rights.
    """

    def analyze(self, path: str) -> dict:
        # Use pathlib for path handling and return resolved full path
        # compute_hash: optional boolean to compute SHA256 (may be slow for large files)
        compute_hash = False
        if isinstance(path, tuple) or isinstance(path, list):
            # legacy callers might send (path, compute_hash)
            path, compute_hash = path

        path_obj = Path(path)
        full_path = str(path_obj.resolve(strict=False))

        st = path_obj.lstat()
        is_symlink = path_obj.is_symlink()
        # For non-symlinks prefer Path methods which follow symlinks by default
        is_file = path_obj.is_file() if not is_symlink else None
        is_dir = path_obj.is_dir() if not is_symlink else None
        target_is_file = None
        target_is_dir = None
        if is_symlink:
            try:
                st_target = path_obj.stat()
                target_is_file = stat.S_ISREG(st_target.st_mode)
                target_is_dir = stat.S_ISDIR(st_target.st_mode)
            except Exception:
                target_is_file = False
                target_is_dir = False

        # Current user rights
        rights = {
            "read": os.access(path, os.R_OK),
            "write": os.access(path, os.W_OK),
            "execute": os.access(path, os.X_OK),
        }

        report = {
            "path": full_path,
            "size": st.st_size,
            "mode": oct(st.st_mode),
            "owner": pwd.getpwuid(st.st_uid).pw_name if hasattr(pwd, "getpwuid") else st.st_uid,
            "group": grp.getgrgid(st.st_gid).gr_name if hasattr(grp, "getgrgid") else st.st_gid,
            "created": datetime.datetime.fromtimestamp(st.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
            "modified": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "accessed": datetime.datetime.fromtimestamp(st.st_atime).strftime("%Y-%m-%d %H:%M:%S"),
            "is_symlink": is_symlink,
            "rights": rights,
        }
        # Add inode, link count and human-readable mode
        report["inode"] = getattr(st, "st_ino", None)
        report["nlink"] = getattr(st, "st_nlink", None)
        try:
            report["mode_str"] = stat.filemode(st.st_mode)
        except Exception:
            report["mode_str"] = None

        # Optional SHA256 (turn on by passing a tuple like (path, True) or using compute_hash variable)
        if compute_hash:
            report["sha256"] = self._compute_sha256(full_path)
        else:
            report["sha256"] = None

        # Try to collect extended attributes (xattrs) if available
        report["xattrs"] = self._get_xattrs(full_path)
        if is_symlink:
            report["target_is_file"] = target_is_file
            report["target_is_dir"] = target_is_dir
        else:
            report["is_file"] = is_file
            report["is_dir"] = is_dir
        return report

    def print_report(self, report: dict):
        console = Console()
        table = Table(title=f"File Profile: {report['path']}")
        table.add_column("Field", style="bold cyan")
        table.add_column("Value", style="white")
        # Only show target_is_file/target_is_dir if is_symlink, otherwise show is_file/is_dir
        fields = ["size", "mode", "owner", "group", "created", "modified", "accessed", "is_symlink"]
        if report.get("is_symlink"):
            fields += ["target_is_file", "target_is_dir"]
        else:
            fields += ["is_file", "is_dir"]
        for key in fields:
            table.add_row(key, str(report.get(key)))
        rights = report.get("rights", {})
        rights_str = ", ".join(f"{k}: {'✔' if v else '✗'}" for k, v in rights.items())
        table.add_row("rights", rights_str)
        console.print(table)

    def _compute_sha256(self, path: str, chunk_size: int = 1 << 20) -> str | None:
        """Compute SHA256 of a file in streaming fashion. Returns hex digest or None on error."""
        import hashlib

        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(chunk_size), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None

    def _get_xattrs(self, path: str) -> dict | None:
        """Return extended attributes as a dict if available, otherwise None."""
        try:
            # xattr API differs by platform; try to import common modules
            try:
                import xattr as _xattr

                xa = {k.decode(): _xattr.get(path, k).decode(errors="ignore") for k in _xattr.listxattr(path)}
                return xa
            except Exception:
                # fallback to os.listxattr if available
                if hasattr(os, "listxattr"):
                    xa = {}
                    for k in os.listxattr(path):
                        try:
                            v = os.getxattr(path, k)
                            if isinstance(k, bytes):
                                kk = k.decode(errors="ignore")
                            else:
                                kk = k
                            xa[kk] = v.decode(errors="ignore") if isinstance(v, (bytes, bytearray)) else str(v)
                        except Exception:
                            xa[k] = None
                    return xa
        except Exception:
            pass
        return None
