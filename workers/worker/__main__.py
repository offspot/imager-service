import signal
import logging

from creator import CreatorWorker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main(worker_cls):
    worker = worker_cls()

    def signal_handler(sig, frame):
        logger.error("requesting quit via {}".format(sig))
        worker.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGHUP, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGQUIT, signal_handler)

    try:
        worker.start()
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)


if __name__ == "__main__":
    main(CreatorWorker)
