---
标题: Hermes SeaTalk Plugin Phase 2 多帐号测试报告
状态: draft
更新日期: 2026-05-05
参考材料:
  - Hermes SeaTalk Plugin Phase 2 多帐号技术设计 (../spec/td_hermes-seatalk-plugin_phase2_multi-account_zh.md)
  - Hermes SeaTalk Plugin Phase 2 多帐号工作分解结构 (../spec/wbs_hermes-seatalk-plugin_phase2_multi-account_zh.md)
  - Hermes SeaTalk Plugin Phase 2 多帐号测试计划 (./tp_hermes-seatalk-plugin_phase2_multi-account_zh.md)
文档摘要: 滚动记录 Hermes SeaTalk Plugin Phase 2 多帐号各 WBS 任务的自动化测试、回归测试和待验证项。
---

# TR: Hermes SeaTalk Plugin Phase 2 多帐号

## 1. 当前结论

当前 Phase 2 已完成：

- W2-00 Accounts 配置模型与校验：PASS
- W2-01 Hermes 注册与内部授权闸门：PASS
- W2-02 多 AccountRuntime 与状态聚合：PASS
- W2-03 入站 account context 与授权策略：PASS
- W2-04 Relay 多帐号 runtime：PASS
- W2-05 Spike: Webhook challenge 与签名行为验证：PENDING
- W2-06 Webhook 多帐号 runtime：PASS
- W2-07 出站 account 选择与 Hermes patch：PASS
- W2-08 Setup wizard、文档与发布边界：PASS
- W2-09 自动化测试与回归收敛：PASS

待验证：

- W2-05 Spike: Webhook challenge 与签名行为验证仍需真实 SeaTalk Bot App 回调确认。

本 TR 采用滚动记录方式：每完成一个 W2 任务，在同一文件追加对应测试结果、回归命令和未覆盖项。

## 2. 测试环境

| 项目 | 内容 |
| --- | --- |
| 工作目录 | `/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk` |
| Python 环境 | plugin repo 有 `pyproject.toml`；当前本地 `uv run pytest` 未安装 pytest，测试使用 sibling hermes-agent `.venv` |
| 测试框架 | `pytest`、`pytest-asyncio` |
| 外部依赖 | W2-00 不依赖真实 SeaTalk credentials |

## 3. 测试执行记录

### W2-00 Accounts 配置模型与校验

执行命令：

```bash
PYTHONPATH=/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk:/Users/yuy/Work/project/ai-study/ref/hermes-agent \
  /Users/yuy/Work/project/ai-study/ref/hermes-agent/.venv/bin/python -m pytest \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_p2_config_accounts.py
```

执行结果：

```text
collected 29 items

tests/test_p2_config_accounts.py .............................           [100%]

29 passed in 0.32s
```

### W2-01 Hermes 注册与内部授权闸门

执行命令：

```bash
PYTHONPATH=/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk:/Users/yuy/Work/project/ai-study/ref/hermes-agent \
  /Users/yuy/Work/project/ai-study/ref/hermes-agent/.venv/bin/python -m pytest \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_p2_config_accounts.py \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_w01_registration.py
```

执行结果：

```text
collected 39 items

tests/test_p2_config_accounts.py .............................           [ 74%]
tests/test_w01_registration.py ..........                                [100%]

39 passed in 0.28s
```

### Batch 1 回归

执行命令：

```bash
PYTHONPATH=/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk:/Users/yuy/Work/project/ai-study/ref/hermes-agent \
  /Users/yuy/Work/project/ai-study/ref/hermes-agent/.venv/bin/python -m pytest \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_p2_config_accounts.py \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_w01_registration.py
```

执行结果：

```text
collected 39 items

tests/test_p2_config_accounts.py .............................           [ 74%]
tests/test_w01_registration.py ..........                                [100%]

39 passed in 0.26s
```

### W2-02 多 AccountRuntime 与状态聚合

执行命令：

```bash
PYTHONPATH=/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk:/Users/yuy/Work/project/ai-study/ref/hermes-agent \
  /Users/yuy/Work/project/ai-study/ref/hermes-agent/.venv/bin/python -m pytest \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_p2_runtime_accounts.py
```

执行结果：

```text
collected 9 items

tests/test_p2_runtime_accounts.py .........                              [100%]

9 passed in 0.29s
```

当前回归命令：

```bash
PYTHONPATH=/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk:/Users/yuy/Work/project/ai-study/ref/hermes-agent \
  /Users/yuy/Work/project/ai-study/ref/hermes-agent/.venv/bin/python -m pytest \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_p2_config_accounts.py \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_w01_registration.py \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_p2_runtime_accounts.py
```

当前回归结果：

```text
collected 48 items

tests/test_p2_config_accounts.py .............................           [ 60%]
tests/test_w01_registration.py ..........                                [ 81%]
tests/test_p2_runtime_accounts.py .........                              [100%]

48 passed in 0.26s
```

### W2-03 入站 account context 与授权策略

执行命令：

```bash
PYTHONPATH=/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk:/Users/yuy/Work/project/ai-study/ref/hermes-agent \
  /Users/yuy/Work/project/ai-study/ref/hermes-agent/.venv/bin/python -m pytest \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_p2_dispatcher_accounts.py
```

执行结果：

```text
collected 10 items

tests/test_p2_dispatcher_accounts.py ..........                          [100%]

10 passed in 0.31s
```

当前回归命令：

```bash
PYTHONPATH=/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk:/Users/yuy/Work/project/ai-study/ref/hermes-agent \
  /Users/yuy/Work/project/ai-study/ref/hermes-agent/.venv/bin/python -m pytest \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_p2_config_accounts.py \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_w01_registration.py \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_p2_runtime_accounts.py \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_p2_dispatcher_accounts.py
```

