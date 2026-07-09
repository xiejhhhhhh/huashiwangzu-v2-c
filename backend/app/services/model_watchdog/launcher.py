import logging
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path

import httpx

from app.config import get_settings
from app.gateway.config import get_models_config
from app.services.model_watchdog.registry import ModelRecord

logger = logging.getLogger("model_watchdog.launcher")

_SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent / "scripts" / "models"


def launch_model(record: ModelRecord) -> None:
    config = get_settings()
    launch_cmd = _build_launch_command(record)

    screen_session = f"model_{record.name}"

    screen_cmd = [
        "screen", "-dmS", screen_session,
        *launch_cmd,
    ]

    logger.info(
        "Launching model %s via screen session %s: %s",
        record.name, screen_session, " ".join(screen_cmd),
    )

    result = subprocess.run(
        screen_cmd,
        capture_output=True,
        text=True,
        timeout=10,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to launch screen session for model {record.name}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )

    logger.info(
        "Screen session %s launched, polling health check...", screen_session
    )

    _poll_until_healthy(
        record=record,
        timeout=config.MODEL_WATCHDOG_TIMEOUT,
        interval=config.MODEL_WATCHDOG_POLL_INTERVAL,
    )


def _poll_until_healthy(
    record: ModelRecord,
    timeout: int,
    interval: float,
) -> None:
    health_url = record.health_url()
    deadline = time.time() + timeout

    with httpx.Client(timeout=5, trust_env=False) as client:
        while time.time() < deadline:
            try:
                resp = client.get(health_url)
                if _healthy_status(record, resp.status_code):
                    logger.info(
                        "Model %s is healthy (HTTP %d)", record.name, resp.status_code
                    )
                    return
            except (httpx.RequestError, httpx.TimeoutException):
                pass

            time.sleep(interval)

    raise TimeoutError(
        f"Model {record.name} did not become healthy within {timeout}s "
        f"(endpoint: {health_url})"
    )


def kill_model(record: ModelRecord) -> None:
    screen_session = f"model_{record.name}"
    _run_quiet(["screen", "-S", screen_session, "-X", "quit"], timeout=5)
    stopped_pids = _kill_processes_on_port(record.port)
    _run_quiet(["screen", "-wipe"], timeout=5)
    logger.info(
        "Model %s stopped via screen session %s; port_pids=%s",
        record.name,
        screen_session,
        stopped_pids,
    )


def _healthy_status(record: ModelRecord, status_code: int) -> bool:
    if record.model_type == "local":
        return 200 <= status_code < 300
    return status_code < 500


def _build_launch_command(record: ModelRecord) -> list[str]:
    launch = record.launch or {}
    if launch:
        backend = str(launch.get("backend") or "").lower()
        if backend in {"llama.cpp", "llama"}:
            return _build_llama_cpp_command(record, launch)

        raw_command = launch.get("command")
        if isinstance(raw_command, list) and raw_command:
            mapping = _launch_mapping(record, launch)
            return [_format_launch_arg(str(arg), mapping) for arg in raw_command]
        if isinstance(raw_command, str) and raw_command.strip():
            mapping = _launch_mapping(record, launch)
            return shlex.split(_format_launch_arg(raw_command, mapping))

    script_path = _SCRIPTS_DIR / record.startup_script
    if not script_path.exists():
        raise FileNotFoundError(
            f"Startup script not found: {script_path} "
            f"(model={record.name}, port={record.port})"
        )
    return ["zsh", str(script_path)]


def _build_llama_cpp_command(record: ModelRecord, launch: dict) -> list[str]:
    binary = _resolve_llama_server_binary(launch)
    mapping = _launch_mapping(record, launch)
    _validate_launch_mapping_paths(record, mapping)
    raw_args = launch.get("args")
    if isinstance(raw_args, list) and raw_args:
        args = [_format_launch_arg(str(arg), mapping) for arg in raw_args]
    else:
        args = ["-m", mapping["model_path"], "--port", mapping["port"]]
    return [binary, *args]


