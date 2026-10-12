# 备件管理系统

Django 5.2 LTS / Python 3.12 / PostgreSQL 16。V1.0 数据模型、申请审批与 Excel 导入框架。

数据库设计见 [docs/DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md)，本次验证结果见
[DELIVERY_REPORT.md](DELIVERY_REPORT.md)。

## Docker 开发

```bash
cp .env.example .env
# 按需修改 .env 中的本地配置
docker compose up --build -d
docker compose exec web python manage.py createsuperuser
```

访问 http://localhost:8000/admin/；http://localhost:8000/health/ 会检查数据库连通性。
启动时自动执行迁移。此 Docker 环境使用 Django 开发服务器，仅用于开发。

```bash
docker compose exec -e DJANGO_SETTINGS_MODULE=config.settings.test web pytest
docker compose down
```

数据库保存在 `postgres_data` 卷；`docker compose down -v` 会删除数据库数据。

## 本地 Python 开发

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements/dev.txt
cp .env.example .env
set -a
source .env
set +a
docker compose up -d db
python manage.py migrate
python manage.py runserver
DJANGO_SETTINGS_MODULE=config.settings.test pytest
```

Django 本身不自动读取 `.env`，本地运行需先导出变量；Compose 自动注入配置。
`POSTGRES_HOST=localhost` 用于本地开发，容器内自动改为 `db`。
数据库测试会创建 `test_spare_parts`，测试账户需要创建数据库权限。

## 目录

```text
apps/accounts/      标准用户扩展、角色授权和操作审计
apps/inventory/     设备、备件、来源记录、Excel 导入
apps/requests/      月度申请、明细、修订和并发保护
apps/approvals/     审批状态机与审批记录
apps/reports/       生效版本汇总与 Excel 导出（无重复业务表）
apps/core/          候选源码 HTTP 适配层、表单及回归测试
config/settings/    基础、开发、测试配置
config/             URL、WSGI、ASGI 入口
requirements/       运行及测试依赖
tests/             pytest 测试
templates/         共享模板
static/            静态资源
docs/              项目文档
.github/workflows/  CI 流程
```

GitHub Actions 在推送到 `develop` / `main` 及提交 PR 时运行 Django 系统检查、
迁移一致性检查、数据库迁移、PostgreSQL 集成测试和 Docker 镜像构建。
正式部署前需添加生产设置、HTTPS、安全 Cookie 和生产 WSGI/ASGI 服务。

## 托管云环境构建

需要代理 CA 的云环境可先构建镜像，再通过 Compose 启动：

```bash
BUILDX_CONFIG=/tmp/spare-parts-buildx docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt \
  -t spare-parts-management-system-web .
docker compose up -d --no-build
```

CA 通过 BuildKit 临时挂载，不写入镜像。

## 账号与 Excel 导入

未提供默认账号。超级管理员可用 `createsuperuser` 创建；其它账号使用安全密码提示：

```bash
docker compose exec web python manage.py create_account alice --role requester --department 工程部
docker compose exec web python manage.py create_account reviewer --role reviewer --department 工程部
```

管理员上传 XLSX 后先预览异常与年月候选，确认主资料创建或逐工作表确认历史申请。
导入历史创建草稿，不自动确定月份、申请人、单位或生效版本。Web 导入入口为 `/imports/`。

单个文件也可通过 CLI 预览/导入（路径需在执行环境可访问）：

```bash
python manage.py import_excel /private/设备备件清单-z.xlsx --actor admin --catalog --preview
python manage.py import_excel /private/设备备件清单-z.xlsx --actor admin --catalog --apply-catalog
python manage.py import_excel /private/history.xlsx --actor admin --source-path 8月/history.xlsx --report /private/report.json
```

有完整原始任务包时可执行：

```bash
python manage.py import_sources --source-dir /private/source --actor admin --report /private/import_stats.json
SOURCE_DIR=/private/source ARCHIVE_DIR=/private/unpacked DJANGO_SETTINGS_MODULE=config.settings.test pytest
```

`import_sources` 保留原始 xlsx/7z 不变，在临时目录解压归档并登记来源；
历史申请仍需人工确认。原件存放于私有 `private_media/`，下载需要管理员权限。
禁止将 `source/`、`archive/`、原件或真实数据报告提交到公共仓库。
本次上传的验收候选源码不包含原始样本，相关两项真实样本测试会明确 SKIP。

## 备份与恢复

维护时停止 web 写入；数据库、`private_media/` 原件和 `templates/default21.xlsx`
必须一起备份，密钥配置单独安全保存。开发环境示例：

```bash
docker compose stop web
mkdir -p backups
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/database.dump
tar -czf backups/files.tar.gz private_media templates/default21.xlsx
# 备份完成后启动应用
docker compose start web
```

恢复应先在隔离环境验证，停止该环境 web 写入后用 `pg_restore --clean --if-exists`
恢复数据库，再还原原件和模板，执行 `migrate`、健康检查、原件哈希核对。
本阶段未声称完成目标服务器的恢复演练或局域网验收。
