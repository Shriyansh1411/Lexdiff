"""Runtime paths. The data directory comes from LENDWISE_DATA_DIR so tests and the canary can sandbox it."""
import os


def data_dir() -> str:
    d = os.environ.get("LENDWISE_DATA_DIR", os.path.join(os.getcwd(), "data"))
    os.makedirs(d, exist_ok=True)
    return d


def path(*parts: str) -> str:
    p = os.path.join(data_dir(), *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p