当前回归结果：

```text
collected 58 items

tests/test_p2_config_accounts.py .............................           [ 50%]
tests/test_w01_registration.py ..........                                [ 67%]
tests/test_p2_runtime_accounts.py .........                              [ 82%]
tests/test_p2_dispatcher_accounts.py ..........                          [100%]

58 passed in 0.29s
```

### W2-04 Relay 多帐号 runtime

执行命令：

```bash
PYTHONPATH=/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk:/Users/yuy/Work/project/ai-study/ref/hermes-agent \
  /Users/yuy/Work/project/ai-study/ref/hermes-agent/.venv/bin/python -m pytest \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_p2_relay_accounts.py
```

执行结果：

```text
collected 9 items

tests/test_p2_relay_accounts.py .........                                [100%]

9 passed in 0.59s
```

说明：该测试需要本机绑定 `127.0.0.1` 临时端口启动 mock WebSocket server；默认 sandbox 下会因端口绑定权限失败，已用提升权限执行。

当前回归命令：

```bash
PYTHONPATH=/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk:/Users/yuy/Work/project/ai-study/ref/hermes-agent \
  /Users/yuy/Work/project/ai-study/ref/hermes-agent/.venv/bin/python -m pytest \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_p2_config_accounts.py \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_w01_registration.py \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_p2_runtime_accounts.py \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_p2_dispatcher_accounts.py \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_p2_relay_accounts.py
```

当前回归结果：

```text
collected 67 items

tests/test_p2_config_accounts.py .............................           [ 43%]
tests/test_w01_registration.py ..........                                [ 58%]
tests/test_p2_runtime_accounts.py .........                              [ 71%]
tests/test_p2_dispatcher_accounts.py ..........                          [ 86%]
tests/test_p2_relay_accounts.py .........                                [100%]

67 passed in 0.62s
```

### W2-06 Webhook 多帐号 runtime

执行命令：

```bash
PYTHONPATH=/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk:/Users/yuy/Work/project/ai-study/ref/hermes-agent \
  /Users/yuy/Work/project/ai-study/ref/hermes-agent/.venv/bin/python -m pytest \
  /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk/tests/test_p2_webhook_accounts.py
```

执行结果：

```text
collected 10 items

tests/test_p2_webhook_accounts.py ..........                            [100%]

10 passed in 0.33s
```

当前回归命令：

```bash
PYTHONPATH=/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk:/Users/yuy/Work/project/ai-study/ref/hermes-agent \
  /Users/yuy/Work/project/ai-study/ref/hermes-agent/.venv/bin/python -m pytest \
  tests/test_p2_config_accounts.py \
  tests/test_w01_registration.py \
  tests/test_p2_runtime_accounts.py \
  tests/test_p2_dispatcher_accounts.py \
  tests/test_p2_relay_accounts.py \
  tests/test_p2_webhook_accounts.py \
  tests/test_w04_webhook.py \
  tests/test_w06_dispatcher.py
```

当前回归结果：

```text
collected 90 items

tests/test_p2_config_accounts.py .............................           [ 32%]
tests/test_w01_registration.py ..........                                [ 43%]
tests/test_p2_runtime_accounts.py .........                              [ 53%]
tests/test_p2_dispatcher_accounts.py ..........                          [ 64%]
tests/test_p2_relay_accounts.py .........                                [ 74%]
tests/test_p2_webhook_accounts.py ..........                             [ 85%]
tests/test_w04_webhook.py .......                                        [ 93%]
tests/test_w06_dispatcher.py ......                                      [100%]

90 passed in 0.76s
```

### W2-07 出站 account 选择与 Hermes patch

执行命令：

```bash
PYTHONPATH=/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk:/Users/yuy/Work/project/ai-study/ref/hermes-agent \
  /Users/yuy/Work/project/ai-study/ref/hermes-agent/.venv/bin/python -m pytest \
  tests/test_p2_outbound_accounts.py
```

执行结果：

```text
collected 10 items

tests/test_p2_outbound_accounts.py ..........                           [100%]

10 passed in 0.28s
```

当前回归命令：

```bash
PYTHONPATH=/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk:/Users/yuy/Work/project/ai-study/ref/hermes-agent \
  /Users/yuy/Work/project/ai-study/ref/hermes-agent/.venv/bin/python -m pytest \
  tests/test_p2_config_accounts.py \
  tests/test_w01_registration.py \
  tests/test_p2_runtime_accounts.py \
  tests/test_p2_dispatcher_accounts.py \
  tests/test_p2_relay_accounts.py \
  tests/test_p2_webhook_accounts.py \
  tests/test_p2_outbound_accounts.py \
  tests/test_w03_outbound_adapter.py \
  tests/test_w04_webhook.py \
  tests/test_w06_dispatcher.py \
  tests/test_w08_runtime_patch.py
```

当前回归结果：

```text
collected 119 items

tests/test_p2_config_accounts.py .............................           [ 24%]
tests/test_w01_registration.py ..........                                [ 32%]
tests/test_p2_runtime_accounts.py .........                              [ 40%]
tests/test_p2_dispatcher_accounts.py ..........                          [ 48%]
tests/test_p2_relay_accounts.py .........                                [ 56%]
tests/test_p2_webhook_accounts.py ..........                             [ 64%]
tests/test_p2_outbound_accounts.py ..........                            [ 73%]
tests/test_w03_outbound_adapter.py ...........                           [ 82%]
tests/test_w04_webhook.py .......                                        [ 88%]
tests/test_w06_dispatcher.py ......                                      [ 93%]
tests/test_w08_runtime_patch.py ........                                 [100%]

119 passed in 1.18s
```

