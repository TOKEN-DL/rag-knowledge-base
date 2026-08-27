-- 在容器首次启动时由 /docker-entrypoint-initdb.d 自动执行
-- 仅当数据卷为空（首次初始化）时才会跑；已存在的库不会重跑
-- pgvector/pgvector 镜像内置了 vector 扩展，这里只需启用即可

-- 启用 pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- 把 public schema 的使用权限显式授予应用账号
-- （PG15+ 默认 PUBLIC 在 public 上的 CREATE 权限被收回）
GRANT USAGE ON SCHEMA public TO rag;
GRANT CREATE ON SCHEMA public TO rag;
