---
标题: Hermes SeaTalk 消息能力人工测试用例
状态: draft
更新日期: 2026-05-07
参考材料:
  - Hermes SeaTalk Plugin 真实联调 Runbook (./e2e_hermes-seatalk-plugin_runbook_zh.md)
  - Hermes SeaTalk Plugin Phase 2 测试计划 (./tp_hermes-seatalk-plugin_phase2_multi-account_zh.md)
  - Hermes SeaTalk Plugin Phase 2 测试报告 (./tr_hermes-seatalk-plugin_phase2_multi-account_zh.md)
文档摘要: 覆盖 SeaTalk DM、群聊、thread、文本、图片、文件、引用、转发及嵌套组合的人工消息测试清单。
---

# Hermes SeaTalk 消息能力人工测试用例

## 1. 目标

本清单用于真实 SeaTalk 环境下人工验证 Hermes SeaTalk plugin 的入站消息处理能力。覆盖范围包括：

- 会话形态：DM、Group、Group Thread。
- 基础消息：text、image、file。
- 包装关系：quote、forward、thread。
- 组合关系：quote + media、forward + media、forward + quote、quote + forward、thread + quote/forward/media、多层嵌套。

本文只记录测试步骤和预期结果，不记录 app secret、signing secret、access token 或带敏感内容的截图。

## 2. 通用验证口径

每条人工消息都带唯一编号，例如 `MC-DM-TXT-01`，便于在 Hermes 回复、SeaTalk 消息和 gateway 日志中定位。

通过标准：

- Hermes 有响应，且响应发回同一个 DM、群或 thread。
- Hermes 能看到测试编号和用户实际发送的文本。
- 图片或文件不丢失；Hermes 至少能识别 media 类型，并在模型支持时可引用附件内容。
- quote 内容出现在 Hermes 输入文本前缀中，不重复、不丢失。
- forward 内容带 `[Forwarded messages]` 语义，内部文本、发送者前缀和媒体不丢失。
- thread 消息保留 thread 上下文，不退回群主会话。
- 未授权用户或群不会触发 Hermes 执行。

建议人工提示语：

```text
<TEST_ID> 请只回复你收到的测试编号、消息类型、是否包含引用、是否包含转发、是否包含附件、是否在 thread 中。
```

## 3. 基础消息矩阵

