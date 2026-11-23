"""数据库引擎、会话与建库建表。"""
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


class Base(DeclarativeBase):
    """全部 ORM 模型的基类。"""


# 增量列迁移：(表, 列, 列定义 SQL)。create_all 只建新表不改旧表，
# 已存在表补列在此声明（幂等：先查 information_schema 再 ALTER）。
_ADD_COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    ("storyboards", "episode_id", "INT NULL"),
    ("timelines", "episode_id", "INT NULL"),
    # 登录注册流程：users 表补齐认证字段（email 唯一索引在 _ensure_indexes 处理）
    ("users", "email", "VARCHAR(128) NULL"),
    ("users", "locked_until", "DATETIME NULL"),
    ("users", "fail_count", "INT NOT NULL DEFAULT 0"),
    # 项目封面
    ("projects", "cover_url", "VARCHAR(500) NULL"),
]


def _ensure_indexes(conn) -> None:
    """为存量表补齐唯一索引（幂等：先查 information_schema 再 CREATE）。"""
    indexes = [
        ("users", "uq_users_email", "ALTER TABLE `users` ADD UNIQUE INDEX `uq_users_email` (`email`)"),
    ]
    for table, name, ddl in indexes:
        exists = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :t AND INDEX_NAME = :i"
            ),
            {"db": settings.DB_NAME, "t": table, "i": name},
        ).scalar()
        if not exists:
            conn.execute(text(ddl))


def _ensure_columns(conn) -> None:
    for table, column, ddl in _ADD_COLUMN_MIGRATIONS:
        exists = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :t AND COLUMN_NAME = :c"
            ),
            {"db": settings.DB_NAME, "t": table, "c": column},
        ).scalar()
        if not exists:
            conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {ddl}"))


def _backfill_episodes(conn) -> None:
    """存量数据回填：为没有任何集的项目创建第 1 集，并把项目级分镜/时间线归入其中。

    用单条 INSERT...SELECT...WHERE NOT EXISTS 原子完成"检查+插入"，
    消除 SELECT-then-INSERT 的竞态窗口（多实例并发启动也不会插入重复第1集），
    且不影响"软删集后 episode_number 可复用"的既有行为（故不加唯一约束）。
    """
    conn.execute(
        text(
            "INSERT INTO episodes (project_id, episode_number, title, status, style, "
            "aspect_ratio, voice_config, deleted, created_at, updated_at) "
            "SELECT p.id, 1, '第1集', p.status, p.style, p.aspect_ratio, p.voice_config, "
            "0, p.created_at, CURRENT_TIMESTAMP FROM projects p "
            "WHERE p.deleted = 0 AND NOT EXISTS "
            "(SELECT 1 FROM episodes e WHERE e.project_id = p.id)"
        )
    )
    ep_first = conn.execute(
        text("SELECT project_id, MIN(id) FROM episodes GROUP BY project_id")
    ).fetchall()
    mapping = {p: e for p, e in ep_first}
    for table in ("storyboards", "timelines"):
        for pid, eid in mapping.items():
            conn.execute(
                text(f"UPDATE `{table}` SET episode_id = :eid WHERE project_id = :pid AND episode_id IS NULL"),
                {"eid": eid, "pid": pid},
            )


def init_db() -> None:
    """启动时：库不存在则自动创建，建全部表，再执行增量列迁移与存量回填。"""
    from .. import models  # noqa: F401  导入以注册模型到 Base.metadata

    bootstrap = create_engine(settings.database_url_no_db)
    try:
        with bootstrap.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{settings.DB_NAME}` "
                    "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
    finally:
        bootstrap.dispose()
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        _ensure_columns(conn)
        _ensure_indexes(conn)
        _backfill_episodes(conn)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
