# 部署到书安 OS 内置 Registry

打包 Harness Agent 镜像并上传到平台 Registry，然后在平台上用这个镜像创建应用。

> **本仓库已按平台「镜像打包标准」改造**，根目录包含完整三件套：
> `.a3s/manifest.acl` + `Dockerfile` + `chart/`（含 `Chart.yaml` /
> `values.yaml` / `templates/deployment.yaml`）。**推荐走方式 A
> 让平台自动构建**——直接 `docker tag/push` 一个 tar 镜像不一定能
> 创建完整可部署应用，因为部署还需要 Helm chart 和 manifest 一起
> 出现在仓库根。两种方式的差异见本文末「方式 A vs 方式 B」一节。

| 参数 | 值 |
|---|---|
| Registry 地址 | `10.12.111.133` |
| 命名空间 | `users/a42b309e-77b1-41a1-b38b-5f951cfddc58/` |
| 镜像全名格式 | `10.12.111.133/users/a42b309e-77b1-41a1-b38b-5f951cfddc58/harness-agent:<tag>` |
| 容器内端口 | `8000` |
| 健康检查路径 | `/api/health` |
| 启动命令 | `uvicorn web.main:app --host 0.0.0.0 --port 8000` |

## 一、本地构建与本地验证

```bash
# 1. 本地构建镜像
docker build -t harness-agent:latest .

# 2.（可选）docker-compose 起一份用本地 .env 验证一下
cp .env.example .env             # 然后填上 OPENAI_API_KEY 等
docker compose up --build

# 3. 浏览器访问验证
#    http://localhost:8000           （前端 + 后端同容器）
#    http://localhost:8000/api/skills （后端 API 入口）
```

`docker-compose.yml` 把 `.audit / .evolution / .reviews / .skills_memory / .skills_versions / .knowledge_bases / skills / tools` 这些目录绑定挂载到容器，重启后数据保留。

## 二、登录平台 Registry

```bash
docker login 10.12.111.133 -u a42b309e-77b1-41a1-b38b-5f951cfddc58 -p <访问令牌>
```

> **不要把访问令牌写进任何脚本或 commit 进仓库。** 一次性在终端里粘贴即可，登录后 Docker 自己会缓存凭证到 `~/.docker/config.json`。

## 三、打标签并推送

```bash
# 把本地镜像打成 Registry 全名 + 版本号
docker tag harness-agent:latest \
  10.12.111.133/users/a42b309e-77b1-41a1-b38b-5f951cfddc58/harness-agent:v0.1.0

# 推送到平台 Registry
docker push \
  10.12.111.133/users/a42b309e-77b1-41a1-b38b-5f951cfddc58/harness-agent:v0.1.0
```

每次发版换 tag（`v0.1.1` / `v0.2.0` / `2025-06-15` …）。不要长期只用 `latest`，否则平台上无法精确回滚。

## 四、拉取验证

在另一台机器（或清掉本地缓存后）拉一下确认确实上去了：

```bash
docker pull 10.12.111.133/users/a42b309e-77b1-41a1-b38b-5f951cfddc58/harness-agent:v0.1.0
```

## 五、在平台上创建应用

1. 镜像地址填 `10.12.111.133/users/a42b309e-77b1-41a1-b38b-5f951cfddc58/harness-agent:v0.1.0`
2. 容器端口 `8000`，平台对外暴露端口按需要选
3. 环境变量按 `.env.example` 列出的项配置（**API Key 必须在这里配，不要打进镜像**）
4. 挂载卷把下面几个目录挂到平台的持久化存储：
   - `/app/.audit`
   - `/app/.evolution`
   - `/app/.reviews`
   - `/app/.skills_memory`
   - `/app/.skills_versions`
   - `/app/.knowledge_bases`
   - `/app/skills`
   - `/app/tools`

## 六、Windows Docker Desktop 注意事项

如果 Registry 走 HTTP 而不是 HTTPS，Docker Desktop 默认会拒绝推送，需要把它加进 insecure-registries：

1. 打开 **Docker Desktop → Settings → Docker Engine**
2. 在那段 JSON 里加上下面这一项（**注意是合并字段，不要覆盖原有 JSON**）：

   ```json
   {
     "insecure-registries": ["10.12.111.133"]
   }
   ```

   如果已经有别的字段（比如 `registry-mirrors`），保留它们，只追加 `insecure-registries`。

3. 点 **Apply & Restart**，等 Docker Desktop 重启完。
4. 重新 `docker login` 一次即可。

Linux 用户在 `/etc/docker/daemon.json` 做同样的修改后 `sudo systemctl restart docker`。

## 七、生产安全要求