| ID | 会话 | 操作 | Payload | 预期 | 验证结果 |
| --- | --- | --- | --- | --- | --- |
| MC-DM-TXT-01 | DM | 发送普通文本 | text | Hermes 回复同一 DM，能复述测试编号 | PASS：2026-05-07 14:17，Safari SeaTalk Web 发送；Hermes 同一 DM 回复 `MC-DM-TXT-01，文本，否，否，否，否`。 |
| MC-DM-LONG-01 | DM | 发送超过 10k 字文本，首尾分别放 `LONG_DM_IN_START` / `LONG_DM_IN_END` | long text | Hermes 不崩溃；响应能确认首尾 marker 或说明长文本被截断位置 | PARTIAL：2026-05-07 15:45，Safari SeaTalk Web DM 发送超过 10k 字长文本后，Hermes 同一 DM 回复 `MC-DM-LONG-01，文本，否，否，否，否`，证明长文本事件进入 Hermes 且未崩溃；但该回包未确认 `LONG_DM_IN_START` / `LONG_DM_IN_END` 或截断范围，需补充验证后才能判 PASS。 |
| MC-DM-IMG-01 | DM | 发送单张图片，caption 可为空 | image | Hermes 回复同一 DM，识别图片附件 | PASS：2026-05-07 15:51，在 `Xiaoyu No.2` DM 上传内容含测试编号的合成 PNG；Hermes 同一 DM 回复 `MC-DM-IMG-01，图片附件已收到`。 |
| MC-DM-IMG-02 | DM | 发送图片并带文字说明 | text + image | Hermes 同时看到文字和图片 | PASS：2026-05-07 15:53，在 `Xiaoyu No.2` DM 发送文字 `MC-DM-IMG-02 text caption...` 加合成 PNG；Hermes 同一 DM 回复 `MC-DM-IMG-02，文本已收到，图片附件已收到`。 |
| MC-DM-FILE-01 | DM | 发送 PDF 或 txt 文件 | file | Hermes 回复同一 DM，识别文件附件 | PASS：2026-05-07 15:54，在 `Xiaoyu No.2` DM 上传 `MC-DM-FILE-01.txt`；Hermes 同一 DM 回复 `MC-DM-FILE-01，文件附件已收到`。 |
| MC-DM-FILE-02 | DM | 发送文件并带文字说明 | text + file | Hermes 同时看到文字和文件 | PASS：2026-05-07 15:55，在 `Xiaoyu No.2` DM 发送文字 `MC-DM-FILE-02 text caption...` 加 `MC-DM-FILE-02.txt`；Hermes 同一 DM 回复 `MC-DM-FILE-02，文本已收到，文件附件已收到`。 |
| MC-GRP-TXT-01 | Group | 授权用户在授权群发送文本，按配置 @bot | text | Hermes 回复同一群，source 为 group | PASS：2026-05-07 15:20，在 `OpenClaw Testing` 通过 SeaTalk mention 候选生成真实 `@ Xiaoyu No.2` token 后发送；Hermes 同一群回复 `MC-GRP-TXT-01 / message type: text / quote: no / forward: no / attachment: no / group thread context not available`。15:14 的纯文本 `@Xiaoyu No.2` 未触发，可作为操作差异参考。 |
| MC-GRP-LONG-01 | Group | 授权用户在授权群发送超过 10k 字文本，首尾分别放 `LONG_GRP_IN_START` / `LONG_GRP_IN_END` | long text | Hermes 不崩溃；响应回同一群，并能确认首尾 marker 或说明截断位置 | PASS：2026-05-07，用户手工发送成功真实 mention 长文本后，Hermes 同一群回复 `MC-GRP-LONG-01 received / message type: long text / start marker: LONG_GRP_IN_START / visible lines: 0001-0069 / quote: no / forward: no / attachment: no / thread: no explicit thread flag detected`。平台侧未传到 `LONG_GRP_IN_END`，但 Hermes 未崩溃并说明可见截断范围。 |
| MC-GRP-IMG-01 | Group | 授权用户在授权群发送图片 | image | Hermes 回复同一群，识别图片附件 | FAIL：2026-05-07 15:57，在 `OpenClaw Testing` 通过真实 `@ Xiaoyu No.2` mention token 加合成 PNG 发送；Hermes 同一群回复 `Hi — ready for the next test.`，未复述图片内测试编号，也未确认图片附件状态。 |
| MC-GRP-IMG-02 | Group | 授权用户在授权群发送图片加文字 | text + image | 文本和图片均进入 Hermes | FAIL：2026-05-07 15:59，在 `OpenClaw Testing` 通过真实 `@ Xiaoyu No.2` mention token 发送文字 `MC-GRP-IMG-02 text caption...` 加合成 PNG；Hermes 同一群回复 `MC-GRP-IMG-02 text: caption received image attachment status: not available / no image visible to me in this message context`，文字进入但图片附件未进入 Hermes。 |
| MC-GRP-FILE-01 | Group | 授权用户在授权群发送文件 | file | Hermes 回复同一群，识别文件附件 | FAIL：2026-05-07 16:01，在 `OpenClaw Testing` 通过真实 `@ Xiaoyu No.2` mention token 加 `MC-GRP-FILE-01.txt` 发送；SeaTalk 显示文件卡片，但 Hermes 同一群仅回复 `Hi — I’m here.`，未复述文件内测试编号，也未确认文件附件状态。 |
| MC-GRP-FILE-02 | Group | 授权用户在授权群发送文件加文字 | text + file | 文本和文件均进入 Hermes | FAIL：2026-05-07 16:04，在 `OpenClaw Testing` 通过真实 `@ Xiaoyu No.2` mention token 发送文字 `MC-GRP-FILE-02 text caption...` 加 `MC-GRP-FILE-02.txt`；Hermes 同一群回复 `MC-GRP-FILE-02 text: caption received file attachment status: not available / no file visible to me in this message context`，文字进入但文件附件未进入 Hermes。 |
| MC-THR-TXT-01 | Group Thread | 在群 thread 中发送文本 | text + thread | Hermes 回复同一 thread | PENDING：需要在 SeaTalk Web 稳定打开/创建 `OpenClaw Testing` 的 group thread；当前自动化只验证了群主会话输入区。 |
| MC-THR-LONG-01 | Group Thread | 在群 thread 中发送超过 10k 字文本，首尾分别放 `LONG_THR_IN_START` / `LONG_THR_IN_END` | long text + thread | Hermes 不崩溃；响应回同一 thread | PENDING：需要可稳定进入目标 group thread 后再发送长文本。 |
| MC-THR-IMG-01 | Group Thread | 在群 thread 中发送图片 | image + thread | 图片进入 Hermes，回复不离开 thread | PENDING：需要可稳定进入目标 group thread；另见 group media/file 入站当前失败结果。 |
| MC-THR-FILE-01 | Group Thread | 在群 thread 中发送文件 | file + thread | 文件进入 Hermes，回复不离开 thread | PENDING：需要可稳定进入目标 group thread；另见 group media/file 入站当前失败结果。 |