### W2-08 Setup wizard、文档与发布边界

执行命令：

```bash
PYTHONPATH=/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk:/Users/yuy/Work/project/ai-study/ref/hermes-agent \
  /Users/yuy/Work/project/ai-study/ref/hermes-agent/.venv/bin/python -m pytest \
  tests/test_p2_setup_docs.py
```

执行结果：

```text
collected 9 items

tests/test_p2_setup_docs.py .........                                    [100%]

9 passed in 0.24s
```

当前回归命令：

```bash
PYTHONPATH=/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk:/Users/yuy/Work/project/ai-study/ref/hermes-agent \
  /Users/yuy/Work/project/ai-study/ref/hermes-agent/.venv/bin/python -m pytest \
  tests/test_p2_config_accounts.py \
  tests/test_w01_registration.py \
  tests/test_p2_runtime_accounts.py \
  tests/test_p2_dispatcher_accounts.py \
  tests/test_p2_relay_accounts.py \
  tests/test_p2_webhook_accounts.py \
  tests/test_p2_outbound_accounts.py \
  tests/test_p2_setup_docs.py \
  tests/test_w03_outbound_adapter.py \
  tests/test_w04_webhook.py \
  tests/test_w06_dispatcher.py \
  tests/test_w08_runtime_patch.py \
  tests/test_w09_operations_docs.py
```

当前回归结果：

```text
collected 136 items

tests/test_p2_config_accounts.py .............................           [ 21%]
tests/test_w01_registration.py ..........                                [ 28%]
tests/test_p2_runtime_accounts.py .........                              [ 35%]
tests/test_p2_dispatcher_accounts.py ..........                          [ 42%]
tests/test_p2_relay_accounts.py .........                                [ 49%]
tests/test_p2_webhook_accounts.py ..........                             [ 56%]
tests/test_p2_outbound_accounts.py ..........                            [ 63%]
tests/test_p2_setup_docs.py .........                                     [ 70%]
tests/test_w03_outbound_adapter.py ...........                           [ 78%]
tests/test_w04_webhook.py .......                                        [ 83%]
tests/test_w06_dispatcher.py ......                                      [ 88%]
tests/test_w08_runtime_patch.py ........                                 [ 94%]
tests/test_w09_operations_docs.py ........                               [100%]

136 passed in 1.12s
```

### W2-09 自动化测试与回归收敛

执行命令：

```bash
uv run pytest -q
```

执行结果：

```text
145 passed, 8 skipped in 0.85s
```

Hermes venv 回归命令：

```bash
PYTHONPATH=/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk:/Users/yuy/Work/project/ai-study/ref/hermes-agent \
  /Users/yuy/Work/project/ai-study/ref/hermes-agent/.venv/bin/python -m pytest -q
```

Hermes venv 回归结果：

```text
176 passed in 1.36s
```

## 4. WBS 任务结果

### W2-00 Accounts 配置模型与校验

| 用例 | 结果 | 验证内容 | 证据 |
| --- | --- | --- | --- |
| T2-00-01 accounts 缺失失败 | PASS | `accounts` 缺失、空 dict、非 dict 时配置校验失败 | `tests/test_p2_config_accounts.py` |
| T2-00-02 enabled false 处理 | PASS | platform disabled 可跳过校验；disabled account 不参与必填校验 | `tests/test_p2_config_accounts.py` |
| T2-00-03 顶层默认 merge | PASS | 顶层默认字段被 account 继承，account 字段覆盖顶层 | `tests/test_p2_config_accounts.py` |
| T2-00-04 credentials 完整性 | PASS | enabled account 缺 `app_id` / `app_secret` / `signing_secret` / `mode` 任一项时整体失败 | `tests/test_p2_config_accounts.py` |
| T2-00-05 relay 必填 | PASS | `mode=relay` 缺 `relay_url` 时整体失败 | `tests/test_p2_config_accounts.py` |
| T2-00-06 webhook 必填 | PASS | `mode=webhook` 的 port/path 非法时整体失败 | `tests/test_p2_config_accounts.py` |
| T2-00-07 account id 校验 | PASS | 空、大写、冒号、斜杠、空格、非法首字符 account id 被拒绝 | `tests/test_p2_config_accounts.py` |
| T2-00-08 重复 app_id | PASS | enabled accounts 中重复 `app_id` 被拒绝 | `tests/test_p2_config_accounts.py` |
| T2-00-09 policy enum | PASS | `dm_policy`、`group_policy`、`processing_indicator` 非法值被拒绝 | `tests/test_p2_config_accounts.py` |
| T2-00-10 pairing 拒绝 | PASS | `dm_policy=pairing` 在 Phase 2 中被拒绝 | `tests/test_p2_config_accounts.py` |
| T2-00-11 group id 格式 | PASS | `group_allow_from` 中以 `group/` 开头的值被拒绝 | `tests/test_p2_config_accounts.py` |
| T2-00-12 env secrets 不参与 | PASS | 未设置 `SEATALK_APP_SECRET` / `SEATALK_SIGNING_SECRET` 但 accounts 中有 secret 时校验成功 | `tests/test_p2_config_accounts.py` |

完成条件核对：

