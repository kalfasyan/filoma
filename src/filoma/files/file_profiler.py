import datetime
import grp
import os
import pwd
import stat

from rich.console import Console
from rich.table import Table


class FileProfiler:
    """
    Profiles a file for system metadata: size, permissions, owner, group, timestamps, etc.
    Uses lstat to correctly identify symlinks, and also checks the target type if symlink.
    Also reports current user's access rights.
    """
    def analyze(self, path: str) -> dict:
        st = os.lstat(path)
        is_symlink = stat.S_ISLNK(st.st_mode)
        is_file = stat.S_ISREG(st.st_mode)
        is_dir = stat.S_ISDIR(st.st_mode)
        target_is_file = None
        target_is_dir = None
        if is_symlink:
            try:
                st_target = os.stat(path)
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
            "path": path,
            "size": st.st_size,
            "mode": oct(st.st_mode),
            "owner": pwd.getpwuid(st.st_uid).pw_name if hasattr(pwd, 'getpwuid') else st.st_uid,
            "group": grp.getgrgid(st.st_gid).gr_name if hasattr(grp, 'getgrgid') else st.st_gid,
            "created": datetime.datetime.fromtimestamp(st.st_ctime).isoformat(),
            "modified": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(),
            "accessed": datetime.datetime.fromtimestamp(st.st_atime).isoformat(),
            "is_symlink": is_symlink,
            "rights": rights,
        }
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
        fields = [
            "size", "mode", "owner", "group", "created", "modified", "accessed",
            "is_symlink"
        ]
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