## 4. Quote 矩阵

| ID | 会话 | 操作 | 被引用消息 | 新消息 | 预期 | 验证结果 |
| --- | --- | --- | --- | --- | --- | --- |
| MC-DM-Q-TXT-01 | DM | reply/quote 一条文本 | text | text | Hermes 输入含 quoted 文本前缀和新文本 | PENDING：需要在 SeaTalk Web 对既有 DM 消息执行 Reply/Quote；当前可见 DOM 未暴露稳定 quote 操作入口。 |
| MC-DM-Q-IMG-01 | DM | quote 一张图片 | image | text | Hermes 输入含 quote 语义，并包含 quoted image media | PENDING：需要可稳定执行 DM 图片 quote 操作。 |
| MC-DM-Q-FILE-01 | DM | quote 一个文件 | file | text | Hermes 输入含 quote 语义，并包含 quoted file media | PENDING：需要可稳定执行 DM 文件 quote 操作。 |
| MC-DM-Q-TXT-IMG-01 | DM | quote 文本后发送图片 | text | image | quote 文本和新图片都进入 Hermes | PENDING：需要可稳定执行 quote 操作后再上传图片。 |
| MC-DM-Q-IMG-FILE-01 | DM | quote 图片后发送文件 | image | file | quoted image 和新文件都不丢失 | PENDING：需要可稳定执行图片 quote 操作后再上传文件。 |
| MC-GRP-Q-TXT-01 | Group | 在群中 quote 文本 | text | text | Hermes 回复同一群，quote 前缀存在 | PENDING：需要在 `OpenClaw Testing` 对既有群消息执行 Reply/Quote；当前可见 DOM 未暴露稳定 quote 操作入口。 |
| MC-GRP-Q-IMG-01 | Group | 在群中 quote 图片 | image | text | quote 图片 media 进入 Hermes | PENDING：需要可稳定执行群图片 quote 操作；另见 group image 入站失败。 |
| MC-GRP-Q-FILE-01 | Group | 在群中 quote 文件 | file | text | quote 文件 media 进入 Hermes | PENDING：需要可稳定执行群文件 quote 操作；另见 group file 入站失败。 |
| MC-THR-Q-TXT-01 | Group Thread | 在 thread 中 quote 文本 | text in thread | text | Hermes 回复同一 thread，quote 前缀存在 | PENDING：需要可稳定进入 group thread 并执行 quote 操作。 |
| MC-THR-Q-IMG-01 | Group Thread | 在 thread 中 quote 图片 | image in thread | text | quote 图片进入 Hermes，thread 保持 | PENDING：需要可稳定进入 group thread 并执行图片 quote 操作。 |
| MC-THR-Q-FILE-01 | Group Thread | 在 thread 中 quote 文件 | file in thread | text | quote 文件进入 Hermes，thread 保持 | PENDING：需要可稳定进入 group thread 并执行文件 quote 操作。 |
| MC-Q-DEDUP-01 | DM 或 Group | 5 秒内连续发送两条都 quote 同一消息 | same text | text + text | Hermes 合并输入中同一 quote 只出现一次 | PENDING：依赖 quote 操作入口和连续消息控制。 |
| MC-Q-MULTI-01 | DM 或 Group | 5 秒内连续发送两条分别 quote 不同消息 | text A / text B | text + text | Hermes 合并输入中两个 quote 都出现 | PENDING：依赖 quote 操作入口和连续消息控制。 |
| MC-Q-MISSING-01 | DM 或 Group | quote 一条已删除或不可读取消息 | unavailable | text | 新文本仍进入 Hermes，不因 quote 解析失败丢弃 | PENDING：需要可删除/不可读消息样本和 quote 操作入口。 |

