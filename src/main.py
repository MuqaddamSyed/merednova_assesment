#!/usr/bin/env python3
"""Voice Coder — entry point."""

from __future__ import annotations

import argparse
import queue
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.config import load_config
from src.events.types import UIEvent
from src.orchestrator import VoiceOrchestrator
from src.ui.app import VoiceCoderApp
from src.utils.logging_setup import setup_logging
from src.utils.preflight import run_preflight
from src.utils.shutdown import ShutdownCoordinator, install_exit_handlers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Voice Coder — hands-free voice interface for Aider",
    )
    parser.add_argument("-c", "--config", type=Path, default=None, help="Path to config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Simulate Aider without spawning")
    parser.add_argument("--no-ui", action="store_true", help="Run headless (logging only)")
    parser.add_argument("--whisper-model", default=None, help="Override STT model size")
    parser.add_argument("--profile", default=None, help="Config profile: demo, quality")
    return parser.parse_args()


def run_headless(orchestrator: VoiceOrchestrator, shutdown: ShutdownCoordinator) -> None:
    import time

    print("Voice Coder running headless. Ctrl+C to exit.")
    try:
        while not shutdown.requested:
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown.request_shutdown()


def main() -> int:
    load_dotenv()
    args = parse_args()
    config = load_config(args.config, profile=args.profile)
    if args.dry_run:
        config.agent.dry_run = True
    if args.whisper_model:
        config.stt.model_size = args.whisper_model

    setup_logging(config.logging.level, config.logging.file)
    shutdown = ShutdownCoordinator()
    event_queue: queue.Queue[UIEvent] = queue.Queue()
    preflight = run_preflight(config)

    orchestrator = VoiceOrchestrator(config, shutdown, event_queue)
    install_exit_handlers(shutdown)

    try:
        if args.no_ui:
            orchestrator.start()
            run_headless(orchestrator, shutdown)
            return 0

        app = VoiceCoderApp(orchestrator, event_queue, preflight=preflight)
        app.run()
    except KeyboardInterrupt:
        shutdown.request_shutdown()
    finally:
        shutdown.request_shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
