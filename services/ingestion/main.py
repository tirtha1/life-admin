"""
Ingestion service entry point.
Starts the Celery worker (and optionally Beat scheduler).

Usage:
    # Worker only
    python -m services.ingestion.main worker

    # Worker + Beat (dev convenience)
    python -m services.ingestion.main worker --beat

    # Beat scheduler only
    python -m services.ingestion.main beat
"""
import sys
import os

# Set up telemetry before importing anything else
from shared.telemetry.setup import setup_telemetry
setup_telemetry("ingestion")

from services.ingestion.tasks import app  # noqa: E402 — after telemetry init

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "worker"
    extra_args = sys.argv[2:]

    if mode == "worker":
        argv = [
            "worker",
            "--loglevel=info",
            "--concurrency=4",
            "--queues=ingestion",
            *extra_args,
        ]
        app.worker_main(argv=argv)

    elif mode == "beat":
        argv = [
            "beat",
            "--loglevel=info",
            "--scheduler=celery.beat:PersistentScheduler",
            *extra_args,
        ]
        app.worker_main(argv=argv)

    else:
        print(f"Unknown mode: {mode}. Use 'worker' or 'beat'.")
        sys.exit(1)