| 完成条件 | 结果 | 证据 |
| --- | --- | --- |
| `accounts` 缺失、空、非法类型时配置校验失败 | MET | T2-00-01 |
| 顶层默认字段可 shallow merge 到 account，account 字段覆盖顶层 | MET | T2-00-03 |
| 任一 enabled account 缺少 credentials 或 mode 时整体失败 | MET | T2-00-04 |
| relay account 缺少 `relay_url` 时整体失败 | MET | T2-00-05 |
| webhook account 的 `webhook_port` / `webhook_path` 非法时整体失败 | MET | T2-00-06 |
| account id 格式合法性校验 | MET | T2-00-07 |
| `dm_policy=pairing` 被拒绝 | MET | T2-00-09 |
| `group_allow_from` 中出现 `group/<id>` 被拒绝 | MET | T2-00-11 |
| 重复 `app_id` 被拒绝 | MET | T2-00-08 |
| `.env` secrets 不参与校验 | MET | T2-00-12 |
| `REQUIRED_ENV = []` | MET | `hermes_seatalk/adapter.py` |

### W2-01 Hermes 注册与内部授权闸门

| 用例 | 结果 | 验证内容 | 证据 |
| --- | --- | --- | --- |
| T2-01-01 check_fn 只查依赖 | PASS | `check_seatalk_requirements()` 不读取 `.env` / `config.yaml`，`aiohttp` 可导入时返回 true | `tests/test_w01_registration.py` |
| T2-01-02 REQUIRED_ENV 为空 | PASS | `REQUIRED_ENV == []`，注册元数据不再要求 SeaTalk secret env | `tests/test_w01_registration.py` |
| T2-01-03 register 使用 allow_all_env | PASS | fake context 记录 `allow_all_env="HERMES_SEATALK_ALLOW_ALL"` | `tests/test_w01_registration.py` |
| T2-01-04 不注册 allowed_users_env | PASS | fake context 中没有 `allowed_users_env` | `tests/test_w01_registration.py` |
| T2-01-05 内部 env 设置 | PASS | `register(ctx)` 设置 process env `HERMES_SEATALK_ALLOW_ALL=true` | `tests/test_w01_registration.py` |
| T2-01-06 不写用户 env 文件 | PASS | register 只设置 process env，不调用 `.env` 写入路径 | `tests/test_w01_registration.py` |
| T2-01-07 validate_config 承担 accounts 校验 | PASS | registry `validate_config` 指向 `_validate_seatalk_config`，非法 accounts 由 validator 拒绝 | `tests/test_w01_registration.py`、`tests/test_p2_config_accounts.py` |
| T2-01-08 register 幂等 | PASS | 重复 `register(ctx)` 不重复注册平台 | `tests/test_w01_registration.py` |

完成条件核对：

| 完成条件 | 结果 | 证据 |
| --- | --- | --- |
| `check_fn` 不读取 `.env` / `config.yaml`，只验证依赖可导入 | MET | T2-01-01 |
| `required_env` 为空，Hermes setup/status 不再提示 SeaTalk secret env | MET | T2-01-02 |
| platform 注册不传 `allowed_users_env` | MET | T2-01-04 |
| 内部 `HERMES_SEATALK_ALLOW_ALL` 不写入用户 `.env` | MET | T2-01-06 |
| 多次 `register(ctx)` 幂等，不重复 patch 或重复注册 | MET | T2-01-08 |
| `validate_config` 承担 accounts 校验 | MET | T2-01-07 |

### W2-02 多 AccountRuntime 与状态聚合

| 用例 | 结果 | 验证内容 | 证据 |
| --- | --- | --- | --- |
| T2-02-01 runtime map 创建 | PASS | 两个 enabled accounts 创建两个 runtime，disabled account 被跳过 | `tests/test_p2_runtime_accounts.py` |
| T2-02-02 runtime 隔离 | PASS | 每个 runtime 拥有独立 client、dispatcher、coalescer | `tests/test_p2_runtime_accounts.py` |
| T2-02-03 secret 跨 account 脱敏 | PASS | 任一 account 的 `app_secret` / `signing_secret` 都存在于每个 client 的 `log_secrets` | `tests/test_p2_runtime_accounts.py` |
| T2-02-04 状态字段 | PASS | runtime state 记录 `running/auth_failed/retrying/stopped/last_error` | `tests/test_p2_runtime_accounts.py` |
| T2-02-05 单 account 永久失败隔离 | PASS | 一个 runtime auth_failed 不停止其他 runtime | `tests/test_p2_runtime_accounts.py` |
| T2-02-06 聚合非 fatal | PASS | 至少一个 runtime running/retrying 时 platform 不 fatal | `tests/test_p2_runtime_accounts.py` |
| T2-02-07 聚合 fatal | PASS | 所有 enabled runtimes 均永久失败时 platform fatal | `tests/test_p2_runtime_accounts.py` |
| T2-02-08 disconnect 全部 runtime | PASS | adapter disconnect 停止全部 runtime 并关闭 client | `tests/test_p2_runtime_accounts.py` |
| T2-02-09 account_id 日志 | PASS | runtime 状态日志包含对应 `account_id` | `tests/test_p2_runtime_accounts.py` |

完成条件核对：

| 完成条件 | 结果 | 证据 |
| --- | --- | --- |
| 每个 enabled account 创建一个 runtime | MET | T2-02-01 |
| disabled account 不创建 runtime | MET | T2-02-01 |
| 每个 runtime 使用自己的 client/dispatcher/coalescer | MET | T2-02-02 |
| 所有 enabled account 的 secret 都注入每个 client 的 `log_secrets` | MET | T2-02-03 |
| 一个 account runtime 永久失败不停止其他 account | MET | T2-02-05 |
| 至少一个 account running/retrying 时 platform 不 fatal | MET | T2-02-06 |
| 所有 enabled accounts 均永久失败时 platform fatal | MET | T2-02-07 |
| connect/disconnect/error 日志包含 `account_id` | MET | T2-02-09 |

