import os
from pathlib import Path

from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]
LOCAL_VENV_ENV_FILE = BACKEND_DIR / ".venv" / "admin.env"


def _load_local_env_file(env_path: Path, *, force: bool = False):
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and (force or key not in os.environ):
            os.environ[key] = value


_load_local_env_file(BACKEND_DIR / ".env", force=True)
_load_local_env_file(LOCAL_VENV_ENV_FILE)


class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "SignalBridge Backend")
    jwt_secret: str = next(
        (
            value
            for value in (
                os.getenv("JWT_SECRET", "").strip(),
                os.getenv("JWT_SECRET_KEY", "").strip(),
            )
            if value
        ),
        "change-this-secret",
    )
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    mongodb_url: str = os.getenv("MONGODB_URL", os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    mongodb_db_name: str = os.getenv("MONGODB_DB_NAME", os.getenv("MONGODB_DB_NAME", "mt5_platform"))
    default_risk_amount: float = float(os.getenv("DEFAULT_RISK_AMOUNT", "100.0"))
    timezone: str = os.getenv("APP_TIMEZONE", "Asia/Calcutta")
    metaapi_webhook_secret: str = os.getenv("METAAPI_WEBHOOK_SECRET", "")
    admin_username: str = os.getenv("ADMIN_USERNAME", "").strip()
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")
    admin_full_name: str = os.getenv("ADMIN_FULL_NAME", "Administrator").strip()
    platform_audit_db_name: str = os.getenv("PLATFORM_AUDIT_DB", os.getenv("MONGODB_DB_NAME", "mt5_platform"))
    log_format: str = os.getenv("LOG_FORMAT", "text")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_file: str = os.getenv("LOG_FILE", "logs/backend.log")
    log_to_console: bool = os.getenv("LOG_TO_CONSOLE", "false").strip().lower() in {"1", "true", "yes", "on"}
    log_max_bytes: int = int(os.getenv("LOG_MAX_BYTES", str(20 * 1024 * 1024)))
    log_backup_count: int = int(os.getenv("LOG_BACKUP_COUNT", "10"))
    cors_origins: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,"
            "https://signalbridge.in,https://www.signalbridge.in,https://app.signalbridge.in,"
            "https://main.d3inecn5vye1xf.amplifyapp.com,"
            "http://ec2-13-201-137-73.ap-south-1.compute.amazonaws.com:5173,"
            "http://13.201.137.73:5173",
        ).split(",")
        if origin.strip()
    ]
    cors_origin_regex: str = os.getenv(
        "CORS_ORIGIN_REGEX",
        r"https://([\w-]+\.)*signalbridge\.in|https://([\w-]+)\.amplifyapp\.com|"
        r"http://ec2-\d+-\d+-\d+-\d+\.ap-south-1\.compute\.amazonaws\.com:5173|"
        r"http://13\.201\.137\.73:5173",
    ).strip()


# Always keep hosted Vite/Amplify origins even when .env overrides CORS_ORIGINS with an older list.
_REQUIRED_CORS_ORIGINS = (
    "https://main.d3inecn5vye1xf.amplifyapp.com",
    "http://ec2-13-201-137-73.ap-south-1.compute.amazonaws.com:5173",
    "http://13.201.137.73:5173",
)
_REQUIRED_CORS_REGEX_PARTS = (
    r"https://([\w-]+)\.amplifyapp\.com",
    r"http://ec2-\d+-\d+-\d+-\d+\.ap-south-1\.compute\.amazonaws\.com:5173",
    r"http://13\.201\.137\.73:5173",
)


settings = Settings()
for _origin in _REQUIRED_CORS_ORIGINS:
    if _origin not in settings.cors_origins:
        settings.cors_origins.append(_origin)
_regex = settings.cors_origin_regex or ""
for _part in _REQUIRED_CORS_REGEX_PARTS:
    if _part not in _regex:
        _regex = f"{_regex}|{_part}" if _regex else _part
settings.cors_origin_regex = _regex