## 5. Forward 矩阵

| ID | 会话 | 操作 | 转发内容 | 预期 | 验证结果 |
| --- | --- | --- | --- | --- | --- |
| MC-DM-FWD-TXT-01 | DM | 转发单条文本 | text | Hermes 输入含 `[Forwarded messages]` 和文本 | PENDING：需要在 SeaTalk Web 对既有消息执行 Forward；当前可见 DOM 未暴露稳定 forward 操作入口。 |
| MC-DM-FWD-MTXT-01 | DM | 转发多条文本 | text[] | 所有文本按行进入 Hermes | PENDING：需要稳定多选/转发 UI。 |
| MC-DM-FWD-IMG-01 | DM | 转发图片 | image | Hermes 输入含 forward 语义，图片 media 不丢失 | PENDING：需要稳定图片转发 UI。 |
| MC-DM-FWD-FILE-01 | DM | 转发文件 | file | Hermes 输入含 forward 语义，文件 media 不丢失 | PENDING：需要稳定文件转发 UI。 |
| MC-DM-FWD-MIX-01 | DM | 转发文本、图片、文件混合记录 | text + image + file | 文本和所有 media 都进入 Hermes | PENDING：需要稳定多选/合并转发 UI。 |
| MC-DM-FWD-SENDER-01 | DM | 转发带原发送者的多条文本 | sender + text[] | 每条文本保留发送者前缀 | PENDING：需要稳定多选/转发 UI，并准备不同原发送者消息。 |
| MC-GRP-FWD-TXT-01 | Group | 在群中转发文本 | text | Hermes 回复同一群，forward 文本存在 | PENDING：需要在 `OpenClaw Testing` 稳定执行群消息 Forward。 |
| MC-GRP-FWD-IMG-01 | Group | 在群中转发图片 | image | 图片 media 不丢失 | PENDING：需要稳定群图片 Forward；另见 group image 入站失败。 |
| MC-GRP-FWD-FILE-01 | Group | 在群中转发文件 | file | 文件 media 不丢失 | PENDING：需要稳定群文件 Forward；另见 group file 入站失败。 |
| MC-GRP-FWD-MIX-01 | Group | 在群中转发文本、图片、文件混合记录 | text + image + file | 所有元素进入 Hermes | PENDING：需要稳定群多选/合并转发 UI；另见 group media/file 入站失败。 |
| MC-THR-FWD-TXT-01 | Group Thread | 在 thread 中转发文本 | text | Hermes 回复同一 thread | PENDING：需要可稳定进入 group thread 并执行 Forward。 |
| MC-THR-FWD-IMG-01 | Group Thread | 在 thread 中转发图片 | image | 图片进入 Hermes，thread 保持 | PENDING：需要可稳定进入 group thread 并执行图片 Forward。 |
| MC-THR-FWD-FILE-01 | Group Thread | 在 thread 中转发文件 | file | 文件进入 Hermes，thread 保持 | PENDING：需要可稳定进入 group thread 并执行文件 Forward。 |
| MC-FWD-NEST-01 | DM 或 Group | 转发“合并转发记录中的嵌套列表” | nested text[] | 嵌套文本被展开，不出现空响应 | PENDING：需要准备嵌套合并转发消息样本并执行 Forward。 |
| MC-FWD-NEST-02 | DM 或 Group | 转发“转发记录里还有转发记录” | forwarded(forwarded text) | 内层 forward 文本可见，保留 forward 语义 | PENDING：需要准备二层 forward 样本并执行 Forward。 |
| MC-FWD-NEST-MEDIA-01 | DM 或 Group | 转发嵌套记录，内层含图片和文件 | nested image + file | 内层 media 不丢失 | PENDING：需要准备含媒体的嵌套 forward 样本；另见 group media/file 入站失败。 |

## 6. Quote 与 Forward 组合矩阵

