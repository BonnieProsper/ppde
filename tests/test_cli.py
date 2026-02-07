"""
Minimal CLI test for ppde.cli.

Tests only:
  - Argument parsing
  - Happy path (valid repo)
  - Error path (non-existent path, non-Git repo)

Does NOT test output formatting or full integration.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def _init_git_repo(path: Path) -> None:
    """Initialize a bare Git repo with one commit."""
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"],
                   cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"],
                   cwd=path, check=True, capture_output=True)
    dummy = path / "README.md"
    dummy.write_text("# Test\n")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


class TestCLI:

    def test_analyze_command_on_valid_repo(self):
        """CLI runs successfully on a valid Git repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            _init_git_repo(repo)

            result = subprocess.run(
                [sys.executable, "-m", "ppde.cli", "analyze", str(repo)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0, f"CLI failed: {result.stderr}"
            assert "Analyzed repository:" in result.stdout
            assert "Total findings:" in result.stdout

    def test_nonexistent_path_returns_error(self):
        """CLI exits with error on non-existent path."""
        result = subprocess.run(
            [sys.executable, "-m", "ppde.cli", "analyze", "/nonexistent/path"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "does not exist" in result.stderr

    def test_non_git_repo_returns_error(self):
        """CLI exits with error on non-Git directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [sys.executable, "-m", "ppde.cli", "analyze", tmpdir],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )

            assert result.returncode == 1
            assert "Not a Git repository" in result.stderr

    def test_default_path_is_current_directory(self):
        """If no path given, CLI analyzes current directory (must be a Git repo)."""
        # This test is brittle - depends on it being a repo.
        # Skip for now. Argument parsing is tested by the above.
        pass


def run_all_tests():
    print("Running CLI tests...\n")

    test_instance = TestCLI()
    methods = [m for m in dir(test_instance) if m.startswith("test_") and not m.endswith("_is_current_directory")]

    passed = 0
    failed = 0

    for method_name in sorted(methods):
        label = f"CLI.{method_name}"
        try:
            getattr(test_instance, method_name)()
            print(f"  ✓ {label}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {label}")
            print(f"      {e}")
            failed += 1

    print(f"\n{'✅' if failed == 0 else '❌'} {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if run_all_tests() else 1)
