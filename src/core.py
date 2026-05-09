"""
コアユーティリティ
ログ設定・ファイル情報など。フォルダ走査と解析は scan_analyze_service を参照。
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from .config import config

logger = logging.getLogger(__name__)

from .utils import format_eta, format_file_size, format_file_size_kb, hamming_dist, path_under_root

__all__ = [
    "setup_logging",
    "get_capture_time",
    "get_file_info",
    "path_under_root",
    "format_eta",
    "hamming_dist",
    "format_file_size",
    "format_file_size_kb",
]


def setup_logging() -> None:
    """ロギングを初期化（ローテーション付きファイルとコンソール）。"""
    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.DEBUG)
    fmt = "%(asctime)s [%(levelname)s] (%(threadName)s) - %(message)s"

    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    root_logger.setLevel(log_level)

    file_handler = RotatingFileHandler(
        config.LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(fmt))
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(fmt))
    root_logger.addHandler(console_handler)

    logging.getLogger("PIL").setLevel(logging.WARNING)


def get_capture_time(path: str) -> float:
    """ファイルの更新日時（mtime）を返す。失敗時は 0.0。"""
    try:
        if not config.validate_path(path):
            logger.warning("Invalid path for get_capture_time: %s", path)
            return 0.0
        return os.path.getmtime(path)
    except (OSError, IOError) as e:
        logger.error("Failed to get mtime for %s: %s", path, e)
        return 0.0
    except Exception as e:
        logger.error("Unexpected error getting mtime for %s: %s", path, e, exc_info=True)
        return 0.0


def get_file_info(path: str) -> dict:
    """exists / file_size / image_width / image_height を返す。"""
    result = {"exists": False, "file_size": 0, "image_width": None, "image_height": None}

    try:
        if not os.path.exists(path):
            return result

        result["exists"] = True
        result["file_size"] = os.path.getsize(path)

        try:
            from PIL import Image

            with Image.open(path) as img:
                result["image_width"] = img.width
                result["image_height"] = img.height
        except (OSError, IOError) as e:
            logger.debug("Could not read image dimensions for %s: %s", path, e)
        except Exception as e:
            logger.warning("Unexpected error reading image dimensions for %s: %s", path, e)

    except Exception as e:
        logger.warning("Failed to get file info for %s: %s", path, e)

    return result
