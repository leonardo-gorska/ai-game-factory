"""
GORVAX GAME FACTORY — Fixer Agent Unit Tests
Tests for the specialized debugging agent.
"""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    router.route = AsyncMock(return_value="mock response")
    router.set_context = MagicMock()
    router.clear_overrides = MagicMock()
    return router


@pytest.fixture
def mock_database():
    return MagicMock()


@pytest.fixture
def fixer_agent(mock_llm_router, mock_database):
    from backend.agents.fixer_agent import FixerAgent
    agent = FixerAgent(
        llm_router=mock_llm_router,
        database=mock_database,
        system_prompt="You are a test fixer.",
    )
    return agent


# ── Test: FixerAgent Initialization ───────────────────────────

class TestFixerAgentInit:
    """Test that FixerAgent initializes correctly."""

    def test_creates_with_custom_prompt(self, fixer_agent):
        assert fixer_agent.name == "fixer"
        assert fixer_agent.role == "Bug Fixer"

    def test_creates_with_default_prompt_if_file_exists(self, mock_llm_router, mock_database):
        """If no system_prompt is passed and fixer.md exists, it should load from file."""
        from backend.agents.fixer_agent import FixerAgent
        from backend.config import PROMPTS_DIR

        fixer_md = PROMPTS_DIR / "fixer.md"
        assert fixer_md.exists(), "fixer.md prompt file should exist"

        agent = FixerAgent(
            llm_router=mock_llm_router,
            database=mock_database,
        )
        assert agent.name == "fixer"
        assert len(agent.system_prompt) > 100  # Should have loaded prompt content


# ── Test: Prompt Building ─────────────────────────────────────

class TestBuildPrompt:
    """Test that _build_prompt constructs the right context."""

    def test_prompt_includes_build_errors(self, fixer_agent):
        input_data = {
            "build_errors": ["Error: Missing semicolon at line 5"],
            "current_files": {},
        }
        prompt = fixer_agent._build_prompt(1, input_data)
        assert "BUILD ERRORS" in prompt
        assert "Missing semicolon" in prompt

    def test_prompt_includes_console_errors(self, fixer_agent):
        input_data = {
            "console_errors": ["Uncaught TypeError: x is not a function"],
            "current_files": {},
        }
        prompt = fixer_agent._build_prompt(1, input_data)
        assert "RUNTIME ERRORS" in prompt
        assert "TypeError" in prompt

    def test_prompt_includes_current_files(self, fixer_agent):
        input_data = {
            "build_errors": ["Error in test.js"],
            "current_files": {"src/test.js": "const x = 1;\n"},
        }
        prompt = fixer_agent._build_prompt(1, input_data)
        assert "test.js" in prompt
        assert "const x = 1" in prompt

    def test_prompt_does_not_include_gdd(self, fixer_agent):
        """Fixer prompt should NEVER contain GDD or feature context."""
        input_data = {
            "gdd_update": "Add a new combat system",  # Should be ignored
            "build_errors": ["Error in test.js"],
            "current_files": {},
        }
        prompt = fixer_agent._build_prompt(1, input_data)
        assert "combat system" not in prompt.lower()

    def test_prompt_includes_failed_fixes(self, fixer_agent):
        input_data = {
            "build_errors": ["Error in test.js"],
            "current_files": {},
            "failed_fixes": ["Tried adding semicolons", "Tried removing import"],
        }
        prompt = fixer_agent._build_prompt(1, input_data)
        assert "Previous fix attempts" in prompt or "FAILED" in prompt
        assert "semicolons" in prompt

    def test_prompt_truncates_large_files(self, fixer_agent):
        large_content = "x" * 10000
        input_data = {
            "build_errors": ["Error in big.js"],
            "current_files": {"src/big.js": large_content},
        }
        prompt = fixer_agent._build_prompt(1, input_data)
        assert "..." in prompt  # Content should be truncated


# ── Test: Response Parsing ────────────────────────────────────

class TestParseCodeResponse:
    """Test that _parse_code_response handles various LLM outputs."""

    def test_parses_valid_json(self, fixer_agent):
        response = json.dumps({
            "summary": "Fixed semicolon",
            "files": [{"path": "src/test.js", "action": "modify", "content": "const x = 1;"}],
            "fix_description": "Added missing semicolon",
        })
        result = fixer_agent._parse_code_response(response)
        assert result["summary"] == "Fixed semicolon"
        assert len(result["files"]) == 1

    def test_handles_invalid_json(self, fixer_agent):
        result = fixer_agent._parse_code_response("not json at all")
        assert "files" in result
        assert isinstance(result["files"], list)


# ── Test: Bracket Validation ──────────────────────────────────

