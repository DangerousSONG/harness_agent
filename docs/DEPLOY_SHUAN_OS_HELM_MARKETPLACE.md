# 通过书安 OS Helm Marketplace API 部署

平台推荐用 Helm Marketplace API 创建应用市场条目，再走标准 release 流程，
而不是直接 `kubectl apply`。本仓库已经按平台「镜像打包标准」改造，
只需要打包 Chart → 上传 → 等导入完成 → dry-run → install 四步即可。

| 参数 | 值 |
|---|---|
| 平台基址 | `http://10.12.111.133:49164` |
| 上传 Chart | `POST /api/v1/helm-marketplace/custom-charts/upload` |
| 查询导入任务 | `GET  /api/v1/helm-marketplace/import-jobs/{JOB_ID}` |
| Dry-run | `POST /api/v1/helm-marketplace/releases/dry-run` |
| 安装 | `POST /api/v1/helm-marketplace/releases/install` |
| Release 列表 | `GET  /api/v1/helm-marketplace/releases` |

## 一、准备访问令牌

把平台给的 `accessToken` 放进 PowerShell 当前会话的环境变量。**不要写进
仓库文件，也不要写进任何脚本**——脚本只从环境变量读。

```powershell
$env:SHUAN_OS_TOKEN = "你的 accessToken"
```

> 这一行只对当前 PowerShell 会话有效。重开窗口需要重新设置。如果你想
> 持久化，可以用 `setx SHUAN_OS_TOKEN "<value>"` 写到用户级环境变量
> ——但**不要把 token 写到代码或公开文档里**。

## 二、打包 Chart

```powershell
.\scripts\package_chart.ps1
```

脚本会：

1. 验证 `chart\Chart.yaml` + `chart\values.yaml` 存在且 `name`/`version`
   非空
2. 检查本机有没有 `helm`，没有就清晰报错
3. 执行 `helm package chart -d artifacts`
4. 输出 `artifacts\harness-agent-0.1.0.tgz`

可选覆盖：

```powershell
.\scripts\package_chart.ps1 -ChartDir chart -OutDir artifacts
```

## 三、上传并部署

```powershell
.\scripts\deploy_to_shuan_os.ps1
```

脚本会按顺序执行：

1. 检查 `$env:SHUAN_OS_TOKEN` 是否存在；没有则直接报错退出
2. `POST /api/v1/helm-marketplace/custom-charts/upload` 上传 `.tgz`
3. 每 3 秒 `GET /api/v1/helm-marketplace/import-jobs/{id}` 轮询，
   最多等 300 秒，直到 `status=completed`（或 `failed` 即停）
4. 从 import 结果里提取 `repositoryName / repositoryUrl /
   repositoryType / chartName / version` 五个字段
5. 组装 release payload，先 `POST /releases/dry-run` 做一次预检
6. dry-run 通过后再 `POST /releases/install` 真正下发
7. `GET /releases` 拉一次列表，把每条 release 的 `name / namespace /
   status / endpoint` 打印出来

### 指定 values

如果想在部署时覆盖 chart 的默认 values（例如把镜像指向平台 Registry
里的真实 tag、注入 OPENAI_API_KEY 的 Secret 名），写一份本地 yaml 然后传给脚本：

```powershell
.\scripts\deploy_to_shuan_os.ps1 -ValuesYamlFile .\deploy-values.yaml
```

`deploy-values.yaml` 示例（**不要 commit 真实 key**）：

```yaml
image:
  repository: 10.12.111.133/users/a42b309e-77b1-41a1-b38b-5f951cfddc58/harness-agent
  tag: "v0.1.0"

extraEnv:
  - name: APP_ENV
    value: production
  - name: PORT
    value: "8000"

# 通过 Kubernetes Secret 注入密钥，永远不要把明文 key 写进 values。
extraEnvFromSecrets:
  - name: OPENAI_API_KEY
    valueFrom:
      secretKeyRef:
        name: harness-agent-secrets
        key: openai_api_key

persistence:
  enabled: true
  size: 10Gi
```

