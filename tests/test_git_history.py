import shutil
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import git

from ppde.data_structures import Commit
from ppde.evaluation import find_subsequent_fix
from ppde.git_history import GitHistoryParser, get_commit_history


def _cleanup(path):
    try:
        shutil.rmtree(path)
    except PermissionError:
        time.sleep(0.1)
        shutil.rmtree(path, ignore_errors=True)


class TestGitHistoryParser:
    @staticmethod
    def create_test_repo():
        temp_dir = tempfile.mkdtemp()
        repo = git.Repo.init(temp_dir)

        with repo.config_writer() as config:
            config.set_value("user", "name", "Test User")
            config.set_value("user", "email", "test@example.com")

        return temp_dir, repo

    @staticmethod
    def add_commit(repo, filename, content, message, author_email="test@example.com"):
        path = Path(repo.working_dir) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

        repo.index.add([filename])
        repo.index.commit(
            message, author=git.Actor("Test User", author_email)
        )

    def test_basic_commit_extraction(self):
        temp_dir, repo = self.create_test_repo()
        try:
            self.add_commit(repo, "test.py", "print('hi')", "Initial")
            self.add_commit(repo, "test.py", "print('hello')", "Update")

            parser = GitHistoryParser(temp_dir)
            commits = parser.get_commits(author_email="test@example.com")

            assert len(commits) == 2
            assert commits[0].message == "Update"
            assert commits[1].message == "Initial"
        finally:
            _cleanup(temp_dir)

    def test_temporal_filtering(self):
        temp_dir, repo = self.create_test_repo()
        try:
            self.add_commit(repo, "test.py", "x", "Commit")

            parser = GitHistoryParser(temp_dir)
            ref = datetime.now(timezone.utc)

            commits = parser.get_commits(
                author_email="test@example.com",
                max_age_days=1,
                reference_time=ref,
            )
            assert len(commits) == 1

            commits = parser.get_commits(
                author_email="test@example.com",
                max_age_days=0,
                reference_time=ref - timedelta(days=1),
            )
            assert len(commits) == 0
        finally:
            _cleanup(temp_dir)

    def test_subsequent_fix_detection(self):
        temp_dir, repo = self.create_test_repo()
        try:
            self.add_commit(repo, "api.py", "requests.get(url)", "Add API")
            self.add_commit(
                repo,
                "api.py",
                "requests.get(url, timeout=30)",
                "Fix: add timeout",
            )

            parser = GitHistoryParser(temp_dir)
            commits = parser.get_commits(author_email="test@example.com")

            original = commits[1]
            fix = find_subsequent_fix(original, commits, max_days=7)

            assert fix is not None
            assert "fix" in fix.message.lower()
        finally:
            _cleanup(temp_dir)

    def test_convenience_function(self):
        temp_dir, repo = self.create_test_repo()
        try:
            self.add_commit(repo, "test.py", "code", "Test commit")
            commits = get_commit_history(temp_dir, author_email="test@example.com")
            assert len(commits) == 1
            assert isinstance(commits[0], Commit)
        finally:
            _cleanup(temp_dir)
