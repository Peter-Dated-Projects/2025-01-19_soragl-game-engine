import logging

# library convention: stay silent unless the application configures logging
logging.getLogger("soragl").addHandler(logging.NullHandler())


def configure(level: int = logging.INFO) -> None:
    """Send soragl log records to stderr. Call once from the application."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(relativeCreated)8.0fms %(levelname)-7s %(name)s: %(message)s"
        )
    )
    root = logging.getLogger("soragl")
    root.addHandler(handler)
    root.setLevel(level)
