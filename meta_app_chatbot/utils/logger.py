"""
Centralized logging configuration for the Meta Ads Manager application.
Call ``setup_logging()`` once at application startup (e.g. in main.py).
Every other module simply uses the standard library pattern::

    import logging

    logger = logging.getLogger(__name__)

That's it — no special imports needed.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from pythonjsonlogger.json import JsonFormatter


def get_project_root(start_path: Path) -> Path:
	for parent in [start_path] + list(start_path.parents):
		if (parent / 'pyproject.toml').exists() or (parent / '.git').exists():
			return parent
	raise RuntimeError('Project root not found')


PROJECT_ROOT = get_project_root(Path(__file__).resolve())
_DEFAULT_LOG_DIR = PROJECT_ROOT / 'logs'
_DEFAULT_LOG_FILE = 'app.log.jsonl'
_DEFAULT_LEVEL = logging.DEBUG
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per log file
_BACKUP_COUNT = 3  # keep 3 rotated copies

# ── Formatters ───────────────────────────────────────────────────────
# Console gets a pretty, human-readable format
_CONSOLE_FMT = '%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s'

# File gets clean space-separated keys for JsonFormatter to parse correctly
_FILE_FMT = '%(asctime)s %(levelname)s %(name)s %(lineno)d %(message)s'
_DATE_FMT = '%Y-%m-%d %H:%M:%S'

_is_configured = False


def setup_logging(
	level: int = _DEFAULT_LEVEL,
	log_dir: str | Path | None = None,
	log_file: str = _DEFAULT_LOG_FILE,
) -> None:
	"""
	Configure the root logger with console + rotating file handlers.
	Safe to call multiple times — subsequent calls are no-ops.

	Args:
	    level: Minimum log level (default: logging.DEBUG).
	    log_dir: Directory for log files. Defaults to ``src/logs/``.
	    log_file: Log filename inside *log_dir*.
	"""
	global _is_configured
	if _is_configured:
		return

	_is_configured = True

	log_dir = Path(log_dir) if log_dir else _DEFAULT_LOG_DIR
	log_dir.mkdir(parents=True, exist_ok=True)

	log_path = log_dir / log_file

	# Dynamically name the error log based on the main log_file name
	# e.g., app.log.jsonl -> app_error.jsonl
	error_filename = f'{log_path.stem.replace(".log", "")}_error{log_path.suffix}'
	log_error_path = log_dir / error_filename

	root = logging.getLogger()
	root.setLevel(level)

	# ── Console handler ──────────────────────────────────────────────
	console = logging.StreamHandler(sys.stdout)
	console.setLevel(level)
	console.setFormatter(logging.Formatter(_CONSOLE_FMT, datefmt=_DATE_FMT))
	root.addHandler(console)

	# ── Error file handler ───────────────────────────────────────────
	error_handler = RotatingFileHandler(
		log_error_path,
		maxBytes=_MAX_BYTES,
		backupCount=_BACKUP_COUNT,
		encoding='utf-8',
	)
	error_handler.setLevel(logging.ERROR)
	error_handler.setFormatter(JsonFormatter(_FILE_FMT))
	root.addHandler(error_handler)

	# ── Rotating file handler ────────────────────────────────────────
	file_handler = RotatingFileHandler(
		log_path,
		maxBytes=_MAX_BYTES,
		backupCount=_BACKUP_COUNT,
		encoding='utf-8',
	)
	file_handler.setLevel(level)
	file_handler.setFormatter(JsonFormatter(_FILE_FMT))
	root.addHandler(file_handler)

	# Quiet down noisy third-party loggers
	for logger_name in ('httpx', 'httpcore', 'urllib3'):
		logging.getLogger(logger_name).setLevel(logging.WARNING)


def log_ads(
	logger: logging.Logger,
	results: list[dict],
	level: int = logging.DEBUG,
	class_name: str = 'Main',
) -> None:
	"""
	Logs metadata about processed ads. Outputs human-readable strings for the console
	and injects structured JSON data for the file loggers.
	"""
	for task in results:
		entity = task.get('entity') or {}
		actions = task.get('actions') or []

		ad_id = entity.get('ad_id')
		adset_id = entity.get('adset_id')
		campaign_id = entity.get('campaign_id')

		actions_done = task.get('done') or []
		actions_skipped = task.get('skipped') or []

		# We keep string building ONLY for the human-readable console message
		action_descriptions = (
			', '.join(f'{a.get("name")} (rule={a.get("rule_id")})' for a in actions)
			or 'none'
		)

		# Extract stats safely
		stats = {
			k: entity.get(k)
			for k in (
				'cpm',
				'ctr',
				'impressions',
				'spend',
				'cost_per_message',
				'cost_per_result',
				'cpp',
				'cpc',
			)
			if entity.get(k) is not None
		}

		stats_str = ', '.join(f'{key}:{value}' for key, value in stats.items())

		# 🚀 Use `logger.log()` and pass variables using `extra={}`
		# The extra dictionary will automatically be parsed by JsonFormatter!
		logger.log(
			level,
			'[%s] task_processed ad_id=%s adset_id=%s campaign_id=%s stats=[%s] actions=[%s]',
			class_name,
			ad_id,
			adset_id,
			campaign_id,
			stats_str,
			action_descriptions,
			extra={
				'class_name': class_name,
				'ad_id': ad_id,
				'adset_id': adset_id,
				'campaign_id': campaign_id,
				'stats': stats,
				'actions_done': actions_done,
				'actions_skipped': actions_skipped,
				'raw_actions': actions,  # Full structured data is saved to JSON log!
			},
		)
