# CRM V2 部署文档

## 环境要求

- Python 3.10+
- SQLite 3.35+
- 512MB 内存（推荐 1GB）

## 部署步骤

### 1. 准备工作

```bash
# 进入项目目录
cd /opt/data/crm

# 创建必要的目录
mkdir -p /opt/data/crm/uploads /opt/data/crm/backups
```

### 2. 构建 Docker 镜像

```bash
# 构建镜像
docker build -t crm-v2 .

# 或者使用 docker-compose
docker-compose build
```

### 3. 启动服务

```bash
# 使用 docker-compose 启动
docker-compose up -d

# 或者直接运行
docker run -d \
  --name crm-v2 \
  -p 8010:8010 \
  -v /opt/data/crm/crm.db:/opt/data/crm/crm.db \
  -v /opt/data/crm/backups:/opt/data/crm/backups \
  -v /opt/data/crm/uploads:/opt/data/crm/uploads \
  -e ADMIN_USERNAME=chen \
  -e ADMIN_PASSWORD=your_secure_password \
  crm-v2
```

### 4. 数据库迁移

首次启动或升级时会自动执行迁移：

```bash
# 查看迁移状态
docker exec crm-v2 python3 -m app.migrations --db /opt/data/crm/crm.db

# 手动执行迁移（如果需要）
docker exec crm-v2 python3 -m app.migrations
```

### 5. 验证部署

```bash
# 检查服务状态
curl http://localhost:8010/health

# 检查 API 端点
curl http://localhost:8010/api/crm/health
```

## 配置说明

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| CRM_DB | 数据库文件路径 | `/opt/data/crm/crm.db` |
| CRM_UPLOADS | 上传文件目录 | `/opt/data/crm/uploads` |
| ADMIN_USERNAME | 管理员用户名 | `chen` |
| ADMIN_PASSWORD | 管理员密码 | `test123` |

### 目录结构

```
/opt/data/crm/
├── crm.db              # 主数据库文件
├── backups/            # 备份目录
└── uploads/           # 上传文件目录
```

## 回滚说明

如需回滚到 V1 版本：

```bash
# 停止服务
docker-compose down

# 恢复备份（如果有）
cp /opt/data/crm/backups/crm-pre-v2-*.db /opt/data/crm/crm.db

# 切换到 V1 代码
git checkout v1

# 重启服务
docker-compose up -d
```

## 常见问题

### 1. 数据库权限问题

```bash
# 确保目录权限正确
sudo chown -R $(whoami) /opt/data/crm
sudo chmod -R 755 /opt/data/crm
```

### 2. 端口占用

```bash
# 检查端口占用
lsof -i :8010

# 杀死占用进程
kill -9 $(lsof -t -i :8010)
```

### 3. 迁移失败

```bash
# 查看迁移日志
docker logs crm-v2

# 手动清理并重试
docker exec crm-v2 rm -f /opt/data/crm/crm.db
docker exec crm-v2 python3 -m app.migrations
```

## 监控指标

- `/health` - 健康检查
- 数据库大小监控
- 上传文件目录空间监控