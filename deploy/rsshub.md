# RSSHub 部署到 Railway — 完整指南

> 本文档说明如何将 RSSHub 实例部署到 Railway 云平台，用于抓取微信公众号等内容，
> 供 `kol-intel` 的 `src/fetcher.py` 消费。

---

## 步骤一：本地验证

在部署到云端之前，先确认本地 Docker 环境可以正常运行 RSSHub。

```bash
# 启动 RSSHub 容器（后台运行，映射端口 1200）
docker run -d -p 1200:1200 diygod/rsshub
```

验证微信公众号路由是否返回 XML：

```bash
curl http://localhost:1200/wechat/mp/pmcaff/baidu_xinzhi
```

**预期结果**：返回 XML 格式的 RSS/Atom feed，包含百度新知的文章列表。
若返回 XML 则本地环境正常，可继续下一步。

---

## 步骤二：部署到 Railway

1. 访问 [railway.app](https://railway.app)，登录或注册账号。
2. 点击 **New Project**。
3. 选择 **Deploy from Docker Image**。
4. 在镜像名称输入框中填入：

   ```
   diygod/rsshub
   ```

5. 点击 **Deploy** 等待部署完成（通常需要 1–3 分钟）。
6. 进入项目页面，点击 **Settings → Networking**：
   - 在 **Expose Port** 中输入 `1200`，点击保存。
7. Railway 会自动生成一个公网 URL，格式如：

   ```
   https://rsshub-production-xxxx.up.railway.app
   ```

   复制该 URL，后续步骤中使用。

---

## 步骤三：配置环境变量

在 Railway 项目页面，点击 **Variables** 面板，添加以下变量：

| 变量名 | 值 | 说明 |
|---|---|---|
| `CACHE_TYPE` | `memory` | 使用内存缓存，减少重复请求 |
| `CACHE_EXPIRE` | `300` | 缓存有效期 300 秒（5 分钟） |

添加完成后 Railway 会自动重启服务，变量即时生效。

---

## 步骤四：更新本地 .env

将 `.env` 文件中的 `RSSHUB_BASE_URL` 替换为你的 Railway 公网 URL：

```dotenv
# 替换为步骤二中复制的实际 URL
RSSHUB_BASE_URL=https://rsshub-production-xxxx.up.railway.app
```

---

## 步骤五：验证 WeChat 路由

使用 `config/seeds.json` 中配置的 `wechat_id` 逐一测试，确认公网 RSSHub 可以正常返回内容：

```bash
# 示例：百度新知
curl https://rsshub-production-xxxx.up.railway.app/wechat/mp/pmcaff/baidu_xinzhi

# 示例：360 / 周鸿祎
curl https://rsshub-production-xxxx.up.railway.app/wechat/mp/pmcaff/qihu360

# 示例：百川 AI / 王小川
curl https://rsshub-production-xxxx.up.railway.app/wechat/mp/pmcaff/baichuanAI
```

**预期结果**：每条命令均返回包含文章条目的 XML feed。
若返回正常则说明 `RSSHUB_BASE_URL` 配置成功，`src/fetcher.py` 的 WeChat 抓取功能可正常工作。

---
---

# RSSHub Deployment to Railway — Complete Guide

> This document explains how to deploy a RSSHub instance to Railway cloud platform
> for scraping WeChat public accounts and other content consumed by `kol-intel`'s `src/fetcher.py`.

---

## Step 1: Local Validation

Before deploying to the cloud, verify that RSSHub runs correctly in your local Docker environment.

```bash
# Start RSSHub container (detached mode, map port 1200)
docker run -d -p 1200:1200 diygod/rsshub
```

Verify that the WeChat route returns XML:

```bash
curl http://localhost:1200/wechat/mp/pmcaff/baidu_xinzhi
```

**Expected result**: An RSS/Atom feed in XML format containing article entries from Baidu Xinzhi.
If XML is returned, your local environment is working — proceed to the next step.

---

## Step 2: Deploy to Railway

1. Visit [railway.app](https://railway.app) and log in or sign up.
2. Click **New Project**.
3. Select **Deploy from Docker Image**.
4. Enter the following image name:

   ```
   diygod/rsshub
   ```

5. Click **Deploy** and wait for the deployment to complete (usually 1–3 minutes).
6. Navigate to the project page and click **Settings → Networking**:
   - Under **Expose Port**, enter `1200` and save.
7. Railway will automatically generate a public URL in the format:

   ```
   https://rsshub-production-xxxx.up.railway.app
   ```

   Copy this URL — you will use it in the following steps.

---

## Step 3: Configure Environment Variables

In the Railway project page, open the **Variables** panel and add the following:

| Variable | Value | Description |
|---|---|---|
| `CACHE_TYPE` | `memory` | Use in-memory cache to reduce redundant requests |
| `CACHE_EXPIRE` | `300` | Cache TTL of 300 seconds (5 minutes) |

After adding the variables, Railway will automatically restart the service and apply them immediately.

---

## Step 4: Update Local .env

Replace the `RSSHUB_BASE_URL` value in your `.env` file with the Railway public URL copied in Step 2:

```dotenv
# Replace with your actual URL from Step 2
RSSHUB_BASE_URL=https://rsshub-production-xxxx.up.railway.app
```

---

## Step 5: Verify WeChat Routes

Test each `wechat_id` configured in `config/seeds.json` to confirm that the public RSSHub instance returns content correctly:

```bash
# Example: Baidu Xinzhi (Robin Li)
curl https://rsshub-production-xxxx.up.railway.app/wechat/mp/pmcaff/baidu_xinzhi

# Example: Qihu 360 (Zhou Hongyi)
curl https://rsshub-production-xxxx.up.railway.app/wechat/mp/pmcaff/qihu360

# Example: Baichuan AI (Wang Xiaochuan)
curl https://rsshub-production-xxxx.up.railway.app/wechat/mp/pmcaff/baichuanAI
```

**Expected result**: Each command returns an XML feed containing article entries.
If all routes return valid XML, your `RSSHUB_BASE_URL` is correctly configured and
`src/fetcher.py`'s WeChat fetch functionality is ready to use.

---
---

## GitHub Secrets 配置清单 / GitHub Secrets Checklist

在 GitHub 仓库的 **Settings → Secrets and variables → Actions → New repository secret**
中添加以下四个变量，缺少任意一个将导致对应功能静默跳过或 workflow 报错。

In your GitHub repository, go to **Settings → Secrets and variables → Actions → New repository secret**
and add the following four secrets. Missing any one will cause the corresponding feature
to be silently skipped or the workflow to fail.

| Secret 名称 | 说明（中文） | Description (English) |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API 密钥，用于 P1–P5 全部分析阶段。缺少时 pipeline 直接报错退出。 | Claude API key, required for all five analysis phases (P1–P5). Workflow fails immediately if missing. |
| `RSSHUB_BASE_URL` | 自托管 RSSHub 的公网地址，格式如 `https://rsshub-xxx.railway.app`。缺少时微信公众号抓取全部跳过。 | Public URL of your self-hosted RSSHub instance (e.g. `https://rsshub-xxx.railway.app`). WeChat fetching is skipped if missing. |
| `SENDGRID_API_KEY` | SendGrid 邮件发送 API Key。缺少时邮件推送跳过，pipeline 仍正常完成并保存输出文件。 | SendGrid API key for email delivery. If missing, email is skipped but the pipeline completes and saves output files normally. |
| `DELIVERY_EMAIL` | 简报收件邮箱地址，如 `you@example.com`。缺少时邮件推送跳过。 | Recipient email address for the daily brief, e.g. `you@example.com`. Email is skipped if missing. |

> **提示 / Tip**：`GITHUB_TOKEN` 由 Actions 自动提供，无需手动配置。
> `GITHUB_TOKEN` is provided automatically by GitHub Actions — no manual setup required.
