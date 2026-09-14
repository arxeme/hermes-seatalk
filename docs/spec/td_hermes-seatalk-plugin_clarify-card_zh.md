---
标题: Hermes SeaTalk Platform Plugin 技术设计 · clarify 交互卡片（send_clarify）
状态: draft
更新日期: 2026-09-03
适用范围: hermes-seatalk (plugin 版)，基线 hermes v2026.7.30 (v0.19.1)
作者: AI Agent Team
参考材料:
  - 本插件技术设计主文档 (./td_hermes-seatalk-plugin_zh.md)
  - clarify 工具与 schema (../../../references/hermes-agent/tools/clarify_tool.py)
  - clarify 阻塞原语 (../../../references/hermes-agent/tools/clarify_gateway.py)
  - send_clarify 契约与文本兜底 (../../../references/hermes-agent/gateway/platforms/base.py)
  - SeaTalk OpenAPI 参考 (../../../voyager/docs/references/seatalk-openapi.md)
文档摘要: >
  Hermes 的 clarify 工具让 agent 向用户提出带选项的问题，适配器通过重写 send_clarify
  渲染按钮，未重写时退化为编号文本列表。本文档记录在 hermes-seatalk 上实现该钩子的
  接口设计与数据流。
---

# clarify 交互卡片（send_clarify）

## 0. 本文档定位

主 TD 描述消息收发与多账号运行时，不涉及富消息。本文档是一个**新增能力**的设计。

范围边界：

- **在范围内**：`clarify` 的单选卡片渲染、点击回灌、Other 自由输入、答完后的卡片收尾。
- **不在范围内**：`send_exec_approval` / `send_update_prompt`（危险命令审批与升级提示，由系统流程而非 agent 触发）；`send_slash_confirm`。

## 1. 背景：契约与当前缺口

### 1.1 clarify 是 agent 主动调用的工具

`clarify` 在 `toolsets.py` 的 `_HERMES_CORE_TOOLS` 里，是核心工具，由模型决定何时调用。schema 在 `tools/clarify_tool.py`，三种模式：

| 模式 | 条件 | 说明 |
| --- | --- | --- |
| 单选 | `choices` 非空，最多 4 个 | UI 自动追加第 5 个「Other」 |
| 多选 | `multi_select=true` | 复选，`user_response` 是列表 |
| 开放式 | 省略 `choices` | 用户自由输入 |

适配器钩子（`gateway/platforms/base.py` 的 `send_clarify`）：

```python
async def send_clarify(
    self,
    chat_id: str,
    question: str,
    choices: Optional[list],
    clarify_id: str,
    session_key: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> SendResult:
```

基类默认实现渲染编号文本列表，并调 `mark_awaiting_text(clarify_id)` 让网关的文本拦截捕获用户的打字回复。这一步不属于基类：覆写了钩子的适配器要自己调（见 2.5）。

### 1.2 回灌端按身份寻址

```python
def resolve_gateway_clarify(clarify_id: str, response: str) -> bool:
    entry = _entries.get(clarify_id)
    if entry is None:
        return False
```

`clarify_id` 是 `uuid4().hex[:10]`（`gateway/run.py` 的 clarify 回调），10 个十六进制字符。查不到返回 `False`，**不会误伤其他请求**。传入的是**选项文本**，不是索引。

## 2. 约束

### 2.1 可直接复用

| 能力 | 现状 |
| --- | --- |
| 回灌 | `resolve_gateway_clarify` / `mark_awaiting_text` 是普通函数调用 |
| 鉴权 | `dispatcher.py` 已有 `_dm_policy` / `_group_policy` / `_group_allowlist` / `_group_sender_allowlist` |
| 事件去重 | `dispatcher._record_event(key)`，挡 SeaTalk 重投 |
| 点击者身份 | 点击事件带 `employee_code` / `email` |

**鉴权不新增机制**：点击是入站输入，走消息路径同一套策略。

### 2.2 SeaTalk 卡片的行为

