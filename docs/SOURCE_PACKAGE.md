# 候选源码导入记录

上传文件：备件申请管理系统_V1.0_验收候选源码.zip

SHA-256：`f6727dee59364484d5e0e893ed422f82cc7bcdb02c7001e23eedf1dbf296cca9`

- 原样导入 CODEX_TASK.md 和 AGENTS.md。
- task_docs/*.md 导入 docs/，保留原需求与数据契约内容。
- 审查并复用候选模型、导入器、状态机、HTTP 适配层和回归测试；业务模型与
  服务按 accounts / inventory / requests / approvals / reports 拆分。
- 候选 core/migrations 未复制，按本仓库模型生成并实际执行新的 App 迁移。
- 复用经过空白内容验证的 default21.xlsx 模板和本地静态样式。
- 未导入候选 evidence/、旧交付/验收报告、旧部署脚本，避免混淆执行证据。
- 包中不包含原始 source/、历史归档或 analysis/*.json。SOURCE_ANALYSIS.md
  的原始数量属于包内历史分析记录，本次未据此宣称真实样本导入通过。

本次执行证据位于 docs/verification/，结果见 DELIVERY_REPORT.md。
