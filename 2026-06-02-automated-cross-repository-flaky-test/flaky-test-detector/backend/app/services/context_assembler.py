"""
Context Assembler — FlakyGuard-inspired scoped context extraction.

Instead of dumping entire files into the LLM, we extract precisely scoped context:
- For TIMING: the test function body + any explicit wait/sleep calls + async setup
- For CONCURRENCY: thread/async entry points + shared state references
- For ENVIRONMENT: setup/teardown + env var access + external service calls
- For STATE_LEAKAGE: fixture definitions + shared variables + database/mock setup

Uses tree-sitter for AST parsing when available, falls back to regex-based extraction.
"""
import re
import ast
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger()


@dataclass
class CodeContext:
    test_function: str = ""
    setup_code: str = ""
    teardown_code: str = ""
    fixtures: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    shared_state: List[str] = field(default_factory=list)
    call_graph: List[str] = field(default_factory=list)
    relevant_snippets: List[Dict] = field(default_factory=list)
    file_path: str = ""
    language: str = "python"


def detect_language(file_path: str) -> str:
    ext_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".java": "java",
        ".go": "go",
        ".rb": "ruby",
    }
    for ext, lang in ext_map.items():
        if file_path.endswith(ext):
            return lang
    return "python"


def extract_python_function(source: str, func_name: str) -> Optional[str]:
    """Extract a specific function from Python source using AST."""
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == func_name or func_name in node.name:
                    # Get source lines
                    lines = source.splitlines()
                    start = node.lineno - 1
                    end = node.end_lineno
                    return "\n".join(lines[start:end])
    except SyntaxError:
        pass
    return None


def extract_imports(source: str) -> List[str]:
    """Extract import statements from Python source."""
    imports = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            imports.append(stripped)
    return imports[:20]  # Limit to prevent context bloat


def extract_fixtures(source: str) -> List[str]:
    """Extract pytest fixture definitions."""
    fixtures = []
    lines = source.splitlines()
    in_fixture = False
    current_fixture = []
    
    for i, line in enumerate(lines):
        if "@pytest.fixture" in line or "@fixture" in line:
            in_fixture = True
            current_fixture = [line]
        elif in_fixture:
            current_fixture.append(line)
            # End of fixture: blank line or new def at column 0
            if line == "" and i + 1 < len(lines) and not lines[i + 1].startswith(" "):
                fixtures.append("\n".join(current_fixture))
                in_fixture = False
                current_fixture = []
    
    if current_fixture:
        fixtures.append("\n".join(current_fixture))
    
    return fixtures[:5]  # Limit fixtures


def find_shared_state(source: str) -> List[str]:
    """Find module-level mutable state that could leak between tests."""
    shared = []
    for line in source.splitlines():
        stripped = line.strip()
        # Module-level variables (not inside functions/classes)
        if (
            re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*\s*=', stripped)
            and not stripped.startswith("#")
            and not stripped.startswith("def ")
            and not stripped.startswith("class ")
        ):
            shared.append(stripped)
    return shared[:10]


def find_timing_patterns(source: str) -> List[str]:
    """Find timing-related code patterns."""
    patterns = []
    timing_re = re.compile(
        r"(sleep|wait|timeout|asyncio\.sleep|time\.sleep|"
        r"WebDriverWait|implicitly_wait|explicit_wait|"
        r"polling|retry|backoff)",
        re.IGNORECASE
    )
    for i, line in enumerate(source.splitlines()):
        if timing_re.search(line):
            patterns.append(f"line {i+1}: {line.rstrip()}")
    return patterns[:10]


def find_concurrency_patterns(source: str) -> List[str]:
    """Find concurrency-related code patterns."""
    patterns = []
    concurrency_re = re.compile(
        r"(thread|Thread|async|await|asyncio|concurrent|"
        r"multiprocessing|mutex|lock|semaphore|queue\.Queue|"
        r"threading\.Event|Future|executor)",
        re.IGNORECASE
    )
    for i, line in enumerate(source.splitlines()):
        if concurrency_re.search(line):
            patterns.append(f"line {i+1}: {line.rstrip()}")
    return patterns[:10]


def find_environment_patterns(source: str) -> List[str]:
    """Find environment-dependent code patterns."""
    patterns = []
    env_re = re.compile(
        r"(os\.environ|getenv|subprocess|requests\.|httpx\.|"
        r"socket\.|boto3|connect\(|database\.|redis\.|"
        r"docker|kubectl|popen)",
        re.IGNORECASE
    )
    for i, line in enumerate(source.splitlines()):
        if env_re.search(line):
            patterns.append(f"line {i+1}: {line.rstrip()}")
    return patterns[:10]


def find_state_leakage_patterns(source: str) -> List[str]:
    """Find state that could leak between tests."""
    patterns = []
    state_re = re.compile(
        r"(global\s|setUp|tearDown|beforeEach|afterEach|"
        r"@classmethod|cls\.|self\.\w+\s*=|addCleanup|"
        r"monkeypatch|mock\.patch|MagicMock)",
        re.IGNORECASE
    )
    for i, line in enumerate(source.splitlines()):
        if state_re.search(line):
            patterns.append(f"line {i+1}: {line.rstrip()}")
    return patterns[:10]


