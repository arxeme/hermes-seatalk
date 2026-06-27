---
标题: Hermes SeaTalk Platform Plugin 技术设计 · 变更说明（基于新 hermes 扩展点收敛 monkey-patch）
状态: draft
更新日期: 2026-06-27
适用范围: hermes-seatalk (plugin 版)，仅针对新 hermes
作者: AI Agent Team
参考材料:
  - 本插件技术设计主文档 (./td_hermes-seatalk-plugin_zh.md)
  - 多账号运行时设计 (./tdr_hermes-seatalk-plugin_phase2_multi-account-runtime_zh.md)
  - Hermes platform registry (../../../../hermes-agent/gateway/platform_registry.py)
  - Hermes gateway config 插件启用阶段 (../../../../hermes-agent/gateway/config.py)
  - Hermes send_message tool (../../../../hermes-agent/tools/send_message_tool.py)
  - Hermes 平台接入开发指南 (../../../../hermes-agent/website/docs/developer-guide/adding-platform-adapters.md)
文档摘要: >
  记录一次后续变动：随着新 hermes 提供了正式的 platform plugin 扩展点，
  将 register() 内的 home channel monkey-patch（_patch_home_channel）收敛为
  PlatformEntry.env_enablement_fn 官方钩子。本文档是对主 TD「第 3 节 register() 与
  monkey-patch」的增量说明，不重写主 TD；主 TD 描述的是当时的设计快照，本文档描述其后的演进。
---

# 变更说明：基于新 hermes 扩展点收敛 monkey-patch

## 0. 本文档定位

[主 TD](./td_hermes-seatalk-plugin_zh.md) 第 3 节描述了 `register()` 通过 **四处 monkey-patch**
（cron scheduler 白名单、send_message target 解析、send_to_platform 路由、home channel 解析）
在不改 hermes-agent 源码的前提下接入 SeaTalk。该节是**当时的设计快照**。

此后新 hermes 的 `PlatformRegistry` / `PlatformEntry` 增加了一批正式扩展点（registry 钩子），
使得原本只能靠 monkey-patch 完成的集成可以改为**官方注册参数**。本文档记录这一演进，
并明确哪些 patch 已经/可以收敛、哪些暂时仍需保留及其原因。

> 主 TD 不作改写，仅以本增量文档说明后续变动。

## 1. 演进概览

| 集成点 | 主 TD 当时做法 | 当前做法 | 状态 |
|---|---|---|---|
| cron delivery 白名单 / home target | `_patch_cron_scheduler()` | `PlatformEntry.cron_deliver_env_var="SEATALK_HOME_CHANNEL"` | 已收敛（本次之前） |
| home channel 解析（env 回退） | `_patch_home_channel()` | `PlatformEntry.env_enablement_fn=_seatalk_env_enablement` | **本次收敛** |
| send_message target 解析 | `_patch_send_message_tool()` | 仍为 monkey-patch | 保留（见 §4） |
| send_to_platform 路由 + 媒体 | `_patch_send_to_platform()` | 仍为 monkey-patch | 保留（见 §4） |

本次变动后，`register()` 中的 runtime patch 从 3 个降到 2 个：

```python
def register(ctx):
    os.environ[INTERNAL_ALLOW_ALL_ENV] = "true"
    _patch_send_message_tool()   # 保留：target 解析，无官方钩子
    _patch_send_to_platform()    # 保留：tool 路径媒体发送，无官方钩子
    # _patch_home_channel()      # 已移除，改为 env_enablement_fn
    ctx.register_platform(
        name=SEATALK_PLATFORM,
        ...
        cron_deliver_env_var="SEATALK_HOME_CHANNEL",
        env_enablement_fn=_seatalk_env_enablement,   # 新增
    )
```

## 2. 新机制：env_enablement_fn 取代 home channel patch

### 2.1 原 patch 行为

`_patch_home_channel()` 包裹 `GatewayConfig.get_home_channel`，在原实现返回 `None` 时，
对 SeaTalk 平台读取 `SEATALK_HOME_CHANNEL` / `_THREAD_ID` / `_NAME` 环境变量构造一个
`HomeChannel`，并用 `_make_home_channel()` + `inspect.signature` 兼容老版本不支持 `thread_id`
的 `HomeChannel`。

### 2.2 新实现

改为提供一个纯函数 `_seatalk_env_enablement()`，作为 `PlatformEntry.env_enablement_fn` 注册：

```python
def _seatalk_env_enablement() -> dict[str, Any] | None:
    home = os.getenv("SEATALK_HOME_CHANNEL", "").strip()
    if not home:
        return None
    return {
        "home_channel": {
            "chat_id": home,
            "name": os.getenv("SEATALK_HOME_CHANNEL_NAME", "SeaTalk Home"),
            "thread_id": os.getenv("SEATALK_HOME_CHANNEL_THREAD_ID", "").strip() or None,
        }
    }
```

新 hermes 在 `load_gateway_config()` 的插件启用阶段调用各插件的 `env_enablement_fn`：
返回值里的特殊键 `home_channel` 会被核心提取并构造成正式的 `HomeChannel`（原生支持 `thread_id`）
挂到该平台的 `PlatformConfig` 上；其余键合并进 `PlatformConfig.extra`。之后标准的
`GatewayConfig.get_home_channel` 直接返回 `config.home_channel`，**无需任何 patch**。