def _resolve_llama_server_binary(launch: dict) -> str:
    local_bin = get_models_config().get("local_bin", {})
    explicit = str(launch.get("llama_server") or local_bin.get("llama_server") or "").strip()
    if explicit:
        return _validate_executable(_expand_config_value(explicit), "llama.cpp server binary")

    env_names = [
        str(launch.get("llama_server_env") or "").strip(),
        str(local_bin.get("llama_server_env") or "").strip(),
        "LLAMA_CPP_SERVER_BIN",
    ]
    for env_name in env_names:
        if not env_name:
            continue
        value = os.environ.get(env_name, "").strip()
        if value:
            return _validate_executable(_expand_config_value(value), f"{env_name} llama.cpp server binary")

    from_path = shutil.which("llama-server")
    if from_path:
        return from_path

    raise FileNotFoundError(
        "llama.cpp server binary is not configured. Set LLAMA_CPP_SERVER_BIN "
        "or local_bin.llama_server in models.json."
    )


def _launch_mapping(record: ModelRecord, launch: dict) -> dict[str, str]:
    model_root = _resolve_model_root(launch)
    if not str(model_root):
        raise ValueError(f"local_bin.model_root is required for model {record.name}")
    mapping = {
        "model_root": str(model_root),
        "port": str(record.port),
    }
    for key, value in launch.items():
        if key.endswith("_path") and isinstance(value, str):
            mapping[key] = _resolve_model_path(value, model_root)
    if "model_path" not in mapping:
        raise ValueError(f"launch.model_path is required for model {record.name}")
    return mapping


def _validate_launch_mapping_paths(record: ModelRecord, mapping: dict[str, str]) -> None:
    missing: list[str] = []
    for key, value in mapping.items():
        if not key.endswith("_path"):
            continue
        path = Path(value)
        if not path.exists():
            missing.append(f"{key}={path}")
    if missing:
        joined = "; ".join(missing)
        raise FileNotFoundError(f"Configured model file missing for {record.name}: {joined}")


def _validate_executable(path_value: str, label: str) -> str:
    path = Path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    if not os.access(path, os.X_OK):
        raise PermissionError(f"{label} is not executable: {path}")
    return str(path)


def _resolve_model_root(launch: dict) -> Path:
    local_bin = get_models_config().get("local_bin", {})
    env_names = [
        str(launch.get("model_root_env") or "").strip(),
        str(local_bin.get("model_root_env") or "").strip(),
        "LOCAL_MODEL_ROOT",
    ]
    for env_name in env_names:
        if not env_name:
            continue
        value = os.environ.get(env_name, "").strip()
        if value:
            return Path(_expand_config_value(value))
    return Path(_expand_config_value(str(local_bin.get("model_root", ""))))


def _resolve_model_path(value: str, model_root: Path) -> str:
    expanded = Path(_expand_config_value(value))
    if expanded.is_absolute():
        return str(expanded)
    return str(model_root / expanded)


def _format_launch_arg(value: str, mapping: dict[str, str]) -> str:
    return _expand_config_value(value).format_map(mapping)


def _expand_config_value(value: str) -> str:
    return os.path.expanduser(os.path.expandvars(value))


def _kill_processes_on_port(port: int) -> list[int]:
    if port <= 0:
        return []
    result = _run_quiet(["lsof", "-ti", f"tcp:{port}"], timeout=5, text=True)
    pids = sorted({
        int(line.strip())
        for line in (result.stdout or "").splitlines()
        if line.strip().isdigit()
    })
    for pid in pids:
        _terminate_process_group(pid)
    return pids


def _terminate_process_group(pid: int) -> None:
    try:
        import psutil

        proc = psutil.Process(pid)
        children = proc.children(recursive=True)
        targets = [*children, proc]
        for target in targets:
            try:
                target.terminate()
            except psutil.NoSuchProcess:
                pass
        gone, alive = psutil.wait_procs(targets, timeout=5)
        for target in alive:
            try:
                target.kill()
            except psutil.NoSuchProcess:
                pass
        return
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("psutil process-tree termination failed for pid %s: %s", pid, exc)

    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        return
    except PermissionError:
        logger.warning("No permission to terminate model process pid %s", pid)
        return

    deadline = time.time() + 5
    while time.time() < deadline:
        if not _process_alive(pid):
            return
        time.sleep(0.2)

    try:
        os.kill(pid, 9)
    except ProcessLookupError:
        return
    except PermissionError:
        logger.warning("No permission to kill model process pid %s", pid)
        return


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _run_quiet(command: list[str], *, timeout: int, text: bool = False) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=text,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        logger.debug("Command failed while managing model process: %s (%s)", command, exc)
        return subprocess.CompletedProcess(command, returncode=1, stdout="", stderr=str(exc))