class TestValidateJsBrackets:
    """Test the bracket validation and repair logic."""

    def test_balanced_code_unchanged(self):
        from backend.agents.fixer_agent import FixerAgent
        code = "function foo() {\n  return 1;\n}\n"
        result = FixerAgent._validate_js_brackets(code, "test.js")
        assert result == code

    def test_repairs_missing_braces(self):
        from backend.agents.fixer_agent import FixerAgent
        code = "function foo() {\n  return 1;\n"
        result = FixerAgent._validate_js_brackets(code, "test.js")
        assert result.count('{') == result.count('}')

    def test_repairs_missing_parens(self):
        from backend.agents.fixer_agent import FixerAgent
        code = "console.log('hello'\n"
        result = FixerAgent._validate_js_brackets(code, "test.js")
        assert result.count('(') == result.count(')')


# ── Test: Pipeline Integration ────────────────────────────────

class TestPipelineHasFixerAgent:
    """Test that the Pipeline has a fixer attribute and metrics."""

    def test_pipeline_has_fixer_attribute(self):
        """Pipeline.__init__ should create self.fixer."""
        with patch("backend.orchestrator.pipeline.LLMRouter"):
            with patch("backend.orchestrator.pipeline.Database"):
                with patch("backend.orchestrator.pipeline.GameBuilder"):
                    from backend.orchestrator.pipeline import Pipeline
                    # Check class has fixer in __init__ source code
                    import inspect
                    source = inspect.getsource(Pipeline.__init__)
                    assert "self.fixer" in source, "Pipeline.__init__ should instantiate self.fixer"

    def test_pipeline_has_fixer_metrics(self):
        """Pipeline metrics should include fixer_fixes and fixer_runtime_fixes."""
        from backend.orchestrator.pipeline import Pipeline
        import inspect
        source = inspect.getsource(Pipeline.__init__)
        assert "fixer_fixes" in source
        assert "fixer_runtime_fixes" in source

    def test_build_retries_use_fixer(self):
        """_build_with_retries should call self.fixer instead of self.developer."""
        from backend.orchestrator.pipeline import Pipeline
        import inspect
        source = inspect.getsource(Pipeline._build_with_retries)
        assert "self.fixer.run" in source, "_build_with_retries should call self.fixer.run"
        assert "self.developer.run" not in source, "_build_with_retries should NOT call self.developer.run"


# ── Test: Fixer Agent Write Files (No Blocked Game Files) ─────

class TestFixerWriteFiles:
    """Test that Fixer can write to files that Developer cannot."""

    @pytest.mark.asyncio
    async def test_fixer_can_write_main_js(self, fixer_agent, tmp_path):
        """Fixer should be able to write main.js (blocked for Developer)."""
        from unittest.mock import patch as mp
        code_changes = {
            "files": [
                {"path": "src/main.js", "action": "modify", "content": "// fixed main.js\n"},
            ],
        }
        with mp("backend.agents.fixer_agent.GAME_DIR", tmp_path):
            (tmp_path / "src").mkdir(parents=True, exist_ok=True)
            files_written = await fixer_agent._write_files(code_changes)
            assert any("main.js" in f for f in files_written)

    @pytest.mark.asyncio
    async def test_fixer_can_write_bootscene(self, fixer_agent, tmp_path):
        """Fixer should be able to write BootScene.js (blocked for Developer)."""
        from unittest.mock import patch as mp
        code_changes = {
            "files": [
                {"path": "src/BootScene.js", "action": "modify", "content": "// fixed BootScene\n"},
            ],
        }
        with mp("backend.agents.fixer_agent.GAME_DIR", tmp_path):
            (tmp_path / "src").mkdir(parents=True, exist_ok=True)
            files_written = await fixer_agent._write_files(code_changes)
            assert any("BootScene.js" in f for f in files_written)

    @pytest.mark.asyncio
    async def test_fixer_blocks_config_files(self, fixer_agent, tmp_path):
        """Fixer should still block build config files like package.json."""
        from unittest.mock import patch as mp
        code_changes = {
            "files": [
                {"path": "package.json", "action": "modify", "content": "{}"},
            ],
        }
        with mp("backend.agents.fixer_agent.GAME_DIR", tmp_path):
            (tmp_path / "src").mkdir(parents=True, exist_ok=True)
            files_written = await fixer_agent._write_files(code_changes)
            assert len(files_written) == 0


# ── Test: FixerAgent Export ───────────────────────────────────

class TestFixerExport:
    """Test that FixerAgent is properly exported from backend.agents."""

    def test_fixer_in_all(self):
        from backend.agents import __all__
        assert "FixerAgent" in __all__

    def test_can_import_fixer(self):
        from backend.agents import FixerAgent
        assert FixerAgent is not None