参考：`gateway/config.py` 插件启用阶段对 `home_channel` 的处理；`PlatformEntry.env_enablement_fn`
字段定义见 `gateway/platform_registry.py`；契约说明见平台接入开发指南「Env-Driven Auto-Configuration」。

### 2.3 行为差异（需注意）

- **读取时机**：原 patch 在每次 `get_home_channel` 调用时惰性读 env；新机制在 **gateway 加载配置时**
  读一次。运维含义不变——修改 `SEATALK_HOME_CHANNEL*` 后需重启 gateway 生效（README 已说明）。
- **多账号**：account-qualified 形式（如 `staging:group/Home`）仍原样作为 `chat_id` 存入，
  下游 `send` / cron 解析照旧；cron 路径走 `cron_deliver_env_var` 直接读 env，行为不变
  （见多账号测试 `test_t2_07_11`）。
- **版本兼容**：本次**仅针对新 hermes**，已删除对老版 `HomeChannel`（无 `thread_id`）的回退
  （`_make_home_channel` / `inspect.signature`）。不再支持旧 hermes。

## 3. 仍保留的 monkey-patch 及原因

新 hermes 目前**没有**对应的官方钩子，以下两处暂时保留为 patch：

### 3.1 `_patch_send_message_tool()`（target 解析）

`tools/send_message_tool._parse_target_ref` 仍是按平台硬编码的 if/elif，`PlatformEntry`
没有 target 解析钩子（无 `parse_target_fn` 之类）。SeaTalk 的目标格式特殊：`account_id:` 多账号前缀、
`group/<id>`、email、`:thread_id` 后缀，通用回退（仅识别纯数字 chat_id）无法覆盖，会丢 `thread_id`
并把显式目标判成非显式。故必须保留 patch。

### 3.2 `_patch_send_to_platform()`（tool 路径发送 + 媒体）

agent 的 `send_message` 工具运行在 gateway 进程内，核心 `_send_via_adapter` 命中存活 adapter 时
只调用 `adapter.send(text)`，**不转发 `media_files`** 给 `send_image_file` / `send_document`。
唯一的插件媒体钩子 `standalone_sender_fn` 仅在**无存活 runner**（进程外）时才被调用；
内置 Discord 靠核心里硬编码的 `if platform == Platform.DISCORD` 分支强制走 standalone，
外部插件无法在不 patch 的情况下获得同等待遇。因此直接移除该 patch 会回退进程内 tool 媒体发送
（含 `force_document` / `[[as_document]]`），故暂时保留。

### 3.3 上游收敛方向（建议，未实施）

要彻底去掉上述两处，需要给上游 hermes 增加扩展点：
- `PlatformEntry.parse_target_fn`：平台自定义 target 解析钩子（对其他多账号平台同样有用）。
- 让 tool 发送路径对声明了 `standalone_sender_fn`（或新增「强制 standalone / 支持媒体」标志）
  的插件统一走插件发送，覆盖进程内媒体场景。

落地后，SeaTalk 三处 patch 可全部移除，仅保留 `register_platform(...)` 的声明式注册。

## 4. 影响的文件与测试

代码：
- `hermes_seatalk/adapter.py`
  - 删除 `_patch_home_channel()`、`_make_home_channel()`，移除不再使用的 `import inspect`。
  - 新增 `_seatalk_env_enablement()`。
  - `register()`：去掉 `_patch_home_channel()` 调用；`register_platform(...)` 增加
    `env_enablement_fn=_seatalk_env_enablement`（`cron_deliver_env_var` 已有）。

测试：
- `tests/test_w08_runtime_patch.py`：原 home channel patch 用例（`test_t08_03/04/09/10`）改写为
  针对 `_seatalk_env_enablement` 的用例（未设/基础/thread+name/`register()` 钩子已挂载），
  删除老版 `HomeChannel` 兼容用例；`test_t08_06` 幂等性用例去掉 home channel 部分。
- `tests/test_w10_test_quality.py`：`test_t10_04a/04b` 去掉 `get_home_channel` 断言。
- 其余涉及 `SEATALK_HOME_CHANNEL` 的用例（cron 解析、wizard 写 env、README 校验、adapter 自身
  home 解析）均与本次无关，保持不变。

文档：
- `README.md`：home channel 段落措辞微调（读取时机/重启生效），无内部机制泄漏。
- 本增量文档。

## 5. 与主 TD 的对应关系

| 主 TD 位置 | 现状 |
|---|---|
| §3 「register() 与 monkey-patch」开头「四处 monkey-patch」 | 现为 2 处 runtime patch + 2 处声明式注册（`cron_deliver_env_var`、`env_enablement_fn`） |
| §3.1 `_patch_cron_scheduler()` | 已由 `cron_deliver_env_var` 取代（本次之前） |
| 涉及 `_patch_home_channel()` / `_make_home_channel()` 的段落（如 §3、测试矩阵相关条目） | 已移除，由 `env_enablement_fn` 取代，见本文 §2 |

> 主 TD 文本保持不变，以本文档为准记录上述差异。
