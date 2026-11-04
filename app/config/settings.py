"""全局配置。

systemd（ops/crm-api.service）通过 ``Environment=CRM_DB/CRM_UPLOADS`` 注入真实路径；
这里给出同样的默认值做兜底，便于本地/测试直接跑。测试通过 ``tests/_bootstrap.py``
把这两个变量改到 /tmp 下的临时文件。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- 数据库 ----
    #: SQLite 是默认和回归测试基线；生产切换 MySQL 时显式改成 mysql。
    CRM_DB_ENGINE: Literal["sqlite", "mysql"] = "sqlite"
    CRM_DB: str = "/opt/data/crm/crm.db"
    CRM_UPLOADS: str = "/opt/data/crm/uploads"

    # ---- MySQL（CRM_DB_ENGINE=mysql 时生效）----
    CRM_MYSQL_HOST: str = "127.0.0.1"
    CRM_MYSQL_PORT: int = 3306
    CRM_MYSQL_USER: str = "crm"
    CRM_MYSQL_PASSWORD: str = ""
    CRM_MYSQL_DATABASE: str = "sunshine_crm"
    CRM_MYSQL_CHARSET: str = "utf8mb4"
    # 内网/本机默认关闭；公网或跨网部署应启用 TLS，并限制数据库安全组。
    CRM_MYSQL_SSL_DISABLED: bool = True

    # ---- 服务 ----
    API_PORT: int = 8010
    # 固定 12h，不滑动：用户明确要求"每天重登一次"
    SESSION_TTL_HOURS: int = 12

    # ---- 会话 Cookie ----
    COOKIE_NAME: str = "crm_sid"
    # 内网 HTTP 阶段必须 False；上了 HTTPS 由部署任务置 CRM_COOKIE_SECURE=1
    COOKIE_SECURE: bool = False

    # ---- 首次启动建种子用户用（之后密码只存在 DB 里）----
    ADMIN_USERNAME: str = "chen"
    ADMIN_PASSWORD: str = "change-me"

    @property
    def db_path(self) -> Path:
        return Path(self.CRM_DB)

    @property
    def uploads_path(self) -> Path:
        return Path(self.CRM_UPLOADS)

    @property
    def database_label(self) -> str:
        """用于日志/健康检查，绝不包含数据库密码。"""
        if self.CRM_DB_ENGINE == "sqlite":
            return str(self.db_path)
        return (
            f"mysql://{self.CRM_MYSQL_USER}@"
            f"{self.CRM_MYSQL_HOST}:{self.CRM_MYSQL_PORT}/{self.CRM_MYSQL_DATABASE}"
        )


settings = Settings()
