import logging
import subprocess
import time
from pathlib import Path

import httpx

from app.config import get_settings
from app.services.model_watchdog.registry import ModelRecord

logger = logging.getLogger("model_watchdog.launcher")

_SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent / "scripts" / "models"


def launch_model(record: ModelRecord) -> None:
    config = get_settings()
    script_path = _SCRIPTS_DIR / record.startup_script

    if not script_path.exists():
        raise FileNotFoundError(
            f"Startup script not found: {script_path} "
            f"(model={record.name}, port={record.port})"
        )

    screen_session = f"model_{record.name}"

    screen_cmd = [
        "screen", "-dmS", screen_session,
        "zsh", str(script_path),
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

    with httpx.Client(timeout=5) as client:
        while time.time() < deadline:
            try:
                resp = client.get(health_url)
                if resp.status_code < 500:
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
    subprocess.run(
        ["screen", "-S", screen_session, "-X", "quit"],
        capture_output=True,
        timeout=5,
    )
    logger.info("Screen session %s terminated", screen_session)