### W2-03 入站 account context 与授权策略

| 用例 | 结果 | 验证内容 | 证据 |
| --- | --- | --- | --- |
| T2-03-01 DM chat_id 带 account | PASS | DM `source.chat_id` 为 `<account_id>:<dm_target>` | `tests/test_p2_dispatcher_accounts.py` |
| T2-03-02 group chat_id 带 account | PASS | group `source.chat_id` 为 `<account_id>:group/<seatalk_group_id>` | `tests/test_p2_dispatcher_accounts.py` |
| T2-03-03 user_id 不带 account | PASS | `source.user_id` 保持 email 或 employee code，不加 account prefix | `tests/test_p2_dispatcher_accounts.py` |
| T2-03-04 thread 单独承载 | PASS | group thread id 写入 `source.thread_id`，不拼入 `source.chat_id` | `tests/test_p2_dispatcher_accounts.py` |
| T2-03-05 raw metadata | PASS | `raw_message["seatalk_account_id"]` 等于 runtime account id | `tests/test_p2_dispatcher_accounts.py` |
| T2-03-06 session key 隔离 | PASS | 同 sender 在 default/staging 下生成不同 Hermes session key | `tests/test_p2_dispatcher_accounts.py` |
| T2-03-07 DM allowlist | PASS | `allow_from` 按 email 和 employee code 匹配 | `tests/test_p2_dispatcher_accounts.py` |
| T2-03-08 group raw allowlist | PASS | `group_allow_from` 匹配 raw SeaTalk `group_id`，不是 `group/<id>` | `tests/test_p2_dispatcher_accounts.py` |
| T2-03-09 group sender allowlist | PASS | `group_policy=open` 时仍按 `group_sender_allow_from` 限制 sender | `tests/test_p2_dispatcher_accounts.py` |
| T2-03-10 account policy 隔离 | PASS | account A allow sender 不影响 account B | `tests/test_p2_dispatcher_accounts.py` |

完成条件核对：

| 完成条件 | 结果 | 证据 |
| --- | --- | --- |
| 入站 DM `source.chat_id` 为 `<account_id>:<dm_target>` | MET | T2-03-01 |
| 入站 group `source.chat_id` 为 `<account_id>:group/<seatalk_group_id>` | MET | T2-03-02 |
| `source.user_id` 不加 account prefix | MET | T2-03-03 |
| `source.thread_id` 不拼进 `source.chat_id` | MET | T2-03-04 |
| 同一 sender 在不同 account 下生成不同 session key | MET | T2-03-06 |
| `allow_from` 按 email/employee code 匹配 | MET | T2-03-07 |
| `group_allow_from` 只匹配 raw SeaTalk `group_id` | MET | T2-03-08 |
| `group_sender_allow_from` 在 group policy 下仍生效 | MET | T2-03-09 |
| raw metadata 包含 `seatalk_account_id` | MET | T2-03-05 |

### W2-04 Relay 多帐号 runtime

| 用例 | 结果 | 验证内容 | 证据 |
| --- | --- | --- | --- |
| T2-04-01 多 relay 启动 | PASS | 两个 relay accounts 分别建立 WebSocket 连接 | `tests/test_p2_relay_accounts.py` |
| T2-04-02 relay event 路由 | PASS | default relay event 只进入 default dispatcher，staging 同理 | `tests/test_p2_relay_accounts.py` |
| T2-04-03 relay payload app_id 校验 | PASS | payload `app_id` 与 runtime `app_id` 不一致时丢弃并 warning | `tests/test_p2_relay_accounts.py` |
| T2-04-04 auth_fail 隔离 | PASS | 一个 account 收到 `auth_fail` 后标为永久失败，另一个继续 connected | `tests/test_p2_relay_accounts.py` |
| T2-04-05 网络 pending 隔离 | PASS | 单 account 初始连接未完成时进入 retrying，其他 account 不受影响 | `tests/test_p2_relay_accounts.py` |
| T2-04-06 replaced 隔离 | PASS | 一个 account 收到 `replaced` 后标为永久失败，其他 account 不受影响 | `tests/test_p2_relay_accounts.py` |
| T2-04-07 heartbeat timeout 重连 | PASS | 单 account heartbeat timeout 进入 retrying，不停止其他 account | `tests/test_p2_relay_accounts.py` |
| T2-04-08 网络断开重连 | PASS | mock server 断开单 account 连接，该 account 进入 retrying | `tests/test_p2_relay_accounts.py` |
| T2-04-09 日志 account_id | PASS | relay state 日志包含 `account_id` | `tests/test_p2_relay_accounts.py` |

完成条件核对：

| 完成条件 | 结果 | 证据 |
| --- | --- | --- |
| 两个 relay accounts 可同时启动 | MET | T2-04-01 |
| relay event 进入正确 account dispatcher | MET | T2-04-02 |
| relay payload `app_id` 不匹配 runtime `app_id` 时被丢弃并记录 warning | MET | T2-04-03 |
| 单个 account `auth_fail` 标为永久失败，不影响其他 account | MET | T2-04-04 |
| 单个 account `replaced` 标为永久失败，不影响其他 account | MET | T2-04-06 |
| 单个 account heartbeat timeout 进入 retrying，不影响其他 account | MET | T2-04-07 |
| 单个 account 网络错误 / 断开进入 retrying，不影响其他 account | MET | T2-04-05、T2-04-08 |
| relay failure 按 account 隔离，platform-level fatal 由 W2-02 聚合决定 | MET | T2-04-04 到 T2-04-08；W2-02 聚合测试 |
| relay 日志包含 `account_id` | MET | T2-04-09 |

