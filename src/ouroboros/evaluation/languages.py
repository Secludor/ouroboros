"""Language detection and preset commands for mechanical verification.

Auto-detects project language from marker files and provides appropriate
build/lint/test commands. Supports project-level overrides via
.ouroboros/mechanical.toml.

Usage:
    config = build_mechanical_config(Path("/path/to/project"))
    verifier = MechanicalVerifier(config)
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shlex
from typing import Any

import structlog

from ouroboros.evaluation.mechanical import MechanicalConfig

log = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class LanguagePreset:
    """Command preset for a detected project language.

    Attributes:
        name: Language/toolchain identifier (e.g. "python-uv", "zig", "rust")
        lint_command: Linting command, or None to skip
        build_command: Build/compile command, or None to skip
        test_command: Test runner command, or None to skip
        static_command: Static analysis command, or None to skip
        coverage_command: Coverage command, or None to skip
    """

    name: str
    lint_command: tuple[str, ...] | None = None
    build_command: tuple[str, ...] | None = None
    test_command: tuple[str, ...] | None = None
    static_command: tuple[str, ...] | None = None
    coverage_command: tuple[str, ...] | None = None


LANGUAGE_PRESETS: dict[str, LanguagePreset] = {
    "python-uv": LanguagePreset(
        name="python-uv",
        lint_command=("uv", "run", "ruff", "check", "."),
        build_command=("uv", "run", "python", "-m", "compileall", "-q", "src/"),
        test_command=("uv", "run", "pytest", "--tb=short", "-q"),
        static_command=(
            "uv",
            "run",
            "mypy",
            ".",
            "--ignore-missing-imports",
        ),
        coverage_command=(
            "uv",
            "run",
            "pytest",
            "--cov",
            "--cov-report=term-missing",
            "-q",
        ),
    ),
    "python": LanguagePreset(
        name="python",
        lint_command=("ruff", "check", "."),
        build_command=("python", "-m", "compileall", "-q", "src/"),
        test_command=("pytest", "--tb=short", "-q"),
        static_command=("mypy", ".", "--ignore-missing-imports"),
        coverage_command=(
            "pytest",
            "--cov",
            "--cov-report=term-missing",
            "-q",
        ),
    ),
    "zig": LanguagePreset(
        name="zig",
        build_command=("zig", "build"),
        test_command=("zig", "build", "test"),
    ),
    "rust": LanguagePreset(
        name="rust",
        lint_command=("cargo", "clippy"),
        build_command=("cargo", "build"),
        test_command=("cargo", "test"),
    ),
    "go": LanguagePreset(
        name="go",
        lint_command=("go", "vet", "./..."),
        build_command=("go", "build", "./..."),
        test_command=("go", "test", "./..."),
        coverage_command=("go", "test", "-cover", "./..."),
    ),
    "java-maven": LanguagePreset(
        name="java-maven",
        build_command=("mvn", "clean", "compile"),
        test_command=("mvn", "test"),
    ),
    "node-npm": LanguagePreset(
        name="node-npm",
        lint_command=("npm", "run", "lint"),
        build_command=("npm", "run", "build"),
        test_command=("npm", "test"),
    ),
    "node-pnpm": LanguagePreset(
        name="node-pnpm",
        lint_command=("pnpm", "lint"),
        build_command=("pnpm", "build"),
        test_command=("pnpm", "test"),
    ),
    "node-bun": LanguagePreset(
        name="node-bun",
        lint_command=("bun", "lint"),
        build_command=("bun", "run", "build"),
        test_command=("bun", "test"),
    ),
    "node-yarn": LanguagePreset(
        name="node-yarn",
        lint_command=("yarn", "lint"),
        build_command=("yarn", "build"),
        test_command=("yarn", "test"),
    ),
}

_MAVEN_WRAPPER = "./mvnw"
_MAVEN_WRAPPER_WINDOWS = "mvnw.cmd"

# Ordered list of (marker_file, preset_key) for detection priority.
# More specific markers come first (e.g. uv.lock before pyproject.toml).
_DETECTION_RULES: list[tuple[str, str]] = [
    # Python with uv (most specific Python marker)
    ("uv.lock", "python-uv"),
    # Zig
    ("build.zig", "zig"),
    # Rust
    ("Cargo.toml", "rust"),
    # Go
    ("go.mod", "go"),
    # Java (Maven)
    ("pom.xml", "java-maven"),
    # Node.js package managers (check lockfiles before generic package.json)
    ("bun.lockb", "node-bun"),
    ("bun.lock", "node-bun"),
    ("pnpm-lock.yaml", "node-pnpm"),
    ("yarn.lock", "node-yarn"),
    ("package-lock.json", "node-npm"),
    # Generic Python (after uv, before generic Node)
    ("pyproject.toml", "python"),
    ("setup.py", "python"),
    ("setup.cfg", "python"),
    # Generic Node (no lockfile found)
    ("package.json", "node-npm"),
]


def detect_language(working_dir: Path) -> LanguagePreset | None:
    """Detect project language from marker files in working_dir.

    Checks for known project files in priority order. Returns the first
    matching preset, or None if no language is detected.

    Args:
        working_dir: Project root directory to scan

    Returns:
        LanguagePreset for the detected language, or None
    """
    for marker_file, preset_key in _DETECTION_RULES:
        if (working_dir / marker_file).exists():
            return LANGUAGE_PRESETS[preset_key]
    return None


def _resolve_maven_command(working_dir: Path) -> str:
    """Resolve the safest Maven launcher for the current project/platform.

    Prefers project-local wrapper scripts when they are runnable on the
    current platform. Falls back to plain ``mvn`` when no suitable wrapper is
    available.
    """
    if os.name == "nt":
        wrapper = working_dir / _MAVEN_WRAPPER_WINDOWS
        if wrapper.is_file():
            return _MAVEN_WRAPPER_WINDOWS
        return "mvn"

    wrapper = working_dir / "mvnw"
    if wrapper.is_file() and os.access(wrapper, os.X_OK):
        return _MAVEN_WRAPPER
    return "mvn"


_ESLINT_CONFIG_FILES: tuple[str, ...] = (
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.cjs",
    "eslint.config.ts",
    ".eslintrc.js",
    ".eslintrc.cjs",
    ".eslintrc.json",
    ".eslintrc.yaml",
    ".eslintrc.yml",
    ".eslintrc",
)

_BIOME_CONFIG_FILES: tuple[str, ...] = ("biome.json", "biome.jsonc")

# Tokens in a `scripts.test` value that indicate a specific runner is expected.
# When a token is present but its package is not declared in dependencies,
# the script is considered misconfigured and the test check is skipped.
_TEST_RUNNER_TOKENS: tuple[tuple[str, str], ...] = (
    ("vitest", "vitest"),
    ("jest", "jest"),
    ("mocha", "mocha"),
    ("ava", "ava"),
    ("playwright", "@playwright/test"),
)

_TEST_RUNNER_TOKEN_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(tok) for tok, _ in _TEST_RUNNER_TOKENS) + r")\b",
    re.IGNORECASE,
)


def _read_package_json(working_dir: Path) -> dict[str, Any] | None:
    """Read and parse ``package.json`` safely.

    Returns None when the file is absent or invalid; never raises.
    """
    path = working_dir / "package.json"
    if not path.is_file():
        return None
    try:
        with open(path, "rb") as handle:
            data = json.loads(handle.read())
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("node_preset.package_json_parse_error", path=str(path), error=str(exc))
        return None
    if not isinstance(data, dict):
        return None
    return data


def _has_eslint_config(working_dir: Path, pkg: dict[str, Any]) -> bool:
    if any((working_dir / name).exists() for name in _ESLINT_CONFIG_FILES):
        return True
    return "eslintConfig" in pkg


def _has_biome_config(working_dir: Path) -> bool:
    return any((working_dir / name).exists() for name in _BIOME_CONFIG_FILES)


def _declares_dependency(pkg: dict[str, Any], name: str) -> bool:
    for key in (
        "dependencies",
        "devDependencies",
        "peerDependencies",
        "optionalDependencies",
    ):
        section = pkg.get(key)
        if isinstance(section, dict) and name in section:
            return True
    return False


def _refine_node_lint(
    working_dir: Path,
    pkg: dict[str, Any],
    fallback: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    """Return a safe lint command, or None to skip.

    A lint script is only trusted when:
    - ``scripts.lint`` is defined in package.json, and
    - the referenced tool (eslint/biome) has a config file available.
    """
    scripts = pkg.get("scripts")
    if not isinstance(scripts, dict):
        return None
    lint_script = scripts.get("lint")
    if not isinstance(lint_script, str) or not lint_script.strip():
        return None
    lower = lint_script.lower()
    if "eslint" in lower and not _has_eslint_config(working_dir, pkg):
        log.info("node_preset.lint_skipped", reason="eslint_config_missing")
        return None
    if "biome" in lower and not _has_biome_config(working_dir):
        log.info("node_preset.lint_skipped", reason="biome_config_missing")
        return None
    return fallback


def _refine_node_test(
    pkg: dict[str, Any],
    fallback: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    """Return a safe test command, or None to skip.

    A test script is only trusted when:
    - ``scripts.test`` is defined and is not the npm "no test specified" stub, and
    - any referenced runner (vitest/jest/mocha/…) is declared in dependencies.
    """
    scripts = pkg.get("scripts")
    if not isinstance(scripts, dict):
        return None
    test_script = scripts.get("test")
    if not isinstance(test_script, str) or not test_script.strip():
        return None
    lower = test_script.lower()
    if "no test specified" in lower:
        log.info("node_preset.test_skipped", reason="npm_stub")
        return None
    for match in _TEST_RUNNER_TOKEN_PATTERN.finditer(test_script):
        token = match.group(1).lower()
        for tok, dep_name in _TEST_RUNNER_TOKENS:
            if tok == token and not _declares_dependency(pkg, dep_name):
                log.info(
                    "node_preset.test_skipped",
                    reason="runner_not_declared",
                    runner=token,
                )
                return None
    return fallback


def _refine_node_build(
    working_dir: Path,
    pkg: dict[str, Any],
    fallback: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    """Return a safe build command, or None to skip.

    Keeps ``scripts.build`` when declared. When no build script is available
    but a ``tsconfig.json`` is present, falls back to a type-check-only
    compile via ``npx tsc --noEmit`` so TypeScript projects still get build
    verification.
    """
    scripts = pkg.get("scripts")
    if isinstance(scripts, dict):
        build_script = scripts.get("build")
        if isinstance(build_script, str) and build_script.strip():
            return fallback
    if (working_dir / "tsconfig.json").exists():
        return ("npx", "--no-install", "tsc", "--noEmit")
    return None


def _refine_node_preset(working_dir: Path, preset: LanguagePreset) -> LanguagePreset:
    """Refine a node-* preset against the actual project manifest.

    Returns a new ``LanguagePreset`` where any command the project cannot
    reliably execute is replaced with ``None`` (skipped). Stage 1 is meant
    to be a zero-cost, zero-false-positive sanity gate; it is better to skip
    a check than to run the wrong tool and report a phantom failure.
    """
    pkg = _read_package_json(working_dir)
    if pkg is None:
        return preset
    return LanguagePreset(
        name=preset.name,
        lint_command=_refine_node_lint(working_dir, pkg, preset.lint_command),
        build_command=_refine_node_build(working_dir, pkg, preset.build_command),
        test_command=_refine_node_test(pkg, preset.test_command),
        static_command=preset.static_command,
        coverage_command=preset.coverage_command,
    )


def _load_project_overrides(working_dir: Path) -> dict[str, Any] | None:
    """Load .ouroboros/mechanical.toml if it exists.

    Args:
        working_dir: Project root directory

    Returns:
        Parsed TOML dict, or None if file doesn't exist
    """
    config_path = working_dir / ".ouroboros" / "mechanical.toml"
    if not config_path.exists():
        return None

    import tomllib

    try:
        with open(config_path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        log.warning("mechanical.toml_parse_error", path=str(config_path), error=str(e))
        return None


# Executables allowed in .ouroboros/mechanical.toml overrides.
# Presets (hardcoded) are trusted and bypass this check.
# This prevents untrusted repos from running arbitrary commands
# when evaluated in CI/CD environments.
_ALLOWED_EXECUTABLES: frozenset[str] = frozenset(
    {
        # Python
        "python",
        "python3",
        "uv",
        "pip",
        "ruff",
        "mypy",
        "pytest",
        "pyright",
        "black",
        "isort",
        "flake8",
        "pylint",
        "bandit",
        # Zig
        "zig",
        # Rust
        "cargo",
        "rustc",
        "clippy-driver",
        # Go
        "go",
        "golangci-lint",
        # Node.js
        "npm",
        "npx",
        "pnpm",
        "yarn",
        "bun",
        "node",
        # General build tools
        "make",
        "cmake",
        "gradle",
        "mvn",
        "ant",
        # Other languages
        "cabal",
        "stack",
        "ghc",
        "dotnet",
        "mix",
        "elixir",
        "swift",
        "swiftc",
        "xcodebuild",
        "javac",
        "java",
        "kotlinc",
        "clang",
        "clang-tidy",
        "gcc",
        "g++",
        "deno",
    }
)


def _parse_command(value: str, *, trusted: bool = False) -> tuple[str, ...] | None:
    """Parse a command string into a tuple, or None if empty.

    Args:
        value: Shell command string (e.g. "cargo test --workspace")
               Empty string means "skip this check"
        trusted: If True, skip executable validation (for hardcoded presets)

    Returns:
        Tuple of command parts, or None to skip

    Raises:
        ValueError: If the executable is not in the allowlist and trusted=False
    """
    value = value.strip()
    if not value:
        return None
    parts = tuple(shlex.split(value, posix=(os.name != "nt")))
    if not trusted and parts:
        executable = Path(parts[0]).name
        if executable not in _ALLOWED_EXECUTABLES:
            log.warning(
                "mechanical.blocked_executable",
                executable=executable,
                command=value,
                hint="Add to _ALLOWED_EXECUTABLES or use a preset language",
            )
            return None
    return parts


def _apply_overrides(
    current: dict[str, Any],
    source: dict[str, Any],
) -> None:
    """Apply command overrides from a source dict onto current config values.

    Mutates current in place. Handles command keys (parsed via shlex),
    timeout (int), and coverage_threshold (float).

    Args:
        current: Mutable dict of current config values
        source: Override source (TOML file or explicit overrides)
    """
    for key in ("lint", "build", "test", "static", "coverage"):
        if key in source:
            current[key] = _parse_command(str(source[key]))
    if "timeout" in source:
        current["timeout"] = int(source["timeout"])
    if "coverage_threshold" in source:
        current["coverage_threshold"] = float(source["coverage_threshold"])


def build_mechanical_config(
    working_dir: Path,
    overrides: dict[str, Any] | None = None,
) -> MechanicalConfig:
    """Build a MechanicalConfig by combining auto-detection with overrides.

    Priority (highest to lowest):
    1. Explicit overrides dict (from caller)
    2. .ouroboros/mechanical.toml in project
    3. Auto-detected language preset
    4. All commands None (all checks skip gracefully)

    Args:
        working_dir: Project root directory
        overrides: Optional dict of command overrides

    Returns:
        MechanicalConfig with resolved commands and working_dir set
    """
    # Start with auto-detected preset
    preset = detect_language(working_dir)

    if preset and preset.name.startswith("node-"):
        preset = _refine_node_preset(working_dir, preset)

    build_command = preset.build_command if preset else None
    test_command = preset.test_command if preset else None
    if preset and preset.name == "java-maven":
        maven_command = _resolve_maven_command(working_dir)
        build_command = (maven_command, "clean", "compile")
        test_command = (maven_command, "test")

    # Base command values from preset (or all None)
    current: dict[str, Any] = {
        "lint": preset.lint_command if preset else None,
        "build": build_command,
        "test": test_command,
        "static": preset.static_command if preset else None,
        "coverage": preset.coverage_command if preset else None,
        "timeout": 300,
        "coverage_threshold": 0.7,
    }

    # Layer on .ouroboros/mechanical.toml
    file_overrides = _load_project_overrides(working_dir)
    if file_overrides:
        _apply_overrides(current, file_overrides)

    # Layer on explicit overrides (from caller / MCP params)
    if overrides:
        _apply_overrides(current, overrides)

    return MechanicalConfig(
        lint_command=current["lint"],
        build_command=current["build"],
        test_command=current["test"],
        static_command=current["static"],
        coverage_command=current["coverage"],
        timeout_seconds=current["timeout"],
        coverage_threshold=current["coverage_threshold"],
        working_dir=working_dir,
    )