### 自定义 release 名 / 命名空间

```powershell
.\scripts\deploy_to_shuan_os.ps1 -ReleaseName harness-agent-staging `
                                  -Namespace staging
```

## 四、PowerShell 注意事项

- Windows PowerShell 里的 `curl` 是 `Invoke-WebRequest` 的别名，**不要
  在脚本里假设它是 cURL**。脚本统一用 `Invoke-RestMethod`。如果你要
  在终端里手敲调用平台 API 做调试，请用 `curl.exe` 显式区分。
- 脚本兼容 PowerShell 5.1 和 7+。`Invoke-RestMethod -Form` 是 PS7+
  才有的便捷写法；PS 5.1 走的是手工拼接 multipart body 的 fallback。
  两种路径都会自动生效，你不用管。

## 五、注意事项

- **Chart 包不是 Docker 镜像**。Helm chart 只描述「怎么部署一个镜像」。
- **镜像必须已经在集群可访问的 Registry 里**。如果 `values.yaml` 的
  `image.repository` 指向了集群拉不到的地方，dry-run 可能通过，但
  Pod 起来后会 `ImagePullBackOff`。先 `docker push`，再 deploy。
- **不要把 `SHUAN_OS_TOKEN` 写进 Git**。脚本只从环境变量读，配合
  `.gitignore` 排除掉本地凭证文件。
- **不要把 `.env` / API Key 打进 Chart 包**。`.dockerignore` 已经排除
  了 `.env`，Chart 包应该用 `extraEnv` / `extraEnvFromSecrets` 注入，
  和 Chart 本身一起发的只有公开配置。
- **`OPENAI_API_KEY` 等运行时变量走平台 Secret**。在平台 Secret 里建
  好 key，然后在 `values.yaml` 用 `extraEnvFromSecrets` 引用，不在
  values 文本里出现明文。

## 六、验证

```powershell
# 1) Chart 静态检查
helm lint .\chart

# 2) 本地渲染 Helm 模板，看看会生成什么 YAML
helm template harness-agent .\chart

# 3) 打包
.\scripts\package_chart.ps1

# 4) 设置 token（注意：仅当前会话有效）
$env:SHUAN_OS_TOKEN = "<accessToken>"

# 5) 上传 + dry-run + install
.\scripts\deploy_to_shuan_os.ps1
```

`helm lint` 应该是 0 lint warning；`helm template` 渲染出 Deployment +
Service（如果开了 persistence，还有 PVC）。如果这两步都正常，远端
四步走完之后 release 列表里应该能看到 `harness-agent`。

## 七、不要做的事

1. 不要在脚本里硬编码账号 / 密码 / accessToken。
2. 不要 commit accessToken（包括 `.env`、注释、commit message）。
3. 不要修改 `runtime/` / `web/server.py` 等业务逻辑——这次只是部署。
4. 不要删现有的 `Dockerfile` / `.a3s/` / `chart/`——脚本就靠它们工作。
5. 不要绕开 Helm Marketplace API 直接 `kubectl apply -f`——平台的 release
   状态、回滚、grading 都依赖 Marketplace 注册的 release。

## 八、和现有部署文档的关系

- `docs/DEPLOY_REGISTRY.md` —— 走 Docker Registry（`docker push`）路径，
  适合手工管理镜像 tag、回滚版本号。
- `docs/DEPLOY_CHECKLIST.md` —— 发版前的静态自检（三件套存在、端口一致、
  健康路径一致、Dockerfile 满足规范）。
- 本文 —— 通过 Helm Marketplace API 一键部署成 release，是平台推荐的
  完整应用上架方式。

三份文档不冲突：本文里上传的 `harness-agent-0.1.0.tgz` 描述的是
「怎么部署」，里面引用的 `image.repository` 仍然指向
`DEPLOY_REGISTRY.md` 里 push 上去的镜像。Marketplace 负责把它跑成
release；Registry 负责存镜像。