- **`get_message` 会返回卡片的 `interactive_message.elements`**，并带 `last_edited_time`，因此收尾可以保留原内容、只换按钮。
- **回传的 callback 按钮只有 `text`，没有 `value`**，所以只能重建整份 elements，不能原地改某个元素。
- **`last_edited_time > 0` 即已被改写**，可直接用作重复收尾的判据，不需要插件状态。
- **`title` 会被渲染成加粗大字**，所以问题原文必须放 `description`；放 `title` 会让一段长问题变成粗体标题。
- **同一行的按钮会各自截断到约三分之一卡片宽度**，所以按钮一律用独立 `button` 纵向堆叠，不用 `button_group`。

### 2.3 非点击场景不主动收尾

用户可以不点按钮，直接打字回答（数字或选项原文都算）；clarify 也可能一直没人回答而超时。这两种情况下问题已经结束，但 `tools/clarify_gateway.py` 不会通知适配器，它的导出里没有任何终态回调。

后果是卡片上的按钮还留着，看起来像还能答。这个状态可能持续很久：`clarify.timeout` 默认 3600 秒（`clarify_gateway.resolve_clarify_timeout`，`<= 0` 表示无限）。

改写卡片与补发一条消息都需要先被通知，所以两条路都不可行（卡片本身在 Update 的 7 天窗口内始终可改写）。

终态在有人点击这张失效卡片时体现：`resolve_gateway_clarify` 返回 `False`，卡片随即收尾并显示 `This question is no longer open.`（见 4.2）。在此之前卡片看起来是活的。

### 2.4 只渲染单选

多选与开放式**委托基类文本兜底**，卡片只画一种形态：单选、1-4 个选项、外加一个 Other。基类的多选兜底会给出「reply with the numbers separated by commas」的引导语。

### 2.5 卡片路径同样开启文本拦截

发出卡片后要调 `mark_awaiting_text`，和基类文本列表为自己做的一样。不调的话，打字回答会被 `_coerce_text_response` 拒绝（它只认数字和选项原文），而此时 agent 正阻塞在 `wait_for_response`，被拒的消息于是落到网关忙路径，没有任何回复，直到 clarify 超时。

开启之后仍是数字与选项原文先映射成规范选项，只有自由文本原样进入条目。

## 3. 接口设计

### 3.1 `hermes_seatalk/client.py`

```python
def build_interactive_message(elements: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap card elements into a SeaTalk interactive_message body."""

async def update_message(self, message_id: str, message: dict[str, Any]) -> dict[str, Any]:
    """POST /messaging/v2/update. Interactive messages only."""
```

`get_message_by_id` 已存在。

**投递有调用方超时预算。** `gateway/run.py` 的 clarify 回调等待 `send_clarify` 15 秒，超时即 `clear_session`；而 `RATE_LIMIT_RETRY_DELAYS_SECONDS` 是 `(10.0, 60.0)`，退避无上界。所以 `send_clarify` 整体(卡片与文本兜底共享)套一个 `CLARIFY_SEND_TIMEOUT_SECONDS` deadline，到期返回 `SendResult(success=False)`：任何提示都不在 clarify 清掉之后落地。

取消会顺着 `await` 链传播，所以 `client.refresh_token` 的两个等待点都用 `asyncio.shield`，共享的 token 任务不被某一个超时的调用方带走。

### 3.2 `hermes_seatalk/adapter.py`

```python
async def send_clarify(
    self,
    chat_id: str,
    question: str,
    choices: list | None,
    clarify_id: str,
    session_key: str,
    metadata: dict[str, Any] | None = None,
) -> SendResult:
```

- `choices` 为空、该条目 `multi_select` 为真、选项超过 4 个、或问题超过 1000 字符-> `super().send_clarify(...)`。
- 否则渲染卡片：`description`（问题原文）+ 每个选项一个 callback 按钮 + 一个 Other 按钮，按钮各占一行。
- 发送过程抛错也回落文本，不让 agent 干等。

### 3.3 防连点

```python
self._clarify_claimed: OrderedDict[tuple[str | None, str], None] = OrderedDict()
CLARIFY_CLAIMED_MAX = 1000
```