| ID | 会话 | 操作 | 组合 | 预期 | 验证结果 |
| --- | --- | --- | --- | --- | --- |
| MC-DM-QF-01 | DM | quote 一条转发文本后回复 | quote(forward text) + text | Hermes 输入同时含 quote 和 forward 内容 | PENDING：依赖稳定 quote + forward UI 和预置 forward 样本。 |
| MC-DM-QF-02 | DM | quote 一条转发图片后回复 | quote(forward image) + text | forward image media 不丢失 | PENDING：依赖稳定 quote + forward UI 和预置图片 forward 样本。 |
| MC-DM-FQ-01 | DM | 转发一条带 quote 的文本消息 | forward(quote text + text) | Hermes 输入可见转发文本及其中 quote 语义 | PENDING：依赖稳定 quote/forward UI 和预置 quote 样本。 |
| MC-DM-FQ-02 | DM | 转发一条带 quote 图片的消息 | forward(quote image + text) | quote image media 不丢失 | PENDING：依赖稳定 quote/forward UI 和预置图片 quote 样本。 |
| MC-GRP-QF-01 | Group | 在群中 quote 转发消息后回复 | quote(forward text) + text | Hermes 回复群，quote + forward 内容存在 | PENDING：依赖稳定群 quote/forward UI 和预置 forward 样本。 |
| MC-GRP-QF-02 | Group | 在群中 quote 转发媒体消息后回复 | quote(forward image/file) + text | quoted forward media 不丢失 | PENDING：依赖稳定群 quote/forward UI；另见 group media/file 入站失败。 |
| MC-GRP-FQ-01 | Group | 在群中转发带 quote 的文本消息 | forward(quote text + text) | forward 内的 quote 信息可见或至少文本不丢 | PENDING：依赖稳定群 quote/forward UI 和预置 quote 样本。 |
| MC-THR-QF-01 | Group Thread | 在 thread 中 quote 转发文本后回复 | thread + quote(forward text) | Hermes 回复同一 thread，内容完整 | PENDING：依赖稳定 group thread、quote 和 forward UI。 |
| MC-THR-QF-02 | Group Thread | 在 thread 中 quote 转发媒体后回复 | thread + quote(forward media) | thread 保持，media 不丢失 | PENDING：依赖稳定 group thread、quote、forward 和 media UI；另见 group media/file 入站失败。 |
| MC-THR-FQ-01 | Group Thread | 在 thread 中转发带 quote 的消息 | thread + forward(quote text) | thread 保持，forward/quote 文本可见 | PENDING：依赖稳定 group thread、quote 和 forward UI。 |

## 7. Thread 组合矩阵

| ID | 会话 | 操作 | 组合 | 预期 | 验证结果 |
| --- | --- | --- | --- | --- | --- |
| MC-THR-ROOT-01 | Group | 在群主消息触发 Hermes 后进入 thread 回复 | group root -> thread | 后续 thread 消息进入同一 thread session | PENDING：需要可稳定从群主消息进入/创建 thread。 |
| MC-THR-ROOT-02 | Group Thread | 在 thread 中连续发送两条文本 | text + text within debounce | Hermes 合并同一 thread 内连续文本 | PENDING：需要可稳定进入 group thread。 |
| MC-THR-ISO-01 | Group Thread | 同一群不同 thread 各发送一条文本 | thread A / thread B | 不同 thread 不串 session | PENDING：需要两个稳定 group thread 目标。 |
| MC-THR-USER-01 | Group Thread | 同一 thread 不同授权用户发送文本 | user A / user B | 按当前 session 策略可区分或合并，日志中 user_id 正确 | PENDING：需要第二个授权个人账号和可稳定 thread。 |
| MC-THR-Q-ROOT-01 | Group Thread | 在 thread 中 quote 群主会话消息 | quote root message | quote 内容进入 thread 输入，回复仍在 thread | PENDING：需要可稳定 thread 与 quote 操作入口。 |
| MC-THR-FWD-ROOT-01 | Group Thread | 在 thread 中转发群主会话消息 | forward root message | forward 内容进入 thread 输入，回复仍在 thread | PENDING：需要可稳定 thread 与 forward 操作入口。 |
| MC-THR-MEDIA-MIX-01 | Group Thread | 在 thread 中连续发文本、图片、文件 | text + image + file | 同一 thread 内内容完整，media 不丢失 | PENDING：需要可稳定 thread；另见 group media/file 入站失败。 |

## 8. Multi-account 组合矩阵

如只配置一个 account，本节可记为 N/A。多帐号测试时至少准备 `default` 和 `staging` 或等价 account。

