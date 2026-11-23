-- 002：refresh 令牌轮换链 + 任务幂等键改为项目内唯一
--
-- 说明：后端启动时 init_db() 会通过 information_schema 自动补齐下列结构
-- （见 app/core/db.py 的 _ADD_COLUMN_MIGRATIONS / _ensure_indexes），
-- 本文件用于手工迁移或审计留档。

-- 1) refresh 令牌轮换链
ALTER TABLE `refresh_tokens`
    ADD COLUMN `family_id` VARCHAR(64) NULL;

CREATE INDEX `ix_refresh_tokens_family_id`
    ON `refresh_tokens` (`family_id`);

-- 2) 任务幂等键：全局唯一 -> 项目内唯一
--    先确认没有重复数据，否则下面的唯一索引会创建失败：
--    SELECT project_id, idempotency_key, COUNT(*) FROM gen_tasks
--     WHERE idempotency_key IS NOT NULL
--     GROUP BY project_id, idempotency_key HAVING COUNT(*) > 1;
ALTER TABLE `gen_tasks` DROP INDEX `idempotency_key`;

ALTER TABLE `gen_tasks`
    ADD UNIQUE INDEX `uq_gen_tasks_project_idem` (`project_id`, `idempotency_key`);