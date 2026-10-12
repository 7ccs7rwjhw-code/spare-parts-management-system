# V1.0 数据库与导入框架阶段交付

## 本阶段结果

已导入用户提供的候选源码中的任务说明、开发约定和需求文档，先完成
[数据库设计](docs/DATABASE_DESIGN.md)，再将实现拆分为五个业务 App。
继续使用 Django 标准用户表及角色 Profile；新增设备、备件、别名、库存快照、
原文件与来源行、月度申请、21列明细、审批事件和操作审计模型。
四个有表的 App 初始迁移已在 PostgreSQL 实际执行；reports 是读模型服务，无迁移。
现有账号表保持兼容，模型检查与迁移一致性检查通过。

## 导入框架

- 主资料按表头解析，保留重复新码、无新码及 ASM 码候选，领用记录仅存证。
- 支持21/17/18列历史申请；18列双库存/未交需要人工指定映射。
- 5列费用及其他模板保存为待专用导入，不生成普通备件申请。
- 原文件SHA-256幂等、多个来源路径、工作表/行号/原值/表头/公式缓存可追溯。
- 预览与确认分开，年月/申请人/单位/生效版本由人确认，不自动推断业务事实。
- 数量保存 Decimal，原文与单位独立；错误不强转零，未匹配主资料行不丢弃。
- 创建/修改/审批/选版留事务审计；并发保存、上传、审批、修订与选版已有真实
  PostgreSQL 多线程测试。历史族人工合并同时分配唯一版本号并记录前后快照。
- SQL导入失败时清理事务外已写入的原件，避免孤立文件。

## 本次验证

```bash
docker compose up -d --no-build --force-recreate --wait web
docker compose exec -T -e DJANGO_SETTINGS_MODULE=config.settings.test web pytest -q -ra
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py makemigrations --check --dry-run
docker compose exec -T web python manage.py showmigrations accounts inventory requests approvals
curl --fail http://localhost:8000/health/
```

- 自动化：**84 PASS / 0 FAIL / 2 SKIP**，容器内执行。
- 2项跳过分别为原始备件清单和解压后的真实历史归档；当前上传包不包含这些原件。
- Django系统检查：无问题；迁移一致性：No changes detected。
- accounts/inventory/requests/approvals 的0001_initial全部已应用。
- Docker镜像构建通过，Compose db/web健康；健康接口返回 `{"status":"ok"}`。
- 登录接口HTTP 200；候选应用的权限和页面路由通过自动化回归。
- 原始执行输出：[pytest](docs/verification/pytest.txt)、
  [检查](docs/verification/checks.txt)、[迁移](docs/verification/migrations.txt)。

## 样本统计与未完成验收

合成主资料回归样本：5来源行、4候选物料、1领用存证；同新码两行独立保存，
无新码两行保留，二次确认不重复创建。历史样本验证覆盖21/17/18/5列、200m、
空白/占位/错误、同哈希多路径、不同内容版本及冲突月份。

**真实原始样本导入未执行**，本次不报告292主资料/194历史行等旧证据为实测结果。
提供只读原件后可用 import_sources 生成准确统计，并启用两项真实样本测试。
正式业务验收仍待原始数据、历史年月/单位/版本规则确认，以及目标服务器
局域网访问、多个浏览器和备份恢复演练。设备建档当前为模型/服务端基础设施，
未为其另建专用操作页面。本阶段没有宣称完成全部P0上线验收。

## 分支与 PR

本次开发提交保存在 develop。面向 main 的 PR 标题/正文已准备于 docs/PULL_REQUEST.md。
GitHub API请求返回Forbidden，CLI认证检查未通过；远程推送及PR创建结果将在
交付时如实说明，不将本地准备当成已创建的PR。
