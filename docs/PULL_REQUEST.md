# 备件申请 V1.0：数据库模型、五个 App 与可追溯 Excel 导入

现有仓库仅有 Django/PostgreSQL 骨架。本次导入用户提供的任务说明与需求文档，
完成数据库设计，将候选源码后端拆分到 accounts、inventory、requests、approvals、
reports，新增实际执行过的模型迁移、导入框架、申请状态机和操作审计。

导入保留原件哈希、来源路径、表头、行号、原数量和异常；重复字节不会新增申请。
支持主资料及21/17/18列历史申请，5列费用表仅存证。月份与版本须人工确认，
数量和单位独立保存，已批准版本通过修订维护，生效汇总按单位分组。

验证：Docker构建和Compose健康检查通过；PostgreSQL容器内pytest为84通过、
2跳过；Django检查与迁移一致性通过。跳过项依赖未随源码包提供的原始备件清单
和历史归档。正式局域网及备份恢复验收尚未完成。

详见 docs/DATABASE_DESIGN.md、DELIVERY_REPORT.md 和 docs/verification/。
