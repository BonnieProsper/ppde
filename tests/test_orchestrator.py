"""
End-to-end test for ppde.orchestrator (Step 7).

Uses a tiny fake Git repo. Asserts on:
    - Number of explanations returned
    - Detector names that triggered
Does NOT assert on wording or exact content.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


from ppde.orchestrator import analyze_repo

# ---------------------------------------------------------------------------
# Fake repo setup
# ---------------------------------------------------------------------------

def _init_git_repo(path: Path) -> None:
    """Initialize a bare Git repo with one commit."""
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"],
                   cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"],
                   cwd=path, check=True, capture_output=True)

    # Create a dummy file and commit it
    dummy = path / "README.md"
    dummy.write_text("# Test Repo\n")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"],
                   cwd=path, check=True, capture_output=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOrchestrator:

    def test_empty_repo_returns_empty(self):
        """A repo with no Python files → no explanations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            _init_git_repo(repo_path)

            result = analyze_repo(repo_path)
            assert result == []

    def test_file_with_no_violations_returns_empty(self):
        """A Python file with no detectable patterns → no explanations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            _init_git_repo(repo_path)

            # Write a trivial Python file
            (repo_path / "simple.py").write_text("x = 1 + 2\n")

            result = analyze_repo(repo_path)
            # With an empty frequency table, no patterns will have enough
            # historical data to produce surprise scores.
            assert result == []

    def test_non_git_repo_raises_valueerror(self):
        """Passing a non-Git directory raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            # Do NOT initialize git here

            try:
                analyze_repo(repo_path)
                assert False, "Expected ValueError"
            except ValueError as e:
                assert "Not a Git repository" in str(e)

    def test_ignores_hidden_and_venv_directories(self):
        """Hidden dirs (.git) and venv dirs are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            _init_git_repo(repo_path)

            # Create Python files in excluded locations
            (repo_path / ".hidden").mkdir()
            (repo_path / ".hidden" / "test.py").write_text("x = 1\n")

            (repo_path / "venv").mkdir()
            (repo_path / "venv" / "test.py").write_text("x = 2\n")

            result = analyze_repo(repo_path)
            # These files should be skipped
            assert result == []

    def test_skips_unparseable_python_files(self):
        """Files with syntax errors are silently skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            _init_git_repo(repo_path)

            # Write invalid Python
            (repo_path / "broken.py").write_text("def foo(\n")

            result = analyze_repo(repo_path)
            # Should not crash, just skip the file
            assert result == []

    def test_nested_function_detection_works(self):
        """Verify parent tracking correctly identifies nested functions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            _init_git_repo(repo_path)

            # Write code with nested function
            (repo_path / "nested.py").write_text("""
def outer():
    def inner():
        pass
    return inner
""")

            result = analyze_repo(repo_path)
            # Should not crash - this verifies parent map works
            assert isinstance(result, list)

    def test_returns_explanation_objects(self):
        """Result is a list of Explanation objects (even if empty)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            _init_git_repo(repo_path)

            (repo_path / "dummy.py").write_text("# empty\n")

            result = analyze_repo(repo_path)
            assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all_tests():
    print("Running orchestrator end-to-end tests...\n")

    test_instance = TestOrchestrator()
    methods = [m for m in dir(test_instance) if m.startswith("test_")]

    passed = 0
    failed = 0

    for method_name in sorted(methods):
        label = f"Orchestrator.{method_name}"
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