def assemble_context(
    source_code: str,
    test_name: str,
    file_path: str,
    root_cause: str,
    log_output: str = "",
    error_message: str = "",
) -> CodeContext:
    """
    Assemble precisely scoped context based on root cause category.
    This is the core FlakyGuard-inspired scoping strategy.
    """
    language = detect_language(file_path)
    ctx = CodeContext(file_path=file_path, language=language)
    
    # Extract test function name from fully qualified path
    # e.g., "tests/test_auth.py::TestAuth::test_user_login" -> "test_user_login"
    func_name = test_name.split("::")[-1] if "::" in test_name else test_name
    
    # Always extract imports (limited)
    ctx.imports = extract_imports(source_code)
    
    # Extract the test function itself
    if language == "python":
        test_func = extract_python_function(source_code, func_name)
        ctx.test_function = test_func or _extract_by_regex(source_code, func_name)
    else:
        ctx.test_function = _extract_by_regex(source_code, func_name)
    
    # Cause-specific context assembly
    if root_cause == "timing":
        ctx.relevant_snippets = [
            {"label": "timing_patterns", "content": find_timing_patterns(source_code)},
        ]
        # Find setup that might have hardcoded timeouts
        ctx.setup_code = _extract_setup_teardown(source_code, "setup")
        
    elif root_cause == "concurrency":
        ctx.relevant_snippets = [
            {"label": "concurrency_patterns", "content": find_concurrency_patterns(source_code)},
        ]
        ctx.shared_state = find_shared_state(source_code)
        
    elif root_cause == "environment":
        ctx.relevant_snippets = [
            {"label": "environment_patterns", "content": find_environment_patterns(source_code)},
        ]
        ctx.setup_code = _extract_setup_teardown(source_code, "setup")
        ctx.teardown_code = _extract_setup_teardown(source_code, "teardown")
        
    elif root_cause == "state_leakage":
        ctx.fixtures = extract_fixtures(source_code)
        ctx.shared_state = find_shared_state(source_code)
        ctx.relevant_snippets = [
            {"label": "state_patterns", "content": find_state_leakage_patterns(source_code)},
        ]
        ctx.setup_code = _extract_setup_teardown(source_code, "setup")
        ctx.teardown_code = _extract_setup_teardown(source_code, "teardown")
    
    else:
        # Unknown: extract everything moderately
        ctx.fixtures = extract_fixtures(source_code)[:2]
        ctx.setup_code = _extract_setup_teardown(source_code, "setup")
    
    return ctx


def _extract_by_regex(source: str, func_name: str) -> str:
    """Fallback: extract function using regex."""
    # Match def func_name( ... up to next def at column 0
    pattern = rf"(def {re.escape(func_name)}\s*\(.*?)(?=\ndef |\Z)"
    match = re.search(pattern, source, re.DOTALL)
    if match:
        return match.group(1)[:2000]  # Limit size
    return ""


def _extract_setup_teardown(source: str, kind: str) -> str:
    """Extract setup or teardown methods."""
    patterns = {
        "setup": ["def setUp", "def setup_method", "def setup", "def before_each"],
        "teardown": ["def tearDown", "def teardown_method", "def teardown", "def after_each"],
    }
    
    for pattern in patterns.get(kind, []):
        match = re.search(rf"{re.escape(pattern)}\s*\(.*?(?=\ndef |\Z)", source, re.DOTALL)
        if match:
            return match.group(0)[:1000]
    return ""


def format_context_for_llm(ctx: CodeContext, root_cause: str, failure_evidence: Dict) -> str:
    """
    Format the assembled context into a structured prompt section.
    Keeps total context under ~3000 tokens to avoid context bloat.
    """
    sections = []
    
    sections.append(f"## Test File: {ctx.file_path}")
    sections.append(f"## Root Cause Category: {root_cause}")
    
    if failure_evidence:
        sections.append("## Failure Evidence")
        sections.append(f"```\n{failure_evidence.get('log', '')[:500]}\n```")
    
    if ctx.imports:
        sections.append("## Key Imports")
        sections.append("\n".join(ctx.imports[:10]))
    
    if ctx.test_function:
        sections.append("## Test Function")
        sections.append(f"```python\n{ctx.test_function[:1500]}\n```")
    
    if ctx.setup_code:
        sections.append("## Setup")
        sections.append(f"```python\n{ctx.setup_code[:500]}\n```")
    
    if ctx.teardown_code:
        sections.append("## Teardown")
        sections.append(f"```python\n{ctx.teardown_code[:500]}\n```")
    
    if ctx.fixtures:
        sections.append("## Fixtures")
        for fix in ctx.fixtures[:3]:
            sections.append(f"```python\n{fix[:300]}\n```")
    
    if ctx.shared_state:
        sections.append("## Shared State")
        sections.append("\n".join(ctx.shared_state[:5]))
    
    for snippet in ctx.relevant_snippets:
        if snippet.get("content"):
            sections.append(f"## {snippet['label']}")
            content = snippet["content"]
            if isinstance(content, list):
                sections.append("\n".join(str(c) for c in content[:10]))
            else:
                sections.append(str(content)[:500])
    
    return "\n\n".join(sections)