### W2-05 Spike: Webhook challenge 与签名行为验证

| 用例 | 结果 | 验证内容 | 证据 |
| --- | --- | --- | --- |
| T2-05-01 challenge payload 实测 | PENDING | 记录 SeaTalk `event_verification` payload 是否携带 `app_id` | 需要真实 SeaTalk Bot App 回调 |
| T2-05-02 challenge 签名实测 | PENDING | 确认 challenge 使用与普通事件相同的 Signature 校验规则 | 需要真实 SeaTalk Bot App 回调 |
| T2-05-03 普通事件 app_id 实测 | PENDING | 确认普通 message event 是否总携带 `app_id` | 需要真实 SeaTalk Bot App 回调 |
| T2-05-04 shared endpoint 策略复核 | PENDING | 基于实测确认先验签后解析的 shared endpoint 策略可用 | 等待 T2-05-01 到 T2-05-03 |
| T2-05-05 TD 回填 | PENDING | 若协议与 TD 不一致，更新 TD §5.2 / §11 后再进入 W2-06 | 等待 T2-05-01 到 T2-05-03 |

本地源码证据：

- `hermes_seatalk/webhook.py` 当前处理顺序为 read raw body -> verify `Signature` -> parse JSON -> `event_type=event_verification` 返回 `event.seatalk_challenge`。
- `openclaw-seatalk/src/monitor.ts` 同样先验签，再解析 body，并对 `event_verification` 返回 `body.event.seatalk_challenge`。
- `deploy/capture-seatalk-webhook.py` 可从 `deploy/app.local` 读取 `app_id` / `signing_secret`，
  启动临时 webhook endpoint，并输出脱敏后的验签与 payload 结构记录。

当前结论：

- 本地实现支持 challenge payload 不携带 `app_id` 的处理方式。
- 真实 SeaTalk 是否在 challenge / 普通事件中稳定携带 `app_id` 尚未确认。
- W2-06 shared webhook 多帐号 mock/runtime 覆盖已按 TD 假设完成；真实 SeaTalk
  challenge / 普通事件 payload 形态仍由 W2-05 HITL 后续确认。
- OpenClaw SeaTalk 当前 webhook 实现是 per-account server/context：每个 account 使用
  自己的 `signingSecret` 验签，验签通过后才解析 JSON；`event_verification` 只从
  `body.event.seatalk_challenge` 取 challenge 并返回，不依赖 payload `app_id` 选择
  account。Hermes Phase 2 若采用 shared endpoint，需要额外处理 candidate secrets；
  该部分已由 W2-06 mock 集成测试覆盖。

本地 helper 验证：

```bash
python3 deploy/capture-seatalk-webhook.py --show-config
```

结果：脚本可读取 `deploy/app.local` flat YAML 结构，并只输出 masked app id。

```bash
python3 deploy/capture-seatalk-webhook.py --host 127.0.0.1 --port 0 --path /callback
```

使用本地构造的 `event_verification` 请求验证：返回 `200` 和
`{"seatalk_challenge": "challenge-local"}`；capture 输出显示：

```text
signature_valid=true
matched_account_id=default
event_type=event_verification
payload_has_app_id=false
event_has_seatalk_challenge=true
```

该验证只证明 helper 自身和现有签名算法可工作，不替代真实 SeaTalk Bot App 回调实测。

远端临时环境清理：

- 已停止 VM 内 `capture-seatalk-webhook.py` 后台进程。
- 已移除 VM 内临时文件：
  - `/home/openclaw/.hermes/plugins/seatalk/deploy/capture-seatalk-webhook.py`
  - `/home/openclaw/.hermes/plugins/seatalk/deploy/app.local`
  - `/home/openclaw/.hermes/seatalk-webhook-capture.pid`
  - `/home/openclaw/.hermes/logs/seatalk-webhook-capture.log`
- 已移除 Incus 临时 proxy device：`seatalk-capture-webhook`。
- 已确认宿主 `:18080` 不再监听该临时转发。

### W2-06 Webhook 多帐号 runtime

| 用例 | 结果 | 验证内容 | 证据 |
| --- | --- | --- | --- |
| T2-06-01 shared server 合并 | PASS | 相同 `(host, port, path)` 的多个 accounts 只启动一个 server | `tests/test_p2_webhook_accounts.py` |
| T2-06-02 不同 endpoint 分离 | PASS | 不同 port 的 accounts 启动不同 server | `tests/test_p2_webhook_accounts.py` |
| T2-06-03 先验签后解析 | PASS | malformed JSON 但签名错误时返回 403，不进入 JSON parse error 路径 | `tests/test_p2_webhook_accounts.py` |
| T2-06-04 candidate secret 命中 | PASS | 使用 staging secret 签名的请求路由到 staging runtime | `tests/test_p2_webhook_accounts.py` |
| T2-06-05 签名无匹配 | PASS | 所有 candidate secrets 都不匹配时返回 403，不 dispatch | `tests/test_p2_webhook_accounts.py` |
| T2-06-06 app_id mismatch | PASS | 签名匹配 account A 但 payload `app_id` 是 B 时返回 403 | `tests/test_p2_webhook_accounts.py` |
| T2-06-07 challenge 无 app_id | PASS | 签名有效且 challenge payload 无 app_id 时仍返回 challenge | `tests/test_p2_webhook_accounts.py` |
| T2-06-08 普通事件缺 app_id | PASS | 普通 message event 缺 app_id 时被拒绝 | `tests/test_p2_webhook_accounts.py` |
| T2-06-09 unknown app_id | PASS | unknown app_id 返回 403，不泄露 account 枚举 | `tests/test_p2_webhook_accounts.py` |
| T2-06-10 dispatch account_id | PASS | webhook dispatch 后进入正确 account dispatcher | `tests/test_p2_webhook_accounts.py` |

