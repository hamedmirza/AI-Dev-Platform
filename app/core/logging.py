
import logging

from app.core.request_context import get_request_id, get_run_id


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        record.run_id = get_run_id() or "-"
        return True


def configure_logging(level: str) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] request_id=%(request_id)s run_id=%(run_id)s "
            "%(message)s"
        )
    )
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(handler)
