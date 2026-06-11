# 部署自检清单

每次准备把 Harness Agent 推到平台之前，对照下面这张表逐项确认。
出现任何 ✗ 就先修，再发版。

## 一、平台三件套必须齐全

| 项 | 路径 | 检查 |
|---|---|---|
| ☐ | `.a3s/manifest.acl` | 文件存在 |
| ☐ | `Dockerfile` | 文件存在 |
| ☐ | `chart/Chart.yaml` | 文件存在 |
| ☐ | `chart/values.yaml` | 文件存在 |
| ☐ | `chart/templates/deployment.yaml` | 文件存在 |
| ☐ | `chart/templates/service.yaml` | 文件存在 |

快速验证：

```bash
ls .a3s/manifest.acl Dockerfile chart/Chart.yaml chart/values.yaml \
   chart/templates/deployment.yaml chart/templates/service.yaml
```

六个文件都列出来即通过。

## 二、`chart/values.yaml` 必须包含 image 字段

平台触发构建的硬性条件——少了任何一个，平台拒绝构建。

| 项 | 字段 | 检查 |
|---|---|---|
| ☐ | `image.repository` | 非空字符串，例如 `a3s/harness-agent` |
| ☐ | `image.tag` | 非空字符串，例如 `"0.1.0"`（带引号，避免被 YAML 解析成数字） |

快速验证：

```bash
grep -E "^\s*(repository|tag):" chart/values.yaml
```

## 三、三处端口必须一致

下面三处端口值必须**全部等于 8000**（要改的话三处一起改）：

| 来源 | 字段 | 当前值 |
|---|---|---|
| ☐ | `Dockerfile` `ENV PORT` / `EXPOSE` | `8000` |
| ☐ | `.a3s/manifest.acl` `contract.port` | `8000` |
| ☐ | `chart/values.yaml` `service.targetPort` | `8000` |

快速验证：

```bash
grep -E "^(ENV PORT|EXPOSE)" Dockerfile
grep "port:" .a3s/manifest.acl | head
grep "targetPort:" chart/values.yaml
```

## 四、三处健康检查路径必须一致

下面三处路径必须**全部等于 `/api/health`**：

| 来源 | 字段 | 当前值 |
|---|---|---|
| ☐ | `Dockerfile` `HEALTHCHECK` curl 路径 | `/api/health` |
| ☐ | `.a3s/manifest.acl` `contract.health` | `/api/health` |
| ☐ | `chart/values.yaml` `probes.liveness.path` 和 `probes.readiness.path` | `/api/health` |

快速验证：

```bash
grep "HEALTHCHECK" Dockerfile
grep "health:" .a3s/manifest.acl
grep "path:" chart/values.yaml | head
```

健康检查路径本身由 `web/main.py` 注册（`GET /api/health` 返回
`{"status": "ok"}`）——不在 `web/server.py` 里，所以业务逻辑没动。

## 五、Dockerfile 满足最小工程规范

| 项 | 检查 |
|---|---|
| ☐ | 多阶段构建（`FROM node:* AS ui-builder` + `FROM python:* AS runtime`） |
| ☐ | 非 root 用户运行（`USER app` 且 `useradd --uid 10001`） |
| ☐ | `ENV PORT=8000` |
| ☐ | `EXPOSE 8000` |
| ☐ | `HEALTHCHECK` 指向 `/api/health` |
| ☐ | `CMD` 走 `uvicorn web.main:app --host 0.0.0.0 --port ${PORT:-8000}` |
| ☐ | `.dockerignore` 把 `.env / .git / .venv / node_modules / 运行态目录` 全部排除 |

快速验证：

```bash
grep -E "^(FROM|USER|ENV|EXPOSE|HEALTHCHECK|CMD)" Dockerfile
```

## 六、Helm chart 能渲染

如果本地装了 `helm`：

```bash
helm template harness-agent ./chart > /tmp/rendered.yaml
echo "ok ($(wc -l < /tmp/rendered.yaml) lines rendered)"
```

期望输出：`ok (NN lines rendered)`，没有 `Error: ...`。

如果没装 helm，可以用 docker 临时跑一个：

```bash
docker run --rm -v "$PWD:/work" -w /work alpine/helm:3.16 \
  template harness-agent ./chart > /tmp/rendered.yaml
```

## 七、镜像构建 + 启动 smoke test

```bash
# 1) 构建
docker build -t harness-agent:latest .

# 2) 启动
docker run --rm -d --name harness-agent-smoke -p 8000:8000 \
  -e APP_ENV=production harness-agent:latest

# 3) 等几秒，命中健康检查
sleep 5
curl -fsS http://localhost:8000/api/health
#   → {"status":"ok"}

# 4) 命中静态前端
curl -fsS http://localhost:8000/ | head -c 200
#   → 应该看到 <div id="root">…

# 5) 命中一个真实 API
curl -fsS http://localhost:8000/api/skills | head -c 200
#   → JSON

# 6) 清理
docker stop harness-agent-smoke
```

四步都通过即可以推 Registry。任何一步失败先排查，**不要带病发版**。

## 八、生产安全

| 项 | 检查 |
|---|---|
| ☐ | `.env` 不在镜像里（`.dockerignore` 排除） |
| ☐ | 任何 commit 都没有真实 `OPENAI_API_KEY` / Registry PAT |
| ☐ | 生产环境的 `AUTH_USERNAME` / `AUTH_PASSWORD` 通过平台环境变量注入 |
| ☐ | 高危接口在生产环境鉴权（参见 `DEPLOY_REGISTRY.md` 第七节） |
| ☐ | 运行态目录用平台持久化存储（`persistence.enabled=true` 或对应的 PVC） |
| ☐ | 镜像 tag 是确定版本号（`v0.1.0`），不是 `latest` |

## 九、最终检查脚本

下面这个一键脚本会跑前六项的快速验证：

```bash
#!/usr/bin/env bash
set -e
echo "三件套存在性…"
test -f .a3s/manifest.acl
test -f Dockerfile
test -f chart/Chart.yaml
test -f chart/values.yaml
test -f chart/templates/deployment.yaml
test -f chart/templates/service.yaml
echo "✓"

echo "values.yaml image 字段…"
grep -q "^  repository:" chart/values.yaml
grep -q "^  tag:"        chart/values.yaml
echo "✓"

echo "端口三处一致…"
grep -qE "PORT=8000"              Dockerfile  # works for both ``ENV PORT=8000`` and multi-line ENV blocks
grep -q "EXPOSE 8000"             Dockerfile
grep -q "port: 8000"              .a3s/manifest.acl
grep -q "targetPort: 8000"        chart/values.yaml
echo "✓"

echo "健康检查路径三处一致…"
grep -q "/api/health"             Dockerfile
grep -q "health: /api/health"     .a3s/manifest.acl
grep -q "path: /api/health"       chart/values.yaml
echo "✓"

echo "所有静态检查通过。"
```
