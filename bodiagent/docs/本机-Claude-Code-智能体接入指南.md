# 本机 Claude Code 接入 BodiAgent 智能体部署指南

适用服务地址：`http://106.53.153.76:8000`  
适用场景：服务端已经部署完成，需要把本机的 Claude Code 作为智能体运行时接入 BodiAgent。  
更新时间：2026-05-27

---

## 1. 整体架构

本机需要同时具备 Claude Code CLI 和 `bodiagent-daemon`：

```text
Claude Code CLI（claude）
        ↑
bodiagent-daemon
        ↑ HTTP / WebSocket
BodiAgent 服务端：http://106.53.153.76:8000
```

服务端负责 Issue、Agent、任务队列和执行记录；真正执行 Claude Code 的是本机 daemon。

---

## 2. 本机基础依赖

### 2.1 Linux / Ubuntu / Debian

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git curl
python3 --version
```

建议 Python 版本为 3.12+。

### 2.2 macOS

```bash
brew install python git node
python3 --version
node -v
npm -v
```

---

## 3. 安装 Claude Code

### 3.1 安装 Node.js

如果本机已经有 Node.js，可先检查：

```bash
node -v
npm -v
```

如未安装：

```bash
# macOS
brew install node

# Ubuntu / Debian
sudo apt install -y nodejs npm
```

### 3.2 安装 Claude Code CLI

```bash
npm install -g @anthropic-ai/claude-code
```

验证：

```bash
which claude
claude --version
```

### 3.3 登录或配置 Claude Code

首次运行：

```bash
claude
```

按提示完成登录。

也可以通过环境变量配置 Anthropic API Key：

```bash
export ANTHROPIC_API_KEY="你的 Anthropic API Key"
```

建议写入 shell 配置：

```bash
echo 'export ANTHROPIC_API_KEY="你的 Anthropic API Key"' >> ~/.bashrc
source ~/.bashrc
```

验证 Claude Code 是否能非交互执行：

```bash
claude -p "hello" --output-format stream-json --verbose
```

如果能输出 JSON 流，说明 Claude Code 可被 daemon 调用。

---

## 4. 安装 bodiagent-daemon

在本机拉取代码：

```bash
git clone https://github.com/springking2005/multica.git
cd multica
git checkout feature/zh-cn
cd bodiagent
```

创建 Python 虚拟环境，并安装 **daemon CLI 独立包**：

```bash
python3 -m venv .venv
source .venv/bin/activate

python3 -m pip install --upgrade pip
python3 -m pip install -e ./daemon_cli
```

> 建议直接安装 `./daemon_cli` 独立包。当前 `bodiagent/` 根包也提供 `bodiagent-daemon` 入口用于兼容，但独立包更贴近 daemon 发布形态。

验证 daemon 命令：

```bash
bodiagent-daemon version
```

正常情况下会看到类似输出：

```text
bodiagent-daemon v0.1.0
Detected AI CLIs: claude
```

如果提示 `bodiagent-daemon: command not found`，通常是没有安装 `daemon_cli` 独立包或虚拟环境未激活，执行：

```bash
cd /path/to/multica/bodiagent
source .venv/bin/activate
python3 -m pip install -e ./daemon_cli
which bodiagent-daemon
bodiagent-daemon version
```

如果 `Detected AI CLIs` 里没有 `claude`，先检查：

```bash
which claude
echo "$PATH"
```

---

## 5. 在 Web 端准备用户 Token 和 Workspace ID

浏览器打开：

```text
http://106.53.153.76:8000
```

登录系统后，准备以下两个值：

1. **用户 API token**：JWT、`pat_...` 或 `cli_...`。推荐在 Web 端生成 `cli_...`。
2. **Workspace ID**：目标工作区 UUID。浏览器切换工作区下拉框里的 `option value` 就是 workspace id。

### 5.1 生成 CLI Token

进入：

```text
设置 → CLI Token
```

点击生成 Token，复制显示出来的 `cli_...` token。

> 注意：Token 只显示一次，请立即保存。`cli_...`/`pat_...` 是用户 API token，用于 daemon setup、列出工作区和授权绑定；`mdt_...` 是 daemon 运行时 token，不要拿 `mdt_...` 去做 setup 的用户认证。

### 5.2 获取 Workspace ID

如果页面能显示工作区 ID，直接复制。浏览器切换工作区选项里的 `option value` 是 workspace id。

也可以通过 API 获取：

```bash
curl -H "Authorization: Bearer <cli_or_pat_token>" \
  http://106.53.153.76:8000/api/workspaces/
```

从返回结果中找到目标工作区的 `id`。

---

## 6. 配置本机 daemon

推荐使用新的闭环 setup：CLI 用用户 token 调用服务端 `/api/daemons/setup/`，服务端会创建/复用 daemon、绑定到 workspace，并返回 `mdt_...` daemon 运行时 token；CLI 会自动保存该 `mdt_...`。

```bash
bodiagent-daemon setup \
  --server-url http://106.53.153.76:8000 \
  --token <cli_or_pat_token> \
  --workspace-id <workspace_uuid>
