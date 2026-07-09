import logging
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import NamedTuple

import httpx

from app.config import get_settings
from app.gateway.config import get_models_config
from app.services.model_watchdog.registry import ModelRecord
from app.services.model_watchdog.runtime import (
    mark_model_failed,
    mark_model_healthy,
    mark_model_loading,
    mark_model_starting,
)

logger = logging.getLogger("model_watchdog.launcher")

_SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent / "scripts" / "models"


def launch_model(record: ModelRecord) -> None:
    config = get_settings()
    launch_cmd = _build_launch_command(record)
    mark_model_starting(record, "launch command accepted by watchdog")

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
        timeout=record.launch_timeout_seconds or config.MODEL_WATCHDOG_TIMEOUT,
        interval=config.MODEL_WATCHDOG_POLL_INTERVAL,
        launch_cmd=launch_cmd,
    )


def _poll_until_healthy(
    record: ModelRecord,
    timeout: int,
    interval: float,
    launch_cmd: list[str] | None = None,
) -> None:
    health_url = record.health_url()
    start_time = time.time()
    startup_stall_timeout = max(10, record.startup_stall_timeout_seconds or timeout)
    max_startup_seconds = max(timeout, record.max_startup_seconds or (timeout + startup_stall_timeout))
    last_progress_at = start_time
    last_signal = _LoadingSignal()

    with httpx.Client(timeout=5, trust_env=False) as client:
        while True:
            now = time.time()
            decision = _startup_wait_decision(
                elapsed_seconds=now - start_time,
                seconds_since_progress=now - last_progress_at,
                launch_timeout_seconds=timeout,
                startup_stall_timeout_seconds=startup_stall_timeout,
                max_startup_seconds=max_startup_seconds,
            )
            if not decision.continue_waiting:
                snapshot = _model_process_snapshot(record, launch_cmd or [])
                details = {
                    "reason": decision.reason,
                    "elapsed_seconds": round(now - start_time, 3),
                    "seconds_since_progress": round(now - last_progress_at, 3),
                    "launch_timeout_seconds": timeout,
                    "startup_stall_timeout_seconds": startup_stall_timeout,
                    "max_startup_seconds": max_startup_seconds,
                    "process": snapshot,
                }
                message = (
                    f"Model {record.name} did not become healthy: {decision.reason} "
                    f"(endpoint: {health_url})"
                )
                mark_model_failed(record, message=message, details=details)
                raise TimeoutError(message)

            status_code: int | None = None
            try:
                resp = client.get(health_url)
                status_code = resp.status_code
                if _healthy_status(record, resp.status_code):
                    elapsed = time.time() - start_time
                    details = {
                        "http_status": resp.status_code,
                        "elapsed_seconds": round(elapsed, 3),
                    }
                    mark_model_healthy(
                        record,
                        message=f"model is healthy after {elapsed:.1f}s",
                        details=details,
                    )
                    logger.info(
                        "Model %s is healthy (HTTP %d)", record.name, resp.status_code
                    )
                    return
            except (httpx.RequestError, httpx.TimeoutException):
                pass

            signal = _loading_signal(record, launch_cmd or [], status_code)
            if signal.is_progress_since(last_signal):
                last_progress_at = time.time()
                last_signal = signal
                mark_model_loading(
                    record,
                    message=f"model is loading ({signal.reason})",
                    details={
                        "progress_reason": signal.reason,
                        "http_status": status_code,
                        "process": signal.process,
                        "elapsed_seconds": round(last_progress_at - start_time, 3),
                        "launch_timeout_seconds": timeout,
                        "startup_stall_timeout_seconds": startup_stall_timeout,
                        "max_startup_seconds": max_startup_seconds,
                    },
                )

            time.sleep(interval)


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


class _StartupDecision(NamedTuple):
    continue_waiting: bool
    reason: str


class _LoadingSignal(NamedTuple):
    process_key: str = ""
    rss_mb: float = 0.0
    http_status: int | None = None
    reason: str = "no_signal"
    process: dict | None = None

    def is_progress_since(self, previous: "_LoadingSignal") -> bool:
        if self.http_status is not None and self.http_status != previous.http_status:
            return True
        if self.process_key and self.process_key != previous.process_key:
            return True
        if self.rss_mb > previous.rss_mb + 32:
            return True
        return False