一个有界的已认领卡片集合，只在点击时写：键已在表内说明本进程已认领过，直接返回；否则写入并继续，随后 FIFO 裁剪至上限。读写之间不能有 `await`。发送时不记账。

键是 `(account_id, message_id)`。SeaTalk 文档：`message_id` 按 app 作用域，不可跨 app 比较。多账号下裸用 `message_id` 会让一个账号的卡片挡掉另一个账号的同名卡片。

**键不存在表示「本进程没认领过」，要继续处理。** 卡片活在 SeaTalk 服务器上（Update 限 7 天），而这张表只活在进程内存里且有上限，所以进程重启或条目被淘汰后，点击到达时键都不在表里。当成已认领就等于既不收尾也不回话，用户只看到沉默。

不设 TTL：两种缺失都落回上面这条路径，内存由上限约束。

上游竞态：`resolve_gateway_clarify` 不检查 `entry.event.is_set()`，先打字作答再立刻点按钮时，agent 可能收到按钮值而不是打字内容。窗口为毫秒级。

这只防同进程连点，不承担正确性上界：`resolve_gateway_clarify` 按 `clarify_id` 寻址，重复调用最坏是返回 `False`，不会误伤其他请求。跨进程的重复点击就由它兜底，外加 `last_edited_time > 0` 时跳过收尾。

### 3.4 按钮 `value` 编码

```
stc1:<clarify_id>:<idx>      选项
stco1:<clarify_id>           Other
```

`clarify_id` 是 10 位十六进制，`idx` 是 0-3，总长约 20 字符，远低于 200 字符上限。

三条约束：

- **解码失败 -> 完全忽略。** 前缀对不上说明未必是我们发出的卡片。
- **`idx` 越界 -> 忽略。** 规范选项文本从 `_entries[clarify_id].choices[idx]` 取回，取不到时退化为位置标签。
- **不沿用 `ADDING_A_PLATFORM.md` 里的 `cl:<id>:<idx>` / `cl:<id>:other`。** `ADDING_A_PLATFORM.md` 列的是 `cl:` / `appr:` / `sc:` 三个各自专用的前缀，解析在各适配器内。差异只在 `cl:<id>:other` 与 `cl:<id>:<idx>` 共前缀、靠尾部区分，而 `stc1:` / `stco1:` 各自锚定，任何一条 value 只可能匹配一种形态。
- **这是一个 wire format。** 已发出的卡片会持续用旧编码回传点击，解码端必须容忍自己已不再生产的取值。

### 3.5 `hermes_seatalk/dispatcher.py`

`interactive_message_click` 不是消息事件，不加入 `SUPPORTED_MESSAGE_EVENTS`。新增一条独立分支，位置在 `dispatch` 中 `LOG_ONLY_EVENTS` 判断之后、`SUPPORTED_MESSAGE_EVENTS` 判断之前；去重沿用 `_record_event`。

## 4. 数据流

### 4.1 发送

```
agent 调 clarify 工具
  -> gateway/run.py _clarify_callback_sync
     -> clarify_id = uuid4().hex[:10]；clarify_gateway.register(...)
     -> adapter.send_clarify(chat_id, question, choices, clarify_id, session_key, metadata)
        -> 多选 / 开放式 / 选项数超限 / 问题超长: super().send_clarify(...) 文本兜底
        -> 单选: 构造 elements = description(问题) + 选项按钮 + Other 按钮
                 client.send_group_chat / send_single_chat(interactive_message)
                       _arm_clarify_text_capture(clarify_id) -> mark_awaiting_text
     -> 阻塞在 wait_for_response(clarify_id, timeout)
```

### 4.2 点击选项

```
dispatcher.dispatch
  -> _record_event("<app_id>:<event_id>")   失败则丢弃（SeaTalk 重投）
  -> 解码 value；失败则忽略
  -> 鉴权：沿用消息路径的 DM / 群策略
  -> _clarify_claimed 内已有 (account_id, message_id) 则返回（连点）；否则写入并裁剪
  -> 取规范选项文本：_entries[clarify_id].choices[idx]，取不到则位置标签
  -> resolve_gateway_clarify(clarify_id, text)
       True  -> 收尾卡片（勾选该项）
       False -> 收尾卡片（无勾选，状态行为 "This question is no longer open."）
```