| ID | Account | 会话 | 操作 | 预期 | 验证结果 |
| --- | --- | --- | --- | --- | --- |
| MC-ACC-DM-01 | default | DM | 发送文本 | `source.chat_id` 使用 default 语义，回复来自 default Bot App | PASS：2026-05-07，当前仅配置/使用 `Xiaoyu No.2` bot；`MC-DM-TXT-01` 已验证 default DM 入站和同 DM 回复。未检查后台 `source.chat_id` 日志。 |
| MC-ACC-DM-02 | staging | DM | 发送文本 | `source.chat_id` 带 staging account 维度，回复来自 staging Bot App | PENDING：需要 staging 或第二个 SeaTalk bot account 配置；当前事实只提供 `Xiaoyu No.2`。 |
| MC-ACC-GRP-01 | default | Group | 群文本 | default 群消息不与 staging 群 session 混淆 | PASS：2026-05-07，当前仅配置/使用 default `Xiaoyu No.2`；`MC-GRP-TXT-01` 已验证 default 群入站和同群回复。未检查后台 account 维度日志。 |
| MC-ACC-GRP-02 | staging | Group | 群文本 | staging 群消息不与 default 群 session 混淆 | PENDING：需要 staging 或第二个 SeaTalk bot account 配置。 |
| MC-ACC-THR-01 | staging | Group Thread | thread 文本 | account + group + thread 均正确保留 | PENDING：需要 staging account，且需要可稳定创建/进入 SeaTalk group thread。 |
| MC-ACC-QF-01 | staging | Group Thread | quote + forward + media | staging account 下复杂组合完整进入 Hermes | PENDING：需要 staging account，且依赖 thread、quote、forward 与 media 组合 UI/配置。 |

## 9. 授权与负向矩阵

| ID | 会话 | 操作 | 预期 | 验证结果 |
| --- | --- | --- | --- | --- |
| MC-AUTH-DM-01 | DM | allowlist 内用户发送文本 | Hermes 执行并回复 | PASS：2026-05-07，当前登录 `Yu Yue 余跃` / `yuy@sea.com` 与 `Xiaoyu No.2` DM 的 `MC-DM-TXT-01` 已执行并收到同 DM 回复。 |
| MC-AUTH-DM-02 | DM | allowlist 外用户发送文本 | Hermes 不执行，日志显示 sender_not_allowed | PENDING：需要 allowlist 外 SeaTalk 个人账号发送 DM，或调整当前账号授权配置；当前未提供第二个人员账号。 |
| MC-AUTH-GRP-01 | Group | 授权群内授权用户发送文本 | Hermes 执行并回复 | PASS：2026-05-07，当前登录账号在 `OpenClaw Testing` 发送真实 mention 文本，`MC-GRP-TXT-01` 已收到同群回复。 |
| MC-AUTH-GRP-02 | Group | 授权群内非授权用户发送文本 | Hermes 不执行，日志显示 sender_not_allowed | PENDING：需要非授权个人账号在 `OpenClaw Testing` 发送，或调整授权配置。 |
| MC-AUTH-GRP-03 | Group | 非授权群内授权用户发送文本 | Hermes 不执行，日志显示 group_not_allowed | PENDING：需要明确非授权群或临时修改 group allow 配置。 |
| MC-AUTH-GRP-04 | Group | group_policy=open 且 group_sender_allow_from 命中 | 任意群可触发，但只有 allowlist 用户可执行 | PASS：2026-05-07，用户确认 Hermes group policy 为 open 且当前账号有权限；`MC-GRP-TXT-01` 在 `OpenClaw Testing` 触发并收到同群回复。 |
| MC-AUTH-GRP-05 | Group | group_policy=open 但 group_sender_allow_from 未命中 | Hermes 不执行 | PENDING：需要不命中 `group_sender_allow_from` 的发送者或配置变更。 |

## 10. 边界与降级矩阵

