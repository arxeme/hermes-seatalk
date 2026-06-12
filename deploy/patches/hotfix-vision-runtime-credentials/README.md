# Hotfix: vision auto-detect 丢失 custom provider 运行时凭据

> **临时补丁，不随插件发布。** 上游修复合入后即应删除本目录。

## 症状

主模型配置为命名 custom provider（如 `custom:garena-gateway-anthropic`）时，
普通对话正常，但发送图片后 `vision_analyze` 始终失败：

```
WARNING agent.auxiliary_client: resolve_provider_client: custom/main requested but no endpoint credentials found
ERROR tools.vision_tools: Error analyzing image: No LLM provider configured for task=vision provider=auto. Run: hermes setup
```

## 根因

`turn_context.py` 每个 turn 调用 `set_runtime_main(agent.provider, ...)`，
其中 `agent.provider` 已被主 resolver 压平为裸 `"custom"`，端点凭据单独记录在
`_RUNTIME_MAIN_BASE_URL` / `_RUNTIME_MAIN_API_KEY` / `_RUNTIME_MAIN_API_MODE`。

- 非 vision 辅助任务走 `_resolve_auto()`，上游 PR #35259 已在那里桥接这些全局变量 → 正常
- vision 走 `resolve_vision_provider_client()` 的 auto 分支，调用
  `resolve_provider_client("custom", ...)` 时**没有**透传凭据 → 匿名 custom 分支
  找不到端点，整链返回 None

本补丁在 vision auto 分支镜像 `_resolve_auto` 的桥接逻辑（见 `fix.diff`）。

## 上游进度

| 项目 | 链接 | 状态 |
|---|---|---|
| Issue | <https://github.com/NousResearch/hermes-agent/issues/43251> | OPEN |
| PR | <https://github.com/NousResearch/hermes-agent/pull/43254> | OPEN |

**删除条件**：VM 上的 hermes-agent 升级到包含 PR #43254 的版本后，删除本目录，
并清理 VM 上的备份文件（见下）。

## 应用方法

### 一行远程安装（推荐）

以 hermes 用户在目标机器上执行（自动定位 venv python、打补丁、语法校验）。
**默认不重启 gateway**——便于嵌入全新安装/升级流程中间执行，全流程结束后再统一重启：

```bash
curl -fsSL https://raw.githubusercontent.com/arxeme/hermes-seatalk/main/deploy/patches/hotfix-vision-runtime-credentials/install.sh \
  | bash -s -- --hermes-root ~/.hermes/hermes-agent
```

> **注意**：本补丁只存在于 `main` 分支（仓库默认分支是 `publish`），URL 中的
> `main` 不能省略或改成默认分支。

常用变体：

```bash
# 打补丁后立即重启 gateway（单独应用本补丁时使用）
curl -fsSL .../install.sh | bash -s -- --hermes-root ~/.hermes/hermes-agent --restart

# 回滚（从备份恢复；同样默认不重启，加 --restart 立即重启）
curl -fsSL .../install.sh | bash -s -- --hermes-root ~/.hermes/hermes-agent --restore --restart
```

幂等：重复执行输出 `ALREADY_PATCHED`，不会重复修改。

### 手动应用

以 hermes 用户在目标 VM 上执行（首次应用自动备份；重复执行为 no-op）：

```bash
# 1. 上传 apply.py 到 VM（任意路径，如 /tmp）
# 2. 用 hermes-agent 的 venv python 执行
~/.hermes/hermes-agent/venv/bin/python /tmp/apply.py
# 输出 PATCHED_OK 后重启 gateway
systemctl --user restart hermes-gateway
```

非默认安装路径时把目标文件作为第一个参数传入：

```bash
~/.hermes/hermes-agent/venv/bin/python /tmp/apply.py /path/to/agent/auxiliary_client.py
```

`fix.diff` 是同一改动的标准 unified diff（来自 PR #43254 的 commit），
适用于对 hermes-agent 源码 checkout 执行 `git apply fix.diff` 的场景。
行号基于 v0.16.0 之后的 main（commit `7df3aa34b` 附近）；若 apply 失败优先用
`apply.py`（按代码块文本匹配，不依赖行号）。

## 验证

```bash
~/.hermes/hermes-agent/venv/bin/python - <<'EOF'
import os
from hermes_cli.env_loader import load_hermes_dotenv
load_hermes_dotenv(hermes_home=os.path.expanduser("~/.hermes"))
from agent.auxiliary_client import resolve_vision_provider_client, set_runtime_main
set_runtime_main("custom", "claude-opus-4-7",
                 base_url="https://<your-gateway>",
                 api_key=os.environ.get("<YOUR_KEY_ENV>", ""),
                 api_mode="anthropic_messages")
prov, client, model = resolve_vision_provider_client(provider="auto")
print("client:", type(client).__name__ if client else None)  # 期望 AnthropicAuxiliaryClient
EOF
```

端到端验证：在 Discord / SeaTalk 给 bot 发一张图片，确认能正常解析。

## 回滚

```bash
cp ~/.hermes/hermes-agent/agent/auxiliary_client.py.bak.hotfix-vision-runtime-credentials \
   ~/.hermes/hermes-agent/agent/auxiliary_client.py
systemctl --user restart hermes-gateway
```

## 已应用记录

| 日期 | 目标 | 操作人 | 备注 |
|---|---|---|---|
| 2026-06-09 | debug VM（hermes 用户） | Claude（会话内 hotfix，早期注释变体） | 已验证 gateway 重启后 SeaTalk + Discord 正常连接 |
| 2026-06-11 | debug VM（hermes 用户） | Claude | 回滚旧变体后改用本目录 apply.py 重新应用，待完整测试 |
