"""
Worker entry point.

Run with:
    python -m workers.run_worker
"""

import asyncio
import signal
import structlog

from workers.drift_worker import DriftDetectionWorker

logger = structlog.get_logger(__name__)


def main():
    worker = DriftDetectionWorker()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _shutdown(signum, frame):
        logger.info("shutdown_signal_received", signum=signum)
        worker.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        loop.run_until_complete(worker.run())
    finally:
        loop.close()
        logger.info("worker_exited")


if __name__ == "__main__":
    main()