| ID | 会话 | 操作 | 预期 | 验证结果 |
| --- | --- | --- | --- | --- |
| MC-EDGE-EMPTY-01 | DM 或 Group | 发送空文本或只有空白字符 | 不触发 Hermes 或被安全忽略 | PENDING：需要验证 SeaTalk Web 是否允许发送纯空白；当前未执行，避免误触发无编号消息。 |
| MC-EDGE-LONG-01 | DM 或 Group | 发送接近 4000 字文本 | Hermes 正常接收，回复不报错 | PENDING：`MC-DM-LONG-01` / `MC-GRP-LONG-01` 已覆盖超过 10k 长文本，但未单独发送接近 4000 字边界文本。 |
| MC-EDGE-MEDIA-FAIL-01 | DM 或 Group | 发送无法下载或权限失效的图片 | 文本占位 `<media:image>` 可见，gateway 记录 media error | PENDING：需要制造 SeaTalk media 下载失败或查看 gateway 日志；当前 Web UI 只能发送正常上传图片。 |
| MC-EDGE-MEDIA-FAIL-02 | DM 或 Group | 发送无法下载或权限失效的文件 | 文本占位 `<media:document>` 可见，gateway 记录 media error | PENDING：需要制造 SeaTalk media 下载失败或查看 gateway 日志；当前 Web UI 只能发送正常上传文件。 |
| MC-EDGE-UNSUP-01 | DM 或 Group | 发送 SeaTalk 支持但 plugin 未支持的消息类型 | Hermes 输入含 `<unsupported:...>` 或日志可定位，不崩溃 | PENDING：需要明确一个当前 plugin 未支持且 SeaTalk Web 可发送的消息类型，并可观察 Hermes/gateway 日志。 |
| MC-EDGE-DUP-01 | DM 或 Group | 通过重发或 relay/webhook 双投制造同 event id | Hermes 只处理一次 | PENDING：需要 webhook/relay 层双投同 event id，不能仅通过 SeaTalk Web 构造。 |
| MC-EDGE-BURST-01 | DM 或 Group | 5 秒内连续发送 3 条文本 | Hermes 合并为一次输入，文本顺序正确 | PENDING：2026-05-07 16:12 尝试自动连续发送失败，仅第一条 `MC-EDGE-BURST-01 part 1/3 order=A` 发出并收到普通文本回包，后续文本停留在输入框后已清空；该次不满足 burst 条件，需人工或更可靠脚本重跑。 |
| MC-EDGE-BURST-MEDIA-01 | DM 或 Group | 短时间连续发送文本、图片、文本 | 文本顺序正确，图片不丢失 | PENDING：需要可靠连续发送控制；另见 group media/file 入站失败，建议先在 DM 重跑。 |

## 11. Hermes -> SeaTalk 反向发送矩阵

本节只验证 Hermes 主动发送到 SeaTalk 的出站路径。SeaTalk -> Hermes 的入站路径在第 3 到第 10 节覆盖。quote / forward 是 SeaTalk 入站消息结构，Hermes 不主动构造 SeaTalk quote/forward；相关回包验证已包含在第 4 到第 6 节的预期中。