完成条件核对：

| 完成条件 | 结果 | 证据 |
| --- | --- | --- |
| 同 endpoint 下多个 webhook accounts 共享一个 server | MET | T2-06-01 |
| 不同 endpoint 的 webhook accounts 使用不同 server | MET | T2-06-02 |
| webhook handler 先验签，再解析 JSON | MET | T2-06-03 |
| candidate secret 命中后路由到对应 account dispatch | MET | T2-06-04、T2-06-10 |
| 所有 candidate secrets 都不匹配时返回 403 | MET | T2-06-05 |
| payload `app_id` 与签名匹配 account 不一致时返回 403 | MET | T2-06-06 |
| `event_verification` payload 不携带 `app_id` 时仍可返回 challenge | MET | T2-06-07 |
| 普通事件缺 `app_id` 时返回 403 | MET | T2-06-08 |
| unknown `app_id` 不泄露 account 枚举 | MET | T2-06-09 |
| Phase 1 webhook server 兼容路径仍通过回归 | MET | `tests/test_w04_webhook.py` |

### W2-07 出站 account 选择与 Hermes patch

| 用例 | 结果 | 验证内容 | 证据 |
| --- | --- | --- | --- |
| T2-07-01 parser 无 prefix DM | PASS | `EmpABC` 解析为未绑定 account 的 DM target | `tests/test_p2_outbound_accounts.py` |
| T2-07-02 parser account DM | PASS | `staging:EmpABC` 解析为 account `staging`、chat_id `EmpABC`、thread_id None | `tests/test_p2_outbound_accounts.py` |
| T2-07-03 parser group | PASS | `group/<seatalk_group_id>` 解析为 group target | `tests/test_p2_outbound_accounts.py` |
| T2-07-04 parser account group thread | PASS | `staging:group/<seatalk_group_id>:ThreadXYZ` 保留 account/group/thread | `tests/test_p2_outbound_accounts.py` |
| T2-07-05 prefix 先于 thread | PASS | `staging:EmpABC` 不会被误解析为 `chat_id=staging, thread_id=EmpABC` | `tests/test_p2_outbound_accounts.py` |
| T2-07-06 metadata 优先 | PASS | `metadata["seatalk_account_id"]` 优先于 target prefix | `tests/test_p2_outbound_accounts.py` |
| T2-07-07 default fallback | PASS | 无 account prefix 时优先使用 `default` account | `tests/test_p2_outbound_accounts.py` |
| T2-07-08 first enabled fallback | PASS | 无 default account 时使用按 account id 排序的第一个 enabled account | `tests/test_p2_outbound_accounts.py` |
| T2-07-09 send 使用目标 runtime | PASS | send/send_typing/media send 调用解析出的 account runtime client | `tests/test_p2_outbound_accounts.py` |
| T2-07-10 home channel account | PASS | `home_channel_account_id=staging` 返回并使用 `staging:<home_channel>` | `tests/test_p2_outbound_accounts.py` |
| T2-07-11 cron account target | PASS | cron SeaTalk target 使用 account-qualified target | `tests/test_p2_outbound_accounts.py` |
| T2-07-12 内置平台回归 | PASS | Discord 原有 target parser 行为不变 | `tests/test_p2_outbound_accounts.py` |
| T2-07-13 get_chat_info account target | PASS | `get_chat_info("staging:EmpABC")` 不误解析 thread；group info 使用 staging account client | `tests/test_p2_outbound_accounts.py` |
| T2-07-14 SeaTalkTarget 默认 account_id | PASS | 旧式四参数构造仍可用，`account_id` 默认为 None | `tests/test_p2_outbound_accounts.py` |
| T2-07-15 seatalk prefix 与 account prefix | PASS | `seatalk:staging:EmpABC` 先剥离 `seatalk:`，再解析 account prefix 为 staging | `tests/test_p2_outbound_accounts.py` |

完成条件核对：

| 完成条件 | 结果 | 证据 |
| --- | --- | --- |
| account prefix 在 group/email/thread 解析前剥离 | MET | T2-07-02、T2-07-04、T2-07-05 |
| `seatalk:` platform prefix 在 account prefix 解析前剥离 | MET | T2-07-15 |
| `SeaTalkTarget.account_id: str | None = None` | MET | T2-07-14 |
| `staging:EmpABC` 解析为 account `staging`、target `EmpABC`，不是 thread | MET | T2-07-02、T2-07-05 |
| `staging:group/<seatalk_group_id>:ThreadXYZ` 正确保留 thread | MET | T2-07-04 |
| `metadata["seatalk_account_id"]` 优先级高于 target prefix | MET | T2-07-06 |
| 无 account prefix 时按 `default` / 第一个 enabled account 选择 | MET | T2-07-07、T2-07-08 |
| `get_chat_info("staging:EmpABC")` 不误解析 thread，group info 使用 staging runtime client | MET | T2-07-13 |
| `home_channel_account_id` 生效 | MET | T2-07-10 |
| cron delivery 使用 account-qualified target | MET | T2-07-11 |
| 内置平台 target parser 行为不变 | MET | T2-07-12 |

### W2-08 Setup wizard、文档与发布边界

