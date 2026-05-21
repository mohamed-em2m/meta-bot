import json
import os
import pathlib

from dynaconf import Dynaconf

# Configuration Directory
CONFIG_DIR = pathlib.Path(__file__).parent.resolve()

# Root directory of the repository
ROOT_DIR = CONFIG_DIR.parent.parent.resolve()

# Initialize Dynaconf settings
settings = Dynaconf(
	settings_files=[
		str(CONFIG_DIR / 'settings.toml'),
	],
	load_dotenv=True,
	envvar_prefix='DYNACONF',
)

# Export to environment variables to keep existing os.environ.get calls working
for key, value in settings.items():
	key_upper = key.upper()

	# Check if this setting is a path pointing to Config/ or Agent/ and resolve it
	if isinstance(value, str):
		if value.startswith('Config/'):
			# Resolve to the new absolute path under meta_app_chatbot/config/
			relative_part = value.split('/', 1)[1]
			resolved_path = str(CONFIG_DIR / relative_part)
			settings.set(key, resolved_path)
			value = resolved_path  # update value for environment export
		elif value.startswith('Agent/'):
			# Resolve to the new absolute path under meta_app_chatbot/core/agent/
			relative_part = value.split('/', 1)[1]
			resolved_path = str(CONFIG_DIR.parent / 'core' / 'agent' / relative_part)
			settings.set(key, resolved_path)
			value = resolved_path  # update value for environment export

	if isinstance(value, (dict, list)):
		str_val = json.dumps(value)
	else:
		str_val = str(value)

	os.environ[key] = str_val
	os.environ[key_upper] = str_val

# Compatibility for specifically named env vars (may be redundant if already in TOML)
if 'firebase_path' in settings:
	os.environ['firebase_path'] = settings.firebase_path
if 'GOOGLE_APPLICATION_CREDENTIALS' in settings:
	os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = (
		settings.GOOGLE_APPLICATION_CREDENTIALS
	)