- **不要把 `.env` 打入镜像**。`.dockerignore` 已经显式排除了 `.env / .env.*`，但保留了 `.env.example` 作为文档。
- **不要把 `OPENAI_API_KEY` / Registry PAT 写进代码或 commit**。所有密钥都通过平台「环境变量」面板配置。
- **生产环境必须开启登录鉴权**。在平台环境变量里设置 `AUTH_USERNAME` 和 `AUTH_PASSWORD`；留空会禁用登录，仅适合本地调试。
- **高危接口必须鉴权才能调用**，包括但不限于：
  - `POST /api/reviews/{id}/approve` · `/apply` · `/reject`（审批落盘）
  - `POST /api/tools/{name}/run`（工具执行）
  - `POST /api/tools/create` · `POST /api/skills/propose`（资产创建）
  - `DELETE /api/skills/{name}` · `DELETE /api/tools/{name}`（永久删除）
  - `POST /api/skills/{name}/archive` · `/restore`（归档 / 恢复）
  - `POST /api/workspace/files/propose-write`（文件改动审查）
  - `POST /api/workspace/commands/run`（命令执行）
- **运行态目录走平台持久化存储**：上面列出的 8 个挂载点必须用平台提供的卷或 PVC，不能依赖容器层内的临时盘——容器重建会全部丢失。
- **不要 `docker push` 公共 `latest`**：发版固定 tag（`v0.1.0` / `2025-06-15`），平台上才能精确回滚。

## 八、前端是怎么访问的

镜像里前端用 Vite 构建产物放在 `/app/web/ui/dist`，`web/main.py` 启动时把这个目录挂到 FastAPI 上：

- `/assets/*` → 直接返回 `dist/assets/*` 的静态资源
- `/api/*` → 后端业务接口
- 其他路径 → 命中具体文件则返回该文件（`/favicon.ico` 等），否则返回 `index.html`（SPA 路由 fallback）

所以**不需要单独的 Nginx**。如果未来要把前端和后端分开部署（CDN + API），把 `web/ui/dist` 单独发，后端只跑 API 即可。

## 九、本地一键验证清单

执行下面这一组命令，如果都通过，说明镜像可以直接推到平台：

```bash
# 1. 构建
docker build -t harness-agent:latest .

# 2. 启动（无 GPU / 无 OPENAI_API_KEY 也应该能起来）
docker run --rm -d --name harness-agent-test -p 8000:8000 \
  -e APP_ENV=production harness-agent:latest

# 3. 等几秒让 uvicorn 起来，访问 API
sleep 5
curl -fsS http://localhost:8000/api/skills | head -c 200 ; echo

# 4. 访问前端（应返回 HTML）
curl -fsS http://localhost:8000/ | head -c 200 ; echo

# 5. 清理
docker stop harness-agent-test
```

如果第 3 步返回 JSON、第 4 步返回 HTML（带 `<div id="root">`），就可以推 Registry 了。

## 十、方式 A vs 方式 B

### 方式 A：平台推荐（**首选**）

把整个仓库（含三件套）上传到平台，由平台读取：

1. `.a3s/manifest.acl` —— 资产分类、版本、健康检查契约
2. `Dockerfile` —— 镜像构建输入
3. `chart/values.yaml` —— 必须包含 `image.repository` + `image.tag`

平台会**在集群内构建镜像**并自动推送到内置 Registry，然后用
`chart/templates/` 渲染 Deployment + Service 部署上线。这种方式
的好处：

- 平台自动给镜像加上对应版本号 / 命名空间，不需要在本地 `docker tag/push`
- Helm 渲染过程平台可见，出问题时平台日志直接定位
- 升级（patch 版本号）会自动触发滚动更新

### 方式 B：本地手动镜像 tar

仅当**调试 / 镜像管理**用途时考虑：

```bash
docker save \
  10.12.111.133/users/a42b309e-77b1-41a1-b38b-5f951cfddc58/harness-agent:v0.1.0 \
  > harness-agent-v0.1.0.tar
```

把这个 tar 上传到 Registry 后可以拉取，但**不能直接创建一个完整
可部署应用**——平台还需要看到 `.a3s/manifest.acl` 和 `chart/` 才能
渲染 Helm 工作负载。所以方式 B 仅适合：

- 已经在用方式 A 部署应用，单独想把某个镜像 tar 同步到 Registry
- 镜像管理 / 备份场景

**不要只上传 `harness-agent.tar` 作为完整应用**——平台不会拿它跑 Helm 模板。

## 十一、自检清单

详见 `docs/DEPLOY_CHECKLIST.md`。每次发版前对照该文件确认三处端口 /
健康检查路径一致，再 `helm template harness-agent ./chart` 验证模板
能渲染。
