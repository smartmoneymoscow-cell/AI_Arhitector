"""
shared/blender_sandbox.py — S4: Sandbox for bpy-Scripts.

Before executing any Blender script, check it with AST analysis.
Blocks dangerous imports and function calls.

Fix: S4 — Blender executes arbitrary Python from LLM → sandbox.
"""

import ast
import logging
import re

logger = logging.getLogger("archai.blender_sandbox")


# ═══════════════════════════════════════════════════════════════
# BLOCKED PATTERNS
# ═══════════════════════════════════════════════════════════════

BLOCKED_IMPORTS = {
    "os", "sys", "subprocess", "shutil", "pathlib",
    "socket", "http", "urllib", "requests", "httpx",
    "ctypes", "signal", "multiprocessing", "threading",
    "importlib", "code", "codeop", "compile",
    "eval", "exec", "__import__",
}

BLOCKED_FUNCTIONS = {
    "os.system", "os.popen", "os.exec", "os.spawn",
    "os.remove", "os.unlink", "os.rmdir", "os.makedirs",
    "subprocess.run", "subprocess.Popen", "subprocess.call",
    "subprocess.check_output", "subprocess.check_call",
    "exec(", "eval(", "__import__(", "compile(",
    "open(",  # blocks file I/O outside Blender
}

BLOCKED_ATTRIBUTES = {
    "__subclasses__", "__bases__", "__globals__", "__builtins__",
    "__import__", "__loader__", "__spec__",
}

BLOCKED_PATTERNS = [
    r'import\s+os',
    r'import\s+sys',
    r'import\s+subprocess',
    r'from\s+os\s+import',
    r'from\s+sys\s+import',
    r'from\s+subprocess\s+import',
    r'os\.system\s*\(',
    r'os\.popen\s*\(',
    r'subprocess\.\w+\s*\(',
    r'__import__\s*\(',
    r'exec\s*\(',
    r'eval\s*\(',
    r'compile\s*\(',
    r'open\s*\(',  # careful — blocks legitimate file writes
]


# ═══════════════════════════════════════════════════════════════
# AST ANALYSIS
# ═══════════════════════════════════════════════════════════════

class ScriptSecurityError(Exception):
    """Raised when a script fails security checks."""
    pass


def _check_ast(script: str) -> list[str]:
    """Analyze script AST for dangerous patterns."""
    issues = []
    
    try:
        tree = ast.parse(script)
    except SyntaxError as e:
        return [f"Syntax error: {e}"]
    
    for node in ast.walk(tree):
        # Check imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split(".")[0]
                if module in BLOCKED_IMPORTS:
                    issues.append(f"BLOCKED import: {alias.name} (line {node.lineno})")
        
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module = node.module.split(".")[0]
                if module in BLOCKED_IMPORTS:
                    issues.append(f"BLOCKED from-import: {node.module} (line {node.lineno})")
        
        # Check function calls
        elif isinstance(node, ast.Call):
            func_name = _get_call_name(node)
            if func_name:
                for blocked in BLOCKED_FUNCTIONS:
                    if blocked in func_name:
                        issues.append(f"BLOCKED call: {func_name} (line {node.lineno})")
        
        # Check attribute access
        elif isinstance(node, ast.Attribute):
            if node.attr in BLOCKED_ATTRIBUTES:
                issues.append(f"BLOCKED attribute: {node.attr} (line {node.lineno})")
    
    return issues


def _get_call_name(node: ast.Call) -> str | None:
    """Extract function call name from AST node."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    elif isinstance(node.func, ast.Attribute):
        parts = []
        current = node.func
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def _check_regex(script: str) -> list[str]:
    """Regex-based check as backup for AST analysis."""
    issues = []
    for pattern in BLOCKED_PATTERNS:
        matches = re.findall(pattern, script)
        if matches:
            issues.append(f"REGEX match: {pattern} ({len(matches)} occurrences)")
    return issues


# ═══════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════

def validate_blender_script(script: str, allow_file_write: bool = False) -> str:
    """
    Validate a bpy-script for security before execution.
    
    S4 fix: Prevents LLM-generated scripts from:
    - Importing os/sys/subprocess
    - Calling os.system(), subprocess.run(), etc.
    - Accessing __globals__, __builtins__, etc.
    - Using exec()/eval() for code injection
    
    Args:
        script: Python script to validate
        allow_file_write: If True, allows open() for output files
        
    Returns:
        Cleaned script if valid
        
    Raises:
        ScriptSecurityError if script contains dangerous patterns
    """
    # AST analysis
    ast_issues = _check_ast(script)
    
    # Regex backup
    regex_issues = _check_regex(script)
    
    # Filter open() if allowed
    if allow_file_write:
        ast_issues = [i for i in ast_issues if "open(" not in i]
        regex_issues = [i for i in regex_issues if "open(" not in i]
    
    all_issues = ast_issues + regex_issues
    
    if all_issues:
        issue_text = "\n".join(all_issues[:10])  # limit output
        logger.error("Script SECURITY VIOLATION:\n%s", issue_text)
        raise ScriptSecurityError(
            f"Script failed security check ({len(all_issues)} issues):\n{issue_text}"
        )
    
    # Additional cleanup: remove any remaining dangerous patterns
    cleaned = script
    # Remove any sneaky __import__ calls
    cleaned = re.sub(r'__import__\s*\([^)]*\)', 'pass  # BLOCKED', cleaned)
    
    return cleaned


def is_safe_script(script: str) -> bool:
    """Check if script is safe without raising exception."""
    try:
        validate_blender_script(script)
        return True
    except ScriptSecurityError:
        return False