```

也可以不传 `--workspace-id`，如果该 token 只属于一个工作区，setup 会自动选择；如果属于多个工作区，会列出可选工作区并提示输入。

交互式方式：

```bash
bodiagent-daemon setup
```

按提示填写：

```text
Server URL: http://106.53.153.76:8000
User token (JWT, pat_..., or cli_...): <cli_or_pat_token>
Workspace ID (UUID): <目标 workspace UUID>
```

成功后会看到类似输出：

```text
Setup complete.
Daemon ID: ...
Machine ID: ...
Workspace ID: ...
Token saved: mdt_... (daemon runtime token)
```

配置会保存到：

```text
~/.bodiagent/config.json
```

也可以手动写入配置，但只建议在你已经有**已绑定该工作区**的 `mdt_...` token 时使用：

```bash
bodiagent-daemon setup \
  --server-url http://106.53.153.76:8000 \
  --daemon-token <mdt_daemon_token> \
  --workspace-id <workspace_uuid>
```

检查配置：

```bash
bodiagent-daemon status
```

确认输出中包含：

```text
Server URL: http://106.53.153.76:8000
Token: ***
Workspace ID: ...
Detected AI CLIs: claude
```

---

## 7. 启动 daemon

建议首次使用前台调试方式启动：

```bash
bodiagent-daemon start --foreground --verbose
```

正常情况下会看到 daemon 注册成功、WebSocket/轮询启动、任务执行器开始运行等日志。setup 阶段已经保存了 `mdt_...` daemon 运行时 token，启动阶段无需再手动复制 token。

---

## 8. 在平台创建 Claude 智能体

浏览器打开：

```text
http://106.53.153.76:8000
```

进入：

```text
智能体 → 创建智能体
```

建议字段如下：

| 字段 | 示例 |
|---|---|
| 名称 | 本机 Claude Code |
| Provider | `claude` |
| Daemon / Runtime | 选择刚才注册的本机 daemon |
| Model | 可留空，或填 Claude Code 支持的模型 |
| Instructions | 可选，例如“你是代码执行智能体，完成任务后用中文总结。” |

保存后，该 Agent 就会绑定到本机 daemon 和本机 Claude Code。

---

## 9. 端到端测试

### 9.1 创建测试 Issue

在看板新建 Issue：

```text
标题：测试 Claude Code 接入
描述：请检查当前目录并回复一句接入成功。
负责人：选择刚创建的 Claude 智能体
```

### 9.2 观察 daemon 日志

前台运行 daemon 时，应看到类似：

```text
Executing task ... provider=claude
```

实际会调用 Claude Code：

```bash
claude -p "<任务内容>" --output-format stream-json --verbose
```

### 9.3 回到页面检查

在 Issue 详情页确认：

- Agent 有执行消息；
- 任务状态进入完成或失败终态；
- 能看到 Claude 输出内容。

---

## 10. 配置为 systemd 后台服务（Linux）

如果需要 daemon 长期后台运行，可以配置 systemd。

创建服务文件：

```bash
sudo tee /etc/systemd/system/bodiagent-daemon.service > /dev/null <<EOF
[Unit]
Description=BodiAgent Daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/multica/bodiagent
Environment=PATH=$HOME/multica/bodiagent/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=ANTHROPIC_API_KEY=替换成你的APIKey
ExecStart=$HOME/multica/bodiagent/.venv/bin/bodiagent-daemon start --foreground
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bodiagent-daemon
```

查看状态：

```bash
systemctl status bodiagent-daemon
journalctl -u bodiagent-daemon -f
```

---

## 11. 常见问题排查

### 11.1 `Detected AI CLIs: none`

说明 daemon 找不到 `claude`。

检查：

```bash
which claude
echo "$PATH"
```

如果在 systemd 下运行，需要把 `claude` 所在目录加入服务文件的 `Environment=PATH=...`。

---

### 11.2 daemon 注册失败

检查服务端是否可访问：

```bash
curl -i http://106.53.153.76:8000/health/
```

检查配置：

```bash
bodiagent-daemon status
```

重点确认：

- `server_url` 是否是 `http://106.53.153.76:8000`；
- setup 要使用用户 token（JWT、`pat_...` 或 `cli_...`），不要把 `mdt_...` 填到 `--token`；
- 当前用户是否是该 workspace 的 owner/admin；
- daemon 是否已经通过 `/api/daemons/setup/` 或 `bodiagent-daemon setup` 绑定到目标 workspace；
- 网络是否能访问服务端。

---

### 11.3 Claude 执行失败

先本机直接测试 Claude Code：

```bash
claude -p "hello" --output-format stream-json --verbose
```

如果这里失败，先修复 Claude Code 登录或 `ANTHROPIC_API_KEY` 配置。

---

### 11.4 WebSocket 失败

如果后续加 Nginx / HTTPS，必须代理 WebSocket。

Nginx 示例：

```nginx
location /ws/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
}
```

---

## 12. 最小命令汇总

```bash
# 1. 安装 Claude Code
npm install -g @anthropic-ai/claude-code
claude --version
claude -p "hello" --output-format stream-json --verbose

# 2. 安装 daemon
git clone https://github.com/springking2005/multica.git
cd multica
git checkout feature/zh-cn
cd bodiagent
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install -e ./daemon_cli

# 3. 配置 daemon
bodiagent-daemon setup \
  --server-url http://106.53.153.76:8000 \
  --token <cli_or_pat_token> \
  --workspace-id <workspace uuid>

# 4. 启动
bodiagent-daemon start --foreground --verbose
```

完成后，在 Web 端创建 `provider=claude` 的智能体，并把 Issue 分配给它即可。
