# 备件管理系统

Django 5.2 LTS / Python 3.12 / PostgreSQL 16 开发骨架。

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
docker compose exec web pytest
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
pytest
```

Django 本身不自动读取 `.env`，本地运行需先导出变量；Compose 自动注入配置。
`POSTGRES_HOST=localhost` 用于本地开发，容器内自动改为 `db`。
数据库测试会创建 `test_spare_parts`，测试账户需要创建数据库权限。

## 目录

```text
apps/core/          公共应用与数据库健康检查
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
