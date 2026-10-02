# 部署指南

> 适用场景：本机自托管 + 临时分享给朋友。硬件要求见 `CLAUDE.md`（RTX 4060 8GB）。

## 前置准备

1. 已安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/) 并保持运行。
2. 已安装并启动 Ollama，且嵌入模型已下载：

   ```bash
   ollama serve                 # 保持后台运行
   ollama list                  # 确认存在 dengcao/Qwen3-Embedding-8B:Q5_K_M
   ```

3. 项目根目录已配置 `.env`（从 `.env.example` 复制并填入真实值），
   以及 `.streamlit/secrets.toml`（Streamlit 登录密码）：

   ```bash
   cp .env.example .env
   # 编辑 .env：填入 DEEPSEEK_API_KEY / EXERCISEAPI_KEY / USDA_API_KEY / API_KEY
   # 编辑 .streamlit/secrets.toml：APP_PASSWORD = "你的访问密码"
   ```

   容器入口会在启动时探测 Ollama（默认等待约 60 秒），不可达则拒绝启动。

---

## 本机运行

1. 启动 Ollama（如未在后台运行）：

   ```bash
   ollama serve
   ```

2. 构建镜像：

   ```bash
   docker build -t fitness-agent:v0.1.0 .
   ```

3. 启动服务（api + ui）：

   ```bash
   docker compose up -d
   ```

4. 访问页面：<http://localhost:8501>

   - 首次进入需输入 `.streamlit/secrets.toml` 中配置的 `APP_PASSWORD`。
   - 查看状态 / 日志：

     ```bash
     docker compose ps
     docker compose logs -f
     ```

   - 停止服务：

     ```bash
     docker compose down
     ```

> SQLite 与 Chroma 数据通过 `./data` 目录持久化挂载，容器重建不丢数据。

---

## 临时公网访问（Cloudflare Quick Tunnel）

适合临时把本地应用发给朋友试用，无需注册账号、无需公网 IP。

**推荐：用一键菜单。** 双击 `start.bat`（或运行 `scripts/manage.ps1`），先按当前模式
（dev/prod）启动服务，再选择 **[7] 公网隧道（Cloudflare）→ [1] 启动隧道**。
脚本自动按模式选择转发目标（dev → `http://localhost:5173`，prod → `http://localhost:8000`），
PID 记录在 `data/run/cloudflared.pid`，日志在 `logs/cloudflared_quick.log`；
子菜单 [3] 可随时查看公网地址，[2] 停止隧道。

也可手动操作：

1. 安装 cloudflared：

   ```powershell
   winget install --id Cloudflare.cloudflared
   ```

2. 确认本机服务已启动，然后启动隧道（目标按模式选择 5173 / 8000）：

   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```

3. 终端会输出一个 `https://<随机词>.trycloudflare.com` 地址，把它发给朋友即可。

4. 用完停止隧道，公网地址立即失效。

> **Clash 代理下隧道反复掉线（错误 1033 / QUIC timeout）**：默认 QUIC 走 UDP，
> 在 Clash 等代理下容易出现 `failed to accept QUIC stream: no recent network activity`
> 并无限重连。此时强制走 TCP 的 HTTP/2，必要时锁定 IPv4（菜单已默认带上这两个参数）：
>
> ```bash
> cloudflared tunnel --url http://localhost:8000 --protocol http2 --edge-ip-version 4
> ```
>
> **若边缘注册报 `argotunnel.com: no such host`**：是 cloudflared 内置 DoH 被代理拦截，
> 在 Clash 中开启 TUN 模式（或放行 cloudflared 的 DoH/边缘 IP）即可。
>
> 先 `taskkill /F /IM cloudflared.exe` 清掉旧实例再启动，避免多个隧道并存。

---

## 注意事项

- **免费版地址每次重启都会变**：Quick Tunnel 的 `trycloudflare.com` 子域名是随机的，关闭后再开会拿到新地址。
- **需要长期访问再考虑注册域名 + 命名隧道**（`cloudflared tunnel create` + DNS 路由），可获得固定地址与开机自启。
- **FastAPI 不暴露公网，仅容器内部调用**：隧道只指向 Streamlit 的 8501 端口；不要对 8000 端口开隧道。
  （`docker-compose.yml` 当前把 8000 映射到了本机，仅方便本机调试；生产环境可删除该 `ports` 映射，
  ui 到 api 走容器网络 `http://api:8000`，并由 `X-API-Key` 中间件保护。）
- 隧道开启期间任何拿到地址的人都能尝试登录，**务必设置强 `APP_PASSWORD`**；分享范围可控、用完即关。
- Ollama 跑在宿主机上，容器通过 `host.docker.internal:11434` 访问；换机器部署时需相应调整 `OLLAMA_BASE_URL`。
