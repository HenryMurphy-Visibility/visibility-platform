# ============================================================
# log_utils.py — Contextual Logging for Serial Portfolio Engine
# ============================================================
import logging
import functools
import time
import threading

# 🔧 Global verbosity toggle
DIAGNOSTIC_MODE = True

# ------------------------------------------------------------
# Configure global logger
# ------------------------------------------------------------
logger = logging.getLogger("visibility")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if DIAGNOSTIC_MODE else logging.INFO)

# ------------------------------------------------------------
# Context helper
# ------------------------------------------------------------
def get_portfolio_context(kwargs):
    """Attempt to extract a portfolio name for logging context."""
    for key in ["portfolio", "fund", "entity"]:
        if key in kwargs:
            return str(kwargs[key])
    return "UnknownPortfolio"

# ------------------------------------------------------------
# Decorator for contextual, serial diagnostic logging
# ------------------------------------------------------------
def diagnostic_log(func):
    """Logs entry/exit for serial portfolio execution with shard context."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        portfolio = kwargs.get("portfolio", "UnknownPortfolio")
        shard = kwargs.get("shard", "Main")
        thread_name = threading.current_thread().name
        prefix = f"[{thread_name}][Shard={shard}][Portfolio={portfolio}]"

        start = time.time()
        logger.info(f"{prefix} ➡️ Entering {func.__name__}")
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start
            logger.info(f"{prefix} ✅ Exiting {func.__name__} (Elapsed {elapsed:.3f}s)")
            return result
        except Exception as e:
            logger.exception(f"{prefix} ❌ Exception in {func.__name__}: {e}")
            raise
    return wrapper