| 用例 | 结果 | 验证内容 | 证据 |
| --- | --- | --- | --- |
| T2-08-01 wizard add account | PASS | wizard 可创建 `accounts.<account_id>` 并写入 credentials/mode/policy | `tests/test_p2_setup_docs.py` |
| T2-08-02 wizard edit account | PASS | wizard 编辑 account 不破坏其他 accounts | `tests/test_p2_setup_docs.py` |
| T2-08-03 wizard disable/remove | PASS | disable/remove account 后配置结构正确 | `tests/test_p2_setup_docs.py` |
| T2-08-04 wizard home channel | PASS | wizard 可设置 `home_channel_account_id` / `home_channel` / thread | `tests/test_p2_setup_docs.py` |
| T2-08-05 wizard 不写 env | PASS | wizard 不写 SeaTalk secrets 到 `.env` | `tests/test_p2_setup_docs.py` |
| T2-08-06 wizard 无 pairing | PASS | wizard 不展示 `dm_policy=pairing` | `tests/test_p2_setup_docs.py` |
| T2-08-07 README accounts 配置 | PASS | README 展示 `platforms.seatalk.extra.accounts` 示例 | `tests/test_p2_setup_docs.py` |
| T2-08-08 README secrets 提醒 | PASS | README 明确 `config.yaml` 包含 `app_secret` / `signing_secret` | `tests/test_p2_setup_docs.py` |
| T2-08-09 README group 格式 | PASS | README 区分 `group_allow_from` raw id 与 `home_channel` target | `tests/test_p2_setup_docs.py` |
| T2-08-10 publish branch 内容 | PASS | `scripts/publish-release.sh` 输出 publish branch 只含 runtime 文件和 README | `tests/test_p2_setup_docs.py` |
| T2-08-11 deploy 不覆盖 config | PASS | deploy 脚本文档/逻辑不默认覆盖远端 `~/.hermes/config.yaml` | `tests/test_p2_setup_docs.py` |

完成条件核对：

| 完成条件 | 结果 | 证据 |
| --- | --- | --- |
| wizard 支持 add/edit/disable/remove account | MET | T2-08-01 到 T2-08-03 |
| wizard 支持设置 home channel account | MET | T2-08-04 |
| wizard 不写 `.env`，只写 `config.yaml` accounts | MET | T2-08-05 |
| wizard 不展示 `pairing` | MET | T2-08-06 |
| README 明确 `config.yaml` 包含 secrets | MET | T2-08-08 |
| README 区分 `group_allow_from` raw group id 与 `home_channel` target 格式 | MET | T2-08-09 |
| README 说明 `publish` 分支只包含 runtime 文件和 README | MET | T2-08-10 |
| deploy 脚本不默认覆盖远端 `config.yaml` | MET | T2-08-11 |

### W2-09 自动化测试与回归收敛

| 用例 | 结果 | 验证内容 | 证据 |
| --- | --- | --- | --- |
| T2-09-01 全量离线 pytest | PASS | 不设置真实 SeaTalk credentials 时核心 pytest 可通过 | `uv run pytest -q` |
| T2-09-02 env 隔离 | PASS | 测试间 env var 不互相污染，尤其是 internal allow-all env | `tests/conftest.py`、`tests/test_w01_registration.py` |
| T2-09-03 registry 隔离 | PASS | platform registry 在测试间恢复 | `tests/conftest.py` |
| T2-09-04 patch 隔离 | PASS | runtime patch 测试不污染后续用例 | `tests/conftest.py`、`tests/test_w08_runtime_patch.py` |
| T2-09-05 Phase 1 default 回归 | PASS | 单 default account 行为覆盖 Phase 1 主要 send/relay/webhook/auth 路径 | Hermes venv full pytest |
| T2-09-06 batch 命令可用 | PASS | 各 batch 命令已按任务执行并回填本 TR | 本 TR §3 |
| T2-09-07 E2E runbook 更新 | PASS | E2E runbook 包含多 account relay/webhook/出站/home channel 验证步骤 | `docs/test/e2e_hermes-seatalk-plugin_runbook_zh.md` |

完成条件核对：

| 完成条件 | 结果 | 证据 |
| --- | --- | --- |
| `uv run pytest` 可离线运行核心测试 | MET | T2-09-01 |
| 不需要真实 SeaTalk secrets 即可覆盖 config、runtime、relay/webhook mock、outbound parser | MET | W2-00 到 W2-08 自动化测试 |
| env、registry、monkey patch 状态在测试间隔离 | MET | T2-09-02 到 T2-09-04 |
| Phase 1 单帐号路径在 `default` account 下可继续工作 | MET | T2-09-05 |
| E2E runbook 增补多 account 手工验证步骤 | MET | T2-09-07 |

## 5. 人工复核（可选）

| 复核项 | 类型 | 结果 | 验证人 | 备注 |
| --- | --- | --- | --- | --- |
| W2-00 config.yaml accounts 示例复核 | 人工（可选） | READY |  | README/setup wizard 已更新，可按下方步骤复核 |

#### W2-00 config.yaml accounts 示例复核 — 操作步骤

1. 在测试 Hermes 配置中准备 `platforms.seatalk.extra.accounts.default`。
2. 分别填入 relay/webhook account 示例。
3. 运行 `hermes gateway status` 或等价配置加载路径。
4. 验证：完整 accounts 配置可通过校验；缺失 secret、非法 account id、`group/group_id` 格式会被拒绝。

## 6. 未覆盖与后续

- W2-00 只覆盖静态配置解析；runtime 创建和 per-account 状态聚合由 W2-02 覆盖。
- W2-01 将继续覆盖 `check_fn`、`allow_all_env` 和 Hermes 注册边界。
- W2-05 真实 SeaTalk URL verification / message event payload 仍需 HITL 验证；
  当前 shared webhook 行为按 TD 假设和 OpenClaw SeaTalk 参考实现覆盖。
