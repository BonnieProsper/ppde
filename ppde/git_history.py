"""
Git history extraction and filtering.

Handles:
- Repository parsing using subprocess (no GitPython dependency)
- Author filtering
- Temporal windowing (6 months or 250 commits)
- Diff extraction

All operations are deterministic and reproducible.
"""

import re
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from .data_structures import Commit, FileDiff


class GitHistoryParser:
    """Extracts and filters commit history from a Git repository."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()

        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise ValueError(f"Not a Git repository: {repo_path}")

    def _run_git(self, args: List[str], check: bool = True) -> Tuple[int, str, str]:
        result = subprocess.run(
            ["git"] + args,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if check and result.returncode != 0:
            raise RuntimeError(
                f"Git command failed: {' '.join(args)}\n{result.stderr}"
            )
        return result.returncode, result.stdout, result.stderr

    def _get_config_value(self, section: str, key: str) -> Optional[str]:
        code, stdout, _ = self._run_git(
            ["config", "--get", f"{section}.{key}"], check=False
        )
        return stdout.strip() if code == 0 else None

    def get_commits(
        self,
        author_email: Optional[str] = None,
        max_age_days: int = 180,
        max_count: int = 250,
        reference_time: Optional[datetime] = None,
    ) -> List[Commit]:
        """
        Extract commits with temporal filtering.

        Returns commits newest-first.
        """

        # Normalize reference time
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)
        elif reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=timezone.utc)

        if author_email is None:
            author_email = self._get_config_value("user", "email")
            if not author_email:
                author_email = self._get_most_frequent_author()

        _, stdout, _ = self._run_git(
            [
                "log",
                "--no-merges",
                "--format=%H|%ae|%at|%s",
                f"--author={author_email}",
                f"--max-count={max_count * 2}",  # fetch extra, filter later
                "HEAD",
            ]
        )

        commits: List[Commit] = []

        for line in stdout.splitlines():
            if not line:
                continue

            parts = line.split("|", 3)
            if len(parts) != 4:
                continue

            sha, email, ts, subject = parts

            commit_time = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            delta = reference_time - commit_time

            # Commit must not be in the future
            if delta.total_seconds() < 0:
                continue

            # Enforce strict temporal window
            if delta > timedelta(days=max_age_days):
                break  # log is ordered newest → oldest

            commit = self._parse_commit(sha, email, commit_time, subject)

            if commit.python_files_changed:
                commits.append(commit)

            if len(commits) >= max_count:
                break

        return commits

    def _parse_commit(
        self,
        sha: str,
        author_email: str,
        timestamp: datetime,
        subject: str,
    ) -> Commit:
        _, message, _ = self._run_git(["log", "-1", "--format=%B", sha])
        _, diff_output, _ = self._run_git(["show", "--format=", sha])

        file_diffs: List[FileDiff] = []
        current_file: Optional[str] = None
        current_lines: List[str] = []

        for line in diff_output.splitlines():
            if line.startswith("diff --git"):
                if current_file and current_file.endswith(".py"):
                    file_diffs.append(self._build_diff(current_file, current_lines))

                match = re.search(r" b/(.+)$", line)
                current_file = match.group(1) if match else None
                current_lines = [line]
            else:
                if current_file:
                    current_lines.append(line)

        if current_file and current_file.endswith(".py"):
            file_diffs.append(self._build_diff(current_file, current_lines))

        return Commit(
            sha=sha,
            author_email=author_email,
            timestamp=timestamp,
            message=message.strip(),
            file_diffs=file_diffs,
        )

    @staticmethod
    def _build_diff(path: str, lines: List[str]) -> FileDiff:
        additions = sum(
            1 for line in lines if line.startswith("+") and not line.startswith("+++")
        )
        deletions = sum(
            1 for line in lines if line.startswith("-") and not line.startswith("---")
        )
        return FileDiff(
            file_path=path,
            additions=additions,
            deletions=deletions,
            diff_text="\n".join(lines),
        )

    def _get_most_frequent_author(self) -> str:
        _, stdout, _ = self._run_git(
            ["log", "--format=%ae", "--max-count=100", "HEAD"]
        )
        authors = Counter(stdout.splitlines())
        if not authors:
            raise ValueError("Repository has no commits")
        return authors.most_common(1)[0][0]


def get_commit_history(
    repo_path: str,
    author_email: Optional[str] = None,
    max_age_days: int = 180,
    max_count: int = 250,
) -> List[Commit]:
    parser = GitHistoryParser(repo_path)
    return parser.get_commits(
        author_email=author_email,
        max_age_days=max_age_days,
        max_count=max_count,
    )