### 4.3 点击 Other

```
  -> mark_awaiting_text(clarify_id)
       True  -> 勾选 Other，状态文本 = "Reply with your own answer."
       False -> 无勾选，状态文本 = "This question is no longer open."
  -> 收尾卡片(勾选位, 状态文本)，收尾失败不补发（下一步会发）
  -> 回复同一句状态文本
```

Other 与选项点击不同，勾选和状态行同时出现：勾选记录用户点了什么，状态行告诉用户还要打字。

`True` 时 clarify 仍未决，用户随后打字由网关的文本拦截解决。卡片此刻就收尾，因为 2.3 的缘故不主动收尾就会一直挂着。

### 4.4 收尾卡片

```
收尾(message_id, 勾选位, 状态文本)
  -> client.get_message_by_id(message_id)
     -> 没有 interactive_message: 跳过
     -> last_edited_time > 0: 跳过（已被改过）
  -> 重建 elements：保留原 description，
       原 callback 按钮渲染成分隔线 + 勾选清单，按位置勾选（选项按 idx，Other 取末位；
       按标签匹配会在某个选项恰好也叫 Other 时勾出两个），
       状态行由调用方决定：选项已提交时省略，其余情况附加
  -> client.update_message(message_id, ...)
  -> 失败：记 warning；调用方要求时补发一条普通消息（选项已提交时是 `Answered: <选项>`，其余是状态文本）
```

三条约束：

- **dispatch 不能占住入站回调。** webhook 模式 5 秒内必须回 200，失败重试 3 次，所以 `webhook.py` 用 `create_task` 把 dispatch 丢到后台，websocket 用 `run_coroutine_threadsafe`。认领不跨 `await` 的理由另见 3.3。**relay 模式在读循环里直接 `await dispatch`**，点击的 2 到 3 次 HTTP 调用会阻塞后续事件读取。
- **先 resolve 再渲染。** 卡片内容由 resolve 的结果决定，这样落在失效之后的点击会显示已关闭，而不会谎称答案已提交。
- **收尾失败不影响 clarify 的解决结果。** 但认领要回滚：resolve 抛错或 `tools` 导入失败时回复「无法提交」并把认领标记撤掉，否则用户被告知失败却无法重试。

## 5. 影响的文件与测试

| 文件 | 改动 |
| --- | --- |
| `hermes_seatalk/clarify_card.py` | 新增：`value` 编解码、`SeaTalkClarifyCard`、卡片与收尾卡片构造 |
| `hermes_seatalk/client.py` | 新增 `build_interactive_message`、`update_message` |
| `hermes_seatalk/adapter.py` | 新增 `send_clarify`、点击处理、防连点表、收尾卡片改写 |
| `hermes_seatalk/dispatcher.py` | 新增 `interactive_message_click` 分支与鉴权 |
| `hermes_seatalk/tools.py` | `send_message` 工具的 `text_format` 缺省值 |
| `README.md` / `env.example` | clarify 卡片行为说明；`text_format` 语义修正 |
| `tests/test_w14_clarify_card.py` | 新增 |
| `tests/test_w03_outbound_adapter.py` / `test_w13_websocket.py` | 随 `text_format` 缺省值调整 |

测试要覆盖：`value` 编解码（非法输入、越界 `idx`、非法 `clarify_id`）、多选与开放式委托基类、选项数超限委托基类、连点被防连点表挡掉、`resolve_gateway_clarify` 返回 False 时显示已关闭、Other 走 `mark_awaiting_text` 且 clarify 保持未决、且收尾卡片、`mark_awaiting_text` 返回 False 时收尾并回终结文案、`last_edited_time > 0` 时跳过收尾、收尾失败时补发状态文本、鉴权拒绝路径不产生副作用。