def _startup_wait_decision(
    *,
    elapsed_seconds: float,
    seconds_since_progress: float,
    launch_timeout_seconds: int,
    startup_stall_timeout_seconds: int,
    max_startup_seconds: int,
) -> _StartupDecision:
    if elapsed_seconds >= max_startup_seconds:
        return _StartupDecision(False, "max_startup_timeout")
    if elapsed_seconds < launch_timeout_seconds:
        return _StartupDecision(True, "within_launch_timeout")
    if seconds_since_progress < startup_stall_timeout_seconds:
        return _StartupDecision(True, "loading_progress_observed")
    return _StartupDecision(False, "loading_stalled")


def _loading_signal(
    record: ModelRecord,
    launch_cmd: list[str],
    http_status: int | None,
) -> _LoadingSignal:
    process = _model_process_snapshot(record, launch_cmd)
    pids = process.get("pids", [])
    rss_mb = float(process.get("rss_mb") or 0.0)
    if pids and rss_mb > 0:
        return _LoadingSignal(
            process_key=",".join(str(pid) for pid in pids),
            rss_mb=rss_mb,
            http_status=http_status,
            reason="process_rss_progress",
            process=process,
        )
    if pids:
        return _LoadingSignal(
            process_key=",".join(str(pid) for pid in pids),
            rss_mb=0.0,
            http_status=http_status,
            reason="process_detected",
            process=process,
        )
    if http_status is not None:
        return _LoadingSignal(
            http_status=http_status,
            reason="health_endpoint_responded",
            process=process,
        )
    return _LoadingSignal(process=process)


def _model_process_snapshot(record: ModelRecord, launch_cmd: list[str]) -> dict:
    pids = set(_pids_on_port(record.port))
    fragments = _process_match_fragments(record, launch_cmd)
    if fragments:
        pids.update(_pids_matching_fragments(fragments))
    processes: list[dict] = []
    total_rss = 0
    try:
        import psutil

        for pid in sorted(pids):
            try:
                proc = psutil.Process(pid)
                rss = int(proc.memory_info().rss)
                total_rss += rss
                processes.append({
                    "pid": pid,
                    "rss_mb": round(rss / 1024 / 1024, 2),
                    "status": proc.status(),
                    "cmdline": " ".join(proc.cmdline())[:500],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except ImportError:
        pass
    return {
        "pids": sorted(pids),
        "rss_mb": round(total_rss / 1024 / 1024, 2),
        "processes": processes,
        "match_fragments": fragments,
    }


def _pids_on_port(port: int) -> list[int]:
    if port <= 0:
        return []
    result = _run_quiet(["lsof", "-ti", f"tcp:{port}"], timeout=5, text=True)
    return sorted({
        int(line.strip())
        for line in (result.stdout or "").splitlines()
        if line.strip().isdigit()
    })


def _process_match_fragments(record: ModelRecord, launch_cmd: list[str]) -> list[str]:
    fragments: set[str] = set()
    if record.startup_script:
        fragments.add(Path(record.startup_script).name)
    for arg in launch_cmd:
        if not arg:
            continue
        path = Path(arg)
        if path.suffix.lower() in {".gguf", ".safetensors", ".bin", ".py"}:
            fragments.add(path.name)
        elif "Qwen" in arg or "bge-" in arg or "gemma" in arg:
            fragments.add(path.name or arg)
    if record.name:
        fragments.add(record.name)
    return sorted(fragment for fragment in fragments if len(fragment) >= 4)


def _pids_matching_fragments(fragments: list[str]) -> list[int]:
    try:
        import psutil

        pids: list[int] = []
        current_pid = os.getpid()
        for proc in psutil.process_iter(["pid", "cmdline"]):
            pid = int(proc.info.get("pid") or 0)
            if pid <= 0 or pid == current_pid:
                continue
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if cmdline and any(fragment in cmdline for fragment in fragments):
                pids.append(pid)
        return pids
    except ImportError:
        return []


def _kill_processes_on_port(port: int) -> list[int]:
    if port <= 0:
        return []
    pids = _pids_on_port(port)
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
