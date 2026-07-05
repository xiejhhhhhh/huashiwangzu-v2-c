"""Module sandbox verification matrix — scan modules/*/sandbox for testability.

Output: per-module status with check=pass/skip, actionable reason for skips.

Usage:
    python3.14 dev_toolkit/module_sandbox_matrix.py [--check]
    --check  runs 'cd <repo> && .venv/bin/python dev_toolkit/module_sandbox_matrix.py --check'
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_PYTHON = REPO_ROOT / "backend" / ".venv" / "bin" / "python"
MODULES_DIR = REPO_ROOT / "modules"

MANDATORY_PARSERS = {"pdf", "docx", "xlsx", "xls", "pptx", "txt", "md", "csv"}
CHUNK_WARNING_PATTERNS = (
    re.compile(r"some chunks are larger", re.IGNORECASE),
    re.compile(r"chunk size limit", re.IGNORECASE),
    re.compile(r"after minification", re.IGNORECASE),
)


def _frontend_install_needed(sandbox_dir: Path) -> bool:
    package_json = sandbox_dir / "package.json"
    if not package_json.exists():
        return False
    vite_bin = sandbox_dir / "node_modules" / ".bin" / "vite"
    if not vite_bin.exists():
        return True
    package_lock = sandbox_dir / "node_modules" / ".package-lock.json"
    if not package_lock.exists():
        return True
    return package_json.stat().st_mtime > package_lock.stat().st_mtime


def _frontend_install_command(sandbox_dir: Path) -> list[str]:
    if (sandbox_dir / "package-lock.json").exists():
        return ["npm", "ci", "--prefer-offline", "--no-audit", "--no-fund"]
    return ["npm", "install", "--package-lock=false", "--no-audit", "--no-fund"]


def _available_module_keys() -> list[str]:
    return sorted(
        p.name for p in MODULES_DIR.iterdir()
        if p.is_dir() and not p.name.startswith("_")
    )


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _readme_acceptance_info(module_dir: Path) -> dict:
    readme = module_dir / "README.md"
    if not readme.exists():
        return {
            "readme_exists": False,
            "readme_acceptance_matrix": False,
            "readme_acceptance_reason": "README.md missing",
        }

    text = _read_text(readme)
    lower = text.lower()
    has_acceptance = any(marker in lower for marker in ("验收", "验证", "acceptance"))
    has_repro_command = any(
        marker in lower
        for marker in (
            "sandbox",
            "test_module.py",
            "npm run build",
            "backend/.venv/bin/python",
            "pytest",
        )
    )
    ok = has_acceptance and has_repro_command
    reason = "" if ok else "README.md lacks reproducible acceptance/sandbox commands"
    return {
        "readme_exists": True,
        "readme_acceptance_matrix": ok,
        "readme_acceptance_reason": reason,
    }


def parse_requested_modules(module_args: list[str] | None, modules_arg: str | None) -> list[str] | None:
    requested: list[str] = []
    for key in module_args or []:
        key = key.strip()
        if key:
            requested.append(key)
    for key in (modules_arg or "").split(","):
        key = key.strip()
        if key:
            requested.append(key)

    deduped: list[str] = []
    seen = set()
    for key in requested:
        if key not in seen:
            deduped.append(key)
            seen.add(key)
    return deduped or None


def _resolve_module_keys(module_keys: list[str] | None = None) -> list[str]:
    available = _available_module_keys()
    if module_keys is None:
        return available

    available_set = set(available)
    unknown = [key for key in module_keys if key not in available_set]
    if unknown:
        raise ValueError(f"unknown module(s): {', '.join(unknown)}")
    return module_keys


def _build_entry(key: str) -> dict:
    module_dir = MODULES_DIR / key
    sandbox_dir = MODULES_DIR / key / "sandbox"
    backend_dir = MODULES_DIR / key / "backend"

    has_sandbox = sandbox_dir.exists()
    test_module = sandbox_dir / "test_module.py"
    has_test_module = test_module.exists()
    has_backend = (backend_dir / "router.py").exists()
    has_samples = (sandbox_dir / "samples").exists()

    # Build vs test commands
    frontend_build = None
    frontend_dev = None
    backend_test_cmd = None
    auto_runnable = False
    reason = ""

    if has_sandbox:
        pkg_json = sandbox_dir / "package.json"
        if pkg_json.exists():
            frontend_build = f"cd modules/{key}/sandbox && npm run build"
            frontend_dev = f"cd modules/{key}/sandbox && npm run dev"
            auto_runnable = True

    if has_test_module:
        backend_test_cmd = (
            f"PYTHONPATH=backend {BACKEND_PYTHON} modules/{key}/sandbox/test_module.py"
        )
        if BACKEND_PYTHON.exists():
            auto_runnable = True
        else:
            reason = "backend .venv python not found" if not frontend_build else ""
    elif not has_sandbox:
        reason = "no sandbox directory"
    elif not has_test_module and has_backend:
        reason = "has backend router but no sandbox/test_module.py"
    elif not has_test_module and has_sandbox:
        if has_samples:
            reason = "has samples but no test_module.py — probably a parser module needing tests"
        else:
            reason = "sandbox exists but no test_module.py and no backend — likely pure frontend"
    elif not has_test_module:
        reason = "missing test_module.py"

    readme_info = _readme_acceptance_info(module_dir)
    return {
        "module": key,
        "has_sandbox": has_sandbox,
        "has_test_module": has_test_module,
        "has_backend": has_backend,
        "has_samples": has_samples,
        "check": "pass" if auto_runnable else "skip",
        "frontend_build_cmd": frontend_build,
        "frontend_dev_cmd": frontend_dev,
        "backend_test_cmd": backend_test_cmd,
        "reason": reason,
        **readme_info,
    }


def scan_sandbox_matrix(module_keys: list[str] | None = None) -> list[dict]:
    modules = _resolve_module_keys(module_keys)
    return [_build_entry(key) for key in modules]


def _prepare_command(command_text: str) -> tuple[list[str], Path, dict[str, str]]:
    env = os.environ.copy()
    env.setdefault("JWT_SECRET", "module-sandbox-matrix-validation-secret")
    cwd = REPO_ROOT
    if command_text.startswith("cd ") and " && " in command_text:
        cd_part, command_text = command_text.split(" && ", 1)
        cwd = REPO_ROOT / cd_part.removeprefix("cd ").strip()
    final_cmd = []
    for part in shlex.split(command_text):
        if part.startswith("PYTHONPATH="):
            env["PYTHONPATH"] = part.split("=", 1)[1]
        else:
            final_cmd.append(part)
    return final_cmd, cwd, env


def _record_command_result(command_results: list[dict], name: str, proc: subprocess.CompletedProcess) -> None:
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    warnings = extract_chunk_warnings(output)
    command_results.append({
        "name": name,
        "exit_code": proc.returncode,
        "stdout_tail": proc.stdout.strip()[-500:] if proc.stdout else "",
        "stderr_tail": proc.stderr.strip()[-500:] if proc.stderr else "",
        "chunk_warnings": warnings,
    })


def extract_chunk_warnings(output: str) -> list[str]:
    warnings: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(pattern.search(stripped) for pattern in CHUNK_WARNING_PATTERNS):
            warnings.append(stripped[:300])
    return warnings[:5]


def _check_entry(
    entry: dict,
    quiet: bool,
    frontend_semaphore: threading.Semaphore,
) -> tuple[bool, list[str]]:
    if entry["check"] != "pass":
        return True, []

    commands = [
        ("backend", entry.get("backend_test_cmd"), 60),
        ("frontend", entry.get("frontend_build_cmd"), 120),
    ]
    commands = [(name, cmd, timeout) for name, cmd, timeout in commands if cmd]
    if not commands:
        entry["check"] = "skip"
        entry["reason"] = entry.get("reason") or "no runnable sandbox command"
        return True, []

    log_lines = []
    if not quiet:
        log_lines.append(f"\n── {entry['module']} ──\n")
    command_results = []
    entry_pass = True

    for command_name, cmd, timeout in commands:
        final_cmd, cwd, env = _prepare_command(str(cmd))
        try:
            if command_name == "frontend":
                frontend_semaphore.acquire()
            try:
                if command_name == "frontend" and _frontend_install_needed(cwd):
                    install_cmd = _frontend_install_command(cwd)
                    install_proc = subprocess.run(
                        install_cmd,
                        cwd=cwd,
                        capture_output=True,
                        text=True,
                        timeout=180,
                        env=env,
                    )
                    _record_command_result(command_results, "frontend_install", install_proc)
                    if install_proc.returncode != 0:
                        entry_pass = False
                        if not quiet:
                            log_lines.append(f"  frontend_install: FAIL (exit={install_proc.returncode})\n")
                            if install_proc.stderr:
                                log_lines.append(f"  stderr: {install_proc.stderr.strip()[-300:]}\n")
                        continue
                    if not quiet:
                        log_lines.append("  frontend_install: PASS\n")
                proc = subprocess.run(
                    final_cmd,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env,
                )
            finally:
                if command_name == "frontend":
                    frontend_semaphore.release()

            passed = proc.returncode == 0
            _record_command_result(command_results, command_name, proc)
            if not passed:
                entry_pass = False
                if not quiet:
                    log_lines.append(f"  {command_name}: FAIL (exit={proc.returncode})\n")
                    if proc.stderr:
                        log_lines.append(f"  stderr: {proc.stderr.strip()[-300:]}\n")
            elif not quiet:
                log_lines.append(f"  {command_name}: PASS (exit={proc.returncode})\n")
        except subprocess.TimeoutExpired:
            command_results.append({"name": command_name, "exit_code": -1, "stderr_tail": f"timeout (>{timeout}s)"})
            entry_pass = False
            if not quiet:
                log_lines.append(f"  {command_name}: TIMEOUT\n")
        except FileNotFoundError as e:
            command_results.append({"name": command_name, "exit_code": -127, "stderr_tail": f"command not found: {e}"})
            entry_pass = False
            if not quiet:
                log_lines.append(f"  {command_name}: FAIL command not found: {e}\n")

    entry["command_results"] = command_results
    chunk_warnings: list[str] = []
    for result in command_results:
        chunk_warnings.extend(result.get("chunk_warnings") or [])
    entry["chunk_warnings"] = chunk_warnings[:5]
    entry["check"] = "pass" if entry_pass else "fail"
    first_failed = next((r for r in command_results if r.get("exit_code") != 0), None)
    if first_failed:
        entry["exit_code"] = first_failed.get("exit_code")
        entry["stdout_tail"] = first_failed.get("stdout_tail", "")
        entry["stderr_tail"] = first_failed.get("stderr_tail", "")
    return entry_pass, log_lines


def check_sandbox_matrix(
    results: list[dict],
    quiet: bool = False,
    jobs: int = 1,
    frontend_jobs: int = 1,
) -> bool:
    """Run every available sandbox command and fail if any command fails."""
    jobs = max(1, jobs)
    frontend_jobs = max(1, frontend_jobs)
    frontend_semaphore = threading.Semaphore(frontend_jobs)

    if jobs == 1:
        all_pass = True
        for entry in results:
            entry_pass, log_lines = _check_entry(entry, quiet, frontend_semaphore)
            all_pass = all_pass and entry_pass
            if log_lines:
                sys.stdout.write("".join(log_lines))
        return all_pass

    all_pass = True
    logs_by_index: dict[int, list[str]] = {}
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {
            executor.submit(_check_entry, entry, quiet, frontend_semaphore): index
            for index, entry in enumerate(results)
        }
        for future in as_completed(futures):
            index = futures[future]
            entry_pass, log_lines = future.result()
            all_pass = all_pass and entry_pass
            logs_by_index[index] = log_lines

    if not quiet:
        for index in range(len(results)):
            log_lines = logs_by_index.get(index, [])
            if log_lines:
                sys.stdout.write("".join(log_lines))
    return all_pass


def format_markdown(results: list[dict], run_all: bool, passed: bool) -> str:
    lines = [
        "# Module Sandbox Verification Matrix",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Auto-run: {'yes' if run_all else 'no'}",
        f"Overall: {'PASS' if passed else 'FAIL' if run_all else 'N/A (--check not run)'}",
        "",
        "| Module | Sandbox | test_module.py | Backend | Samples | README Acceptance | Check | Reason |",
        "|--------|---------|---------------|---------|---------|-------------------|-------|--------|",
    ]
    for entry in results:
        status = entry.get("check", "skip")
        status_icon = "✅" if status == "pass" else "❌" if status == "fail" else "⏭️"
        reason = entry.get("reason", "") or ""
        if entry.get("exit_code") is not None and status == "fail":
            reason += f" (exit={entry['exit_code']})"
        lines.append(
            f"| {entry['module']} "
            f"| {'✅' if entry['has_sandbox'] else '❌'} "
            f"| {'✅' if entry['has_test_module'] else '❌'} "
            f"| {'✅' if entry['has_backend'] else '❌'} "
            f"| {'✅' if entry['has_samples'] else '❌'} "
            f"| {'✅' if entry.get('readme_acceptance_matrix') else '❌'} "
            f"| {status_icon} "
            f"| {reason} |"
        )

    # Summary
    total = len(results)
    passed_count = sum(1 for e in results if e.get("check") == "pass")
    fail_count = sum(1 for e in results if e.get("check") == "fail")
    skip_count = sum(1 for e in results if e.get("check") == "skip")
    lines.extend([
        "",
        f"**Summary**: {total} modules, {passed_count} pass, {fail_count} fail, {skip_count} skip",
        "",
        "### Commands to re-run",
        "",
        "```bash",
        "# Full matrix",
        "cd {} && {} dev_toolkit/module_sandbox_matrix.py --check".format(
            REPO_ROOT, BACKEND_PYTHON
        ),
        "# Single module",
        "cd {} && PYTHONPATH=backend {} modules/<key>/sandbox/test_module.py".format(
            REPO_ROOT, BACKEND_PYTHON
        ),
        "```",
    ])
    return "\n".join(lines)


def run_sandbox_matrix(
    module_keys: list[str] | None = None,
    run_check: bool = False,
    quiet: bool = False,
    jobs: int = 1,
    frontend_jobs: int = 1,
) -> tuple[list[dict], bool]:
    results = scan_sandbox_matrix(module_keys)

    if run_check:
        check_sandbox_matrix(results, quiet=quiet, jobs=jobs, frontend_jobs=frontend_jobs)

    passed = all(
        entry.get("check") == "pass" or entry.get("check") == "skip"
        for entry in results
    ) if run_check else True
    return results, passed


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Module sandbox verification matrix")
    parser.add_argument("--check", action="store_true", help="Run auto-runnable test_module.py files")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of markdown")
    parser.add_argument(
        "--module",
        action="append",
        default=None,
        help="Only scan/check one module key. Can be provided multiple times.",
    )
    parser.add_argument(
        "--modules",
        default=None,
        help="Only scan/check a comma-separated module key list, e.g. knowledge,agent.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Maximum modules to check concurrently when --check is used (default: 1).",
    )
    parser.add_argument(
        "--frontend-jobs",
        type=int,
        default=1,
        help="Maximum frontend install/build commands to run concurrently (default: 1).",
    )
    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    run_check = args.check
    module_keys = parse_requested_modules(args.module, args.modules)
    try:
        results, passed = run_sandbox_matrix(
            module_keys=module_keys,
            run_check=run_check,
            quiet=args.json,
            jobs=args.jobs,
            frontend_jobs=args.frontend_jobs,
        )
    except ValueError as e:
        parser.error(str(e))

    if args.json:
        output = json.dumps(results, ensure_ascii=False, indent=2)
    else:
        output = format_markdown(results, run_check, passed)

    print(output)
    sys.exit(0 if passed or not run_check else 1)


if __name__ == "__main__":
    main()