| ID | 会话 | 操作 | 目标 / Payload | 预期 | 验证结果 |
| --- | --- | --- | --- | --- | --- |
| MC-OUT-DM-TXT-01 | DM | Hermes 主动发送普通文本 | `seatalk:<employee_code>` 或 email target | SeaTalk DM 收到文本 | PENDING：需要可触发 Hermes 主动出站的命令/API 入口和目标 `employee_code`/email；当前只执行 SeaTalk -> Hermes 入站人工消息。 |
| MC-OUT-DM-LONG-01 | DM | Hermes 主动发送超过 10k 字文本 | `seatalk:<employee_code>` | SeaTalk 收到按约 4000 字分片的多条消息，顺序正确 | PENDING：需要可触发 Hermes 主动出站的命令/API 入口和目标账号。 |
| MC-OUT-DM-IMG-01 | DM | Hermes 主动发送图片 | image file / image URL | SeaTalk DM 收到图片 | PENDING：需要可触发 Hermes 主动发送图片的命令/API 入口和素材路径/URL。 |
| MC-OUT-DM-FILE-01 | DM | Hermes 主动发送文件 | document file | SeaTalk DM 收到文件，文件名可识别 | PENDING：需要可触发 Hermes 主动发送文件的命令/API 入口和文件路径。 |
| MC-OUT-GRP-TXT-01 | Group | Hermes 主动发送群文本 | `seatalk:group/<group_id>` | SeaTalk 群收到文本 | PENDING：需要 `OpenClaw Testing` 的 SeaTalk `group_id` 和可触发 Hermes 出站的命令/API 入口。 |
| MC-OUT-GRP-LONG-01 | Group | Hermes 主动发送超过 10k 字群文本 | `seatalk:group/<group_id>` | 群内收到多条分片消息，顺序正确 | PENDING：需要群 `group_id` 和 Hermes 出站触发入口。 |
| MC-OUT-GRP-IMG-01 | Group | Hermes 主动发送群图片 | `seatalk:group/<group_id>` + image | SeaTalk 群收到图片 | PENDING：需要群 `group_id`、图片素材和 Hermes 出站触发入口。 |
| MC-OUT-GRP-FILE-01 | Group | Hermes 主动发送群文件 | `seatalk:group/<group_id>` + file | SeaTalk 群收到文件 | PENDING：需要群 `group_id`、文件素材和 Hermes 出站触发入口。 |
| MC-OUT-THR-TXT-01 | Group Thread | Hermes 主动发送 thread 文本 | `seatalk:group/<group_id>:<thread_id>` | SeaTalk thread 收到文本，不落到群主会话 | PENDING：需要群 `group_id`、目标 `thread_id` 和 Hermes 出站触发入口。 |
| MC-OUT-THR-LONG-01 | Group Thread | Hermes 主动发送超过 10k 字 thread 文本 | `seatalk:group/<group_id>:<thread_id>` | thread 内收到多条分片消息，顺序正确 | PENDING：需要群 `group_id`、目标 `thread_id` 和 Hermes 出站触发入口。 |
| MC-OUT-THR-IMG-01 | Group Thread | Hermes 主动发送 thread 图片 | `seatalk:group/<group_id>:<thread_id>` + image | SeaTalk thread 收到图片 | PENDING：需要 thread 目标、图片素材和 Hermes 出站触发入口。 |
| MC-OUT-THR-FILE-01 | Group Thread | Hermes 主动发送 thread 文件 | `seatalk:group/<group_id>:<thread_id>` + file | SeaTalk thread 收到文件 | PENDING：需要 thread 目标、文件素材和 Hermes 出站触发入口。 |
| MC-OUT-ACC-DM-01 | Multi-account DM | Hermes 使用指定 account 发送 DM | `seatalk:<account_id>:<employee_code>` | 消息由指定 Bot App 发送 | PENDING：需要 multi-account 配置和出站触发入口。 |
| MC-OUT-ACC-THR-01 | Multi-account Thread | Hermes 使用指定 account 发送 thread 文本 | `seatalk:<account_id>:group/<group_id>:<thread_id>` | 指定 Bot App 的对应 thread 收到消息 | PENDING：需要 multi-account 配置、thread 目标和出站触发入口。 |

建议的出站长文本内容：

```text
LONG_OUT_START
第 0001 行：0123456789abcdefghijklmnopqrstuvwxyz
...
第 0200 行：0123456789abcdefghijklmnopqrstuvwxyz
LONG_OUT_END
```

出站长文本通过标准：

- SeaTalk 侧收到多条消息，而不是单条失败。
- 每条消息不超过 SeaTalk 文本限制，通常约 4000 字以内。
- 第一条含 `LONG_OUT_START`，最后一条含 `LONG_OUT_END`。
- 多条消息顺序正确，没有明显重复或丢段。

## 12. 最小回归子集

如果时间有限，至少执行以下关键子集：

`MC-DM-TXT-01`、`MC-DM-LONG-01`、`MC-DM-IMG-02`、`MC-DM-FILE-02`、`MC-GRP-TXT-01`、`MC-GRP-LONG-01`、`MC-GRP-IMG-02`、`MC-GRP-FILE-02`、`MC-THR-TXT-01`、`MC-THR-LONG-01`、`MC-THR-IMG-01`、`MC-DM-Q-TXT-01`、`MC-DM-Q-IMG-01`、`MC-DM-FWD-MIX-01`、`MC-FWD-NEST-02`、`MC-DM-QF-02`、`MC-THR-QF-02`、`MC-THR-ISO-01`、`MC-AUTH-GRP-04`、`MC-EDGE-MEDIA-FAIL-01`、`MC-EDGE-BURST-MEDIA-01`、`MC-OUT-DM-TXT-01`、`MC-OUT-DM-LONG-01`、`MC-OUT-THR-TXT-01`、`MC-OUT-THR-LONG-01`。
