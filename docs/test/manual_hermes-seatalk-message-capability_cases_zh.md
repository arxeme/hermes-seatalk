---
标题: Hermes SeaTalk 消息能力人工测试用例
状态: draft
更新日期: 2026-05-08
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
- SeaTalk Web 发送 text + image/file 时会拆成独立消息；本文不再把“文字和附件混发在同一条入站事件”作为通过条件。
- Group 内 bot 默认不能看到之前的 media/file 消息；需要 quote 该 media/file 后 @bot，或进入该 media/file 的 replying thread 后 @bot，才判定为有效 group media/file 入站测试。

本文只记录测试步骤和预期结果，不记录 app secret、signing secret、access token 或带敏感内容的截图。

## 2. 通用验证口径

每条人工消息都带唯一编号，例如 `MC-DM-TXT-01`，便于在 Hermes 回复、SeaTalk 消息和 gateway 日志中定位。

通过标准：

- Hermes 有响应，且响应发回同一个 DM、群或 thread。
- Hermes 能看到测试编号和用户实际发送的文本。
- 图片或文件不丢失；DM 中可直接触发并识别 media 类型，Group 中只有通过 quote 或 replying thread @bot 后才判定为 bot 可见。
- text + image/file 在 SeaTalk Web 中按拆分后的独立消息验证；如果需要验证上下文关联，使用 quote 或 replying thread 用例。
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
| MC-DM-LONG-01 | DM | 发送超过 10k 字文本，首尾分别放 `LONG_DM_IN_START` / `LONG_DM_IN_END` | long text | Hermes 不崩溃；响应能确认首尾 marker 或说明长文本被截断位置 | NA: SeaTalk UI 不支持发送长消息。 |
| MC-DM-IMG-01 | DM | 发送单张图片，caption 可为空 | image | Hermes 回复同一 DM，识别图片附件 | PASS：2026-05-07 15:51，在 `Xiaoyu No.2` DM 上传内容含测试编号的合成 PNG；Hermes 同一 DM 回复 `MC-DM-IMG-01，图片附件已收到`。 |
| MC-DM-IMG-02 | DM | 连续发送文字说明和图片；SeaTalk Web 会拆成一条 text 和一条 image | split(text, image) | Hermes 能分别处理拆分后的文字消息和图片消息；不要求同一事件同时包含 text 与 image | PASS：2026-05-07 15:53，在 `Xiaoyu No.2` DM 发送文字 `MC-DM-IMG-02 text caption...` 加合成 PNG；SeaTalk 拆分后 Hermes 同一 DM 分别确认文本和图片附件。 |
| MC-DM-FILE-01 | DM | 发送 PDF 或 txt 文件 | file | Hermes 回复同一 DM，识别文件附件 | PASS：2026-05-07 15:54，在 `Xiaoyu No.2` DM 上传 `MC-DM-FILE-01.txt`；Hermes 同一 DM 回复 `MC-DM-FILE-01，文件附件已收到`。 |
| MC-DM-FILE-02 | DM | 连续发送文字说明和文件；SeaTalk Web 会拆成一条 text 和一条 file | split(text, file) | Hermes 能分别处理拆分后的文字消息和文件消息；不要求同一事件同时包含 text 与 file | PASS：2026-05-07 15:55，在 `Xiaoyu No.2` DM 发送文字 `MC-DM-FILE-02 text caption...` 加 `MC-DM-FILE-02.txt`；SeaTalk 拆分后 Hermes 同一 DM 分别确认文本和文件附件。 |
| MC-GRP-TXT-01 | Group | 授权用户在授权群发送文本，按配置 @bot | text | Hermes 回复同一群，source 为 group | PASS：2026-05-07 15:20，在 `OpenClaw Testing` 通过 SeaTalk mention 候选生成真实 `@ Xiaoyu No.2` token 后发送；Hermes 同一群回复 `MC-GRP-TXT-01 / message type: text / quote: no / forward: no / attachment: no / group thread context not available`。15:14 的纯文本 `@Xiaoyu No.2` 未触发，可作为操作差异参考。 |
| MC-GRP-LONG-01 | Group | 授权用户在授权群发送超过 10k 字文本，首尾分别放 `LONG_GRP_IN_START` / `LONG_GRP_IN_END` | long text | Hermes 不崩溃；响应回同一群，并能确认首尾 marker 或说明截断位置 | NA: SeaTalk UI 不支持发送长消息。 |
| MC-GRP-IMG-01 | Group | 授权用户在授权群直接发送图片，不 quote、不在 thread 中 @bot | image | 不作为 group 图片入站能力判定；用于确认直接图片不会让 bot 自动读取历史 media | PASS：2026-05-07 15:57，在 `OpenClaw Testing` 通过真实 `@ Xiaoyu No.2` mention token 加合成 PNG 发送；Hermes 未确认图片附件，符合 group 直接 media 默认不可见的新口径。 |
| MC-GRP-IMG-02 | Group | 授权用户在授权群连续发送文字说明和图片；SeaTalk Web 会拆成 text 与 image | split(text, image) | 只有 text/mention 可触发 Hermes；image 不应被视为同一条消息附件，需用 `MC-GRP-Q-IMG-TRIGGER-01` 或 `MC-THR-GRP-IMG-TRIGGER-01` 验证图片可见性 | PASS：2026-05-07 15:59，Hermes 同一群确认文字进入，但明确无图片可见；按拆分与 group media 默认不可见口径通过。 |
| MC-GRP-FILE-01 | Group | 授权用户在授权群直接发送文件，不 quote、不在 thread 中 @bot | file | 不作为 group 文件入站能力判定；用于确认直接文件不会让 bot 自动读取历史 media | PASS：2026-05-07 16:01，SeaTalk 显示文件卡片，但 Hermes 未确认文件附件，符合 group 直接 file 默认不可见的新口径。 |
| MC-GRP-FILE-02 | Group | 授权用户在授权群连续发送文字说明和文件；SeaTalk Web 会拆成 text 与 file | split(text, file) | 只有 text/mention 可触发 Hermes；file 不应被视为同一条消息附件，需用 `MC-GRP-Q-FILE-TRIGGER-01` 或 `MC-THR-GRP-FILE-TRIGGER-01` 验证文件可见性 | PASS：2026-05-07 16:04，Hermes 同一群确认文字进入，但明确无文件可见；按拆分与 group file 默认不可见口径通过。 |
| MC-THR-TXT-01 | Group Thread | 在群 thread 中发送文本 | text + thread | Hermes 回复同一 thread | PASS：2026-05-08 15:03，在 Chrome `OpenClaw Testing` 中对群文件 `MC-GRP-FILE-02.txt` 打开 replying thread，在线程输入区发送含真实 `@Xiaoyu No.2` token 的文本 `MC-THR-GRP-FILE-TRIGGER-01`；Hermes 在线程内回复，确认 `thread: yes`。 |
| MC-THR-LONG-01 | Group Thread | 在群 thread 中发送超过 10k 字文本，首尾分别放 `LONG_THR_IN_START` / `LONG_THR_IN_END` | long text + thread | Hermes 不崩溃；响应回同一 thread | PENDING：2026-05-08 16:12，在 `MC-THR-ROOT-01` thread 中用真实 `@Xiaoyu No.2` token 尝试粘贴 21,582 bytes 长文本；SeaTalk Web 编辑器只保留约 5,053 chars，到 line 0042 且缺失 `LONG_THR_IN_END`，未发送。需要支持 >10k thread 输入的客户端/API 或人工可确认的输入路径。 |
| MC-THR-IMG-01 | Group Thread | 在群 thread 中发送图片后 @bot，或在图片消息 thread 中 @bot | image + thread mention | 图片进入 Hermes，回复不离开 thread | FAIL：2026-05-08 16:35-16:36，在 `MC-THR-ROOT-01` thread 内发送两次 PNG 图片（1x1 PNG 与 canvas 生成的 64x64 PNG）；Hermes 均在同 thread 返回 `HTTP 400: The image data you provided does not represent a valid image`，未能确认图片附件正常进入模型。 |
| MC-THR-FILE-01 | Group Thread | 在群 thread 中发送文件后 @bot，或在文件消息 thread 中 @bot | file + thread mention | 文件进入 Hermes，回复不离开 thread | PASS：2026-05-08 15:03，在 Chrome `OpenClaw Testing` 中对群文件 `MC-GRP-FILE-02.txt` 打开 replying thread，在线程输入区通过 SeaTalk mention 候选生成真实 `@Xiaoyu No.2` token 后发送 `MC-THR-GRP-FILE-TRIGGER-01`；Hermes 在线程内回复 `type: group file root / thread: yes / attachment: yes`。 |

## 4. Quote 矩阵

| ID | 会话 | 操作 | 被引用消息 | 新消息 | 预期 | 验证结果 |
| --- | --- | --- | --- | --- | --- | --- |
| MC-DM-Q-TXT-01 | DM | reply/quote 一条文本 | text | text | Hermes 输入含 quoted 文本前缀和新文本 | PASS：2026-05-08，在 `Xiaoyu No.2` DM quote 文本根消息 `MC-DM-Q-TXT-ROOT-01` 后发送 `MC-DM-Q-TXT-01`；Hermes 回复 `type: text / quote: yes`。 |
| MC-DM-Q-IMG-01 | DM | quote 一张图片 | image | text | Hermes 输入含 quote 语义，并包含 quoted image media | PASS：2026-05-08，先用有效 PNG `MC-DM-Q-IMG-ROOT-02.png` 建立图片根消息，再 quote 图片发送 `MC-DM-Q-IMG-01-RETRY2`；Hermes 回复 `type: image / quote: yes / attachment: yes`。早期 1x1 PNG 因测试素材无效触发 `invalid image data`，不计入能力失败。 |
| MC-DM-Q-FILE-01 | DM | quote 一个文件 | file | text | Hermes 输入含 quote 语义，并包含 quoted file media | PASS：2026-05-08，在 `Xiaoyu No.2` DM 上传并 quote `MC-DM-Q-FILE-ROOT-01.txt` 后发送 `MC-DM-Q-FILE-01`；Hermes 回复 `type: file / quote: yes / attachment: yes`。 |
| MC-DM-Q-TXT-IMG-01 | DM | quote 文本后发送图片 | text | image | quote 文本和新图片都进入 Hermes | PENDING：需要可稳定执行 quote 操作后再上传图片。 |
| MC-DM-Q-IMG-FILE-01 | DM | quote 图片后发送文件 | image | file | quoted image 和新文件都不丢失 | PENDING：需要可稳定执行图片 quote 操作后再上传文件。 |
| MC-GRP-Q-TXT-01 | Group | 在群中 quote 文本并 @bot | text | mention text | Hermes 回复同一群，quote 前缀存在 | PASS：2026-05-08 14:52，在 Chrome `OpenClaw Testing` 中 quote 文本 `MC-GRP-FILE-02 text caption...`，通过 SeaTalk mention 候选生成真实 `@Xiaoyu No.2` token（编辑器 HTML 含 `seatalk_mention-item_container data-key=1015224 data-label=Xiaoyu No.2`）后发送 `MC-GRP-Q-TXT-01-RETRY6`；Hermes 同群回复 `type: text / quote: yes`。此前 `Debug Agent` 尝试为错误 bot，不计入本用例结果。 |
| MC-GRP-Q-IMG-01 | Group | 在群中 quote 图片并 @bot | image | mention text | quote 图片 media 进入 Hermes | PASS：2026-05-08 14:54，在 Chrome `OpenClaw Testing` 中 quote 既有群图片消息，真实 @ `Xiaoyu No.2` 后发送 `MC-GRP-Q-IMG-TRIGGER-01`；Hermes 同群回复 `type: image / quote: yes / attachment: yes`。 |
| MC-GRP-Q-FILE-01 | Group | 在群中 quote 文件并 @bot | file | mention text | quote 文件 media 进入 Hermes | PASS：2026-05-08 14:58，在 Chrome `OpenClaw Testing` 中 quote 既有群文件 `MC-GRP-FILE-02.txt`，通过 SeaTalk mention 候选生成真实 `@Xiaoyu No.2` token（编辑器 HTML 含 `seatalk_mention-item_container data-key=1015224 data-label=Xiaoyu No.2`，且无 `Debug Agent`）后发送 `MC-GRP-Q-FILE-TRIGGER-01`；Hermes 同群回复 `type: file / quote: yes / attachment: yes`。 |
| MC-GRP-Q-IMG-TRIGGER-01 | Group | 先发送图片，再 quote 该图片并 @bot | image | quote(image) + mention text | Hermes 能看到 quoted image media，回复同一群并确认测试编号和附件类型 | PASS：2026-05-08 14:54，quote 既有群图片 root 后真实 @ `Xiaoyu No.2` 发送；Hermes 回复 `MC-GRP-Q-IMG-TRIGGER-01 / type: image / quote: yes / attachment: yes`。 |
| MC-GRP-Q-FILE-TRIGGER-01 | Group | 先发送文件，再 quote 该文件并 @bot | file | quote(file) + mention text | Hermes 能看到 quoted file media，回复同一群并确认测试编号和附件类型 | PASS：2026-05-08 14:58，在 Chrome `OpenClaw Testing` 中 quote 既有群文件 `MC-GRP-FILE-02.txt`，真实 @ `Xiaoyu No.2` 后发送；Hermes 回复 `MC-GRP-Q-FILE-TRIGGER-01 / type: file / quote: yes / attachment: yes`。 |
| MC-THR-Q-TXT-01 | Group Thread | 在 thread 中 quote 文本 | text in thread | text | Hermes 回复同一 thread，quote 前缀存在 | PASS：2026-05-08 16:31，在 `MC-THR-ROOT-01` thread 内右键文本消息并选择 `Quote`，编辑器显示 quote preview；随后用真实 `@Xiaoyu No.2` token 发送 `MC-THR-Q-TXT-01`。Hermes 同 thread 回复 `quote: yes / thread: yes`。 |
| MC-THR-Q-IMG-01 | Group Thread | 在 thread 中 quote 图片 | image in thread | text | quote 图片进入 Hermes，thread 保持 | FAIL：2026-05-08 16:38，在 `MC-THR-ROOT-01` thread 内 quote 16:36 图片消息，编辑器显示 `[Image]` quote preview，并用真实 `@Xiaoyu No.2` token 发送 `MC-THR-Q-IMG-01`；Hermes 同 thread 返回 `HTTP 400: The image data you provided does not represent a valid image`，未返回 `attachment: yes`。 |
| MC-THR-Q-FILE-01 | Group Thread | 在 thread 中 quote 文件 | file in thread | text | quote 文件进入 Hermes，thread 保持 | PASS：2026-05-08 16:32-16:34，在 `MC-THR-ROOT-01` thread 内通过 thread 文件输入发送 `MC-THR-Q-FILE-01.txt`；随后右键该文件消息选择 `Quote`，用真实 `@Xiaoyu No.2` token 发送 `MC-THR-Q-FILE-01`。Hermes 同 thread 回复 `quote: yes / attachment: yes / thread: yes`。 |
| MC-Q-DEDUP-01 | DM 或 Group | 5 秒内连续发送两条都 quote 同一消息 | same text | text + text | Hermes 合并输入中同一 quote 只出现一次 | PENDING：依赖 quote 操作入口和连续消息控制。 |
| MC-Q-MULTI-01 | DM 或 Group | 5 秒内连续发送两条分别 quote 不同消息 | text A / text B | text + text | Hermes 合并输入中两个 quote 都出现 | PENDING：依赖 quote 操作入口和连续消息控制。 |
| MC-Q-MISSING-01 | DM 或 Group | quote 一条已删除或不可读取消息 | unavailable | text | 新文本仍进入 Hermes，不因 quote 解析失败丢弃 | PENDING：需要可删除/不可读消息样本和 quote 操作入口。 |

## 5. Forward 矩阵

| ID | 会话 | 操作 | 转发内容 | 预期 | 验证结果 |
| --- | --- | --- | --- | --- | --- |
| MC-DM-FWD-TXT-01 | DM | 转发单条文本 | text | Hermes 输入含 `[Forwarded messages]` 和文本 | PASS：2026-05-08 16:55-16:59，在 `OpenClaw Testing` 发送源文本 `MC-DM-FWD-TXT-01 source group text...`，通过 SeaTalk `Forward` 单条转发到 `Xiaoyu No.2` DM；Hermes 在 DM 回复 `MC-DM-FWD-TXT-01 / forward: yes / source text visible: yes`。 |
| MC-DM-FWD-MTXT-01 | DM | 转发多条文本 | text[] | 所有文本按行进入 Hermes | PASS：2026-05-08 19:39，在 `OpenClaw Testing` 多选两条纯文本 comment（`MC-GRP-FWD-IMG-01 forward image to group...` 与 `MC-GRP-FWD-FILE-01 forward file to group...`）Forward 到 `Xiaoyu No.2` DM；Hermes 回复 `forward: yes / text count 2: yes / both marker texts visible: yes`。 |
| MC-DM-FWD-IMG-01 | DM | 转发图片 | image | Hermes 输入含 forward 语义，图片 media 不丢失 | PASS：2026-05-08 17:11-19:23，在 `OpenClaw Testing` 发送 canvas PNG 图片源消息，SeaTalk `Forward` 到 `Xiaoyu No.2` DM，并在 forward comment 中携带编号；Hermes 在 DM 回复 `forward: yes / attachment: yes / image text visible: yes`。 |
| MC-DM-FWD-FILE-01 | DM | 转发文件 | file | Hermes 输入含 forward 语义，文件 media 不丢失 | PASS（带限制）：2026-05-08 17:06-17:10，在 `OpenClaw Testing` 发送 `MC-DM-FWD-FILE-01.txt` 后 Forward 到 `Xiaoyu No.2` DM。首次无 comment 转发时 Hermes 只确认收到文档附件；重试在 forward comment 中加入编号后，Hermes 回复 `forward: yes / attachment: yes / file name visible: no`。附件未丢失，但 forward 文件名/内容当前不可见。 |
| MC-DM-FWD-MIX-01 | DM | 转发文本、图片、文件组成的多选记录 | forwarded text[] + image[] + file[] | 所有 forward 条目都进入 Hermes；不要求原始消息是 text + media 混发 | FAIL：2026-05-08 19:36，在 `OpenClaw Testing` 多选 forwarded image、forwarded file `MC-DM-FWD-FILE-01.txt` 和纯文本 comment 后 Forward 到 `Xiaoyu No.2` DM；SeaTalk DM 中可见 file 与 text/comment 到达，但 Hermes 返回 `HTTP 400: The image data you provided does not represent a valid image`，混合 forward 中图片解析失败。 |
| MC-DM-FWD-SENDER-01 | DM | 转发带原发送者的多条文本 | sender + text[] | 每条文本保留发送者前缀 | PENDING：需要稳定多选/转发 UI，并准备不同原发送者消息。 |
| MC-GRP-FWD-TXT-01 | Group | 在群中转发文本 | text | Hermes 回复同一群，forward 文本存在 | PASS：2026-05-08 17:03-17:05，先在 `Xiaoyu No.2` DM 发送源文本 `MC-GRP-FWD-TXT-01 source DM text...`，SeaTalk `Forward` 到 `OpenClaw Testing`；forward 到群后未直接触发 bot，随后 quote 该 forwarded message 并真实 @ `Xiaoyu No.2`，Hermes 同群回复 `forward yes / quote yes / source text visible yes`。 |
| MC-GRP-FWD-IMG-01 | Group | 在群中转发图片并 @bot 或转发后 quote/thread @bot | image | 图片 media 不丢失 | PASS：2026-05-08 19:25-19:28，将 `Xiaoyu No.2` DM 中的图片消息 Forward 到 `OpenClaw Testing`，随后在群内 quote 该 forwarded image 并真实 @ `Xiaoyu No.2`；Hermes 同群回复 `forward yes / quote yes / attachment yes / image text visible yes`。 |
| MC-GRP-FWD-FILE-01 | Group | 在群中转发文件并 @bot 或转发后 quote/thread @bot | file | 文件 media 不丢失 | PASS（带限制）：2026-05-08 19:31-19:32，将 `Xiaoyu No.2` DM 中的 `MC-DM-FWD-FILE-01.txt` Forward 到 `OpenClaw Testing`，随后在群内 quote 该 forwarded file 并真实 @ `Xiaoyu No.2`；Hermes 同群回复 `forward yes / quote yes / attachment yes / file name visible no`。附件未丢失，但 forward 文件名当前不可见。 |
| MC-GRP-FWD-MIX-01 | Group | 在群中转发文本、图片、文件混合记录 | forwarded text + image + file | 所有元素在 forward 结构中进入 Hermes；如果转发产物被 SeaTalk 拆分，按拆分后的 forward 条目逐项验证 | PENDING：需要稳定群多选/合并转发 UI；已确认基础 forward 入口可执行。 |
| MC-THR-FWD-TXT-01 | Group Thread | 在 thread 中转发文本 | text | Hermes 回复同一 thread | PENDING：需要可稳定进入 group thread 并执行 Forward。 |
| MC-THR-FWD-IMG-01 | Group Thread | 在 thread 中转发图片 | image | 图片进入 Hermes，thread 保持 | PENDING：需要可稳定进入 group thread 并执行图片 Forward。 |
| MC-THR-FWD-FILE-01 | Group Thread | 在 thread 中转发文件 | file | 文件进入 Hermes，thread 保持 | PENDING：需要可稳定进入 group thread 并执行文件 Forward。 |
| MC-FWD-NEST-01 | DM 或 Group | 转发“合并转发记录中的嵌套列表” | nested text[] | 嵌套文本被展开，不出现空响应 | PENDING：需要准备嵌套合并转发消息样本并执行 Forward。 |
| MC-FWD-NEST-02 | DM 或 Group | 转发“转发记录里还有转发记录” | forwarded(forwarded text) | 内层 forward 文本可见，保留 forward 语义 | PENDING：需要准备二层 forward 样本并执行 Forward。 |
| MC-FWD-NEST-MEDIA-01 | DM 或 Group | 转发嵌套记录，内层含图片和文件 | nested image + file | 内层 media 不丢失；Group 中需通过 quote/thread @bot 触发 bot 可见性 | PENDING：需要准备含媒体的嵌套 forward 样本；已确认基础 forward 入口可执行。 |

## 6. Quote 与 Forward 组合矩阵

| ID | 会话 | 操作 | 组合 | 预期 | 验证结果 |
| --- | --- | --- | --- | --- | --- |
| MC-DM-QF-01 | DM | quote 一条转发文本后回复 | quote(forward text) + text | Hermes 输入同时含 quote 和 forward 内容 | PENDING：依赖稳定 quote + forward UI 和预置 forward 样本。 |
| MC-DM-QF-02 | DM | quote 一条转发图片后回复 | quote(forward image) + text | forward image media 不丢失 | PENDING：依赖稳定 quote + forward UI 和预置图片 forward 样本。 |
| MC-DM-FQ-01 | DM | 转发一条带 quote 的文本消息 | forward(quote text + text) | Hermes 输入可见转发文本及其中 quote 语义 | PENDING：依赖稳定 quote/forward UI 和预置 quote 样本。 |
| MC-DM-FQ-02 | DM | 转发一条带 quote 图片的消息 | forward(quote image + text) | quote image media 不丢失 | PENDING：依赖稳定 quote/forward UI 和预置图片 quote 样本。 |
| MC-GRP-QF-01 | Group | 在群中 quote 转发消息后回复 | quote(forward text) + text | Hermes 回复群，quote + forward 内容存在 | PASS：2026-05-08 17:05，在 `OpenClaw Testing` quote 由 `Xiaoyu No.2` DM 转发来的 `MC-GRP-FWD-TXT-01` 文本，并真实 @ `Xiaoyu No.2`；Hermes 同群回复 `MC-GRP-FWD-TXT-01, forward yes, quote yes, source text visible yes`。 |
| MC-GRP-QF-02 | Group | 在群中 quote 转发媒体消息后 @bot | quote(forward image/file) + mention text | quoted forward media 不丢失 | PENDING：依赖稳定群 quote/forward UI；2026-05-08 已确认基础 quote 和 forward 入口可执行，group media 可见性按 quote 触发路径验证。 |
| MC-GRP-FQ-01 | Group | 在群中转发带 quote 的文本消息 | forward(quote text + text) | forward 内的 quote 信息可见或至少文本不丢 | PENDING：依赖稳定群 quote/forward UI 和预置 quote 样本。 |
| MC-THR-QF-01 | Group Thread | 在 thread 中 quote 转发文本后回复 | thread + quote(forward text) | Hermes 回复同一 thread，内容完整 | PENDING：依赖稳定 group thread、quote 和 forward UI。 |
| MC-THR-QF-02 | Group Thread | 在 thread 中 quote 转发媒体后 @bot | thread + quote(forward media) + mention | thread 保持，media 不丢失 | PENDING：依赖稳定 group thread、quote、forward 和 media UI；2026-05-08 已确认 replying thread、quote 和 forward 入口可执行。 |
| MC-THR-FQ-01 | Group Thread | 在 thread 中转发带 quote 的消息 | thread + forward(quote text) | thread 保持，forward/quote 文本可见 | PENDING：依赖稳定 group thread、quote 和 forward UI。 |

## 7. Thread 组合矩阵

| ID | 会话 | 操作 | 组合 | 预期 | 验证结果 |
| --- | --- | --- | --- | --- | --- |
| MC-THR-ROOT-01 | Group | 在群主消息触发 Hermes 后进入 thread 回复 | group root -> thread | 后续 thread 消息进入同一 thread session | PASS：2026-05-08 16:05，在 `OpenClaw Testing` 先用真实 `@Xiaoyu No.2` token 发送群主消息，Hermes 群内回复 `MC-THR-ROOT-01 / root: yes`；随后进入该消息 replying thread 发送真实 mention 的 `MC-THR-ROOT-01-THREAD`，Hermes 在同一 thread 回复 `thread: yes`。 |
| MC-THR-ROOT-02 | Group Thread | 在 thread 中连续发送两条文本 | text + text within debounce | Hermes 合并同一 thread 内连续文本 | PASS（带限制）：2026-05-08 16:07-16:08，在 `MC-THR-ROOT-01` 的同一 thread 内连续发送 `part 1/2 order=A` 与 `part 2/2 order=B`，两条都使用真实 `@Xiaoyu No.2` token；Hermes 在线程内回复 `MC-THR-ROOT-02 / merged: yes / order A then B: yes / thread: yes`。限制：自动化操作间隔超过 5 秒，严格 debounce 边界仍建议人工或更快脚本补跑。 |
| MC-THR-ISO-01 | Group Thread | 同一群不同 thread 各发送一条文本 | thread A / thread B | 不同 thread 不串 session | PENDING：需要两个稳定 group thread 目标。 |
| MC-THR-USER-01 | Group Thread | 同一 thread 不同授权用户发送文本 | user A / user B | 按当前 session 策略可区分或合并，日志中 user_id 正确 | PENDING：需要第二个授权个人账号和可稳定 thread。 |
| MC-THR-Q-ROOT-01 | Group Thread | 在 thread 中 quote 群主会话消息 | quote root message | quote 内容进入 thread 输入，回复仍在 thread | PENDING：2026-05-08 已确认 quote 与 replying thread 入口可执行；尚未发送带编号验证消息。 |
| MC-THR-FWD-ROOT-01 | Group Thread | 在 thread 中转发群主会话消息 | forward root message | forward 内容进入 thread 输入，回复仍在 thread | PENDING：2026-05-08 已确认 forward 与 replying thread 入口可执行；尚未发送带编号验证消息。 |
| MC-THR-GRP-IMG-TRIGGER-01 | Group Thread | 先发送群图片，再进入该图片 replying thread 并 @bot | image root -> thread mention | Hermes 能看到 thread root image，回复保留在 thread | PENDING：新增用例；2026-05-08 已确认 `reply-in-thread` 入口可打开，尚未在图片消息上执行。 |
| MC-THR-GRP-FILE-TRIGGER-01 | Group Thread | 先发送群文件，再进入该文件 replying thread 并 @bot | file root -> thread mention | Hermes 能看到 thread root file，回复保留在 thread | PASS：2026-05-08 15:03，在群文件 `MC-GRP-FILE-02.txt` 的 replying thread 中真实 @ `Xiaoyu No.2` 发送；Hermes 在线程内回复 `id: MC-THR-GRP-FILE-TRIGGER-01 / type: group file root / thread: yes / attachment: yes`。 |
| MC-THR-MEDIA-MIX-01 | Group Thread | 在 thread 中连续发文本、图片、文件；SeaTalk 可能拆成多条 thread 消息 | split(text, image, file) within thread | 同一 thread 内内容完整，media 不丢失；按拆分后的多条消息逐项验证 | PENDING：需要可稳定 thread；group media/file 可见性优先用 `MC-THR-GRP-IMG-TRIGGER-01` / `MC-THR-GRP-FILE-TRIGGER-01` 验证。 |

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
| MC-EDGE-LONG-01 | DM 或 Group | 发送接近 4000 字文本 | Hermes 正常接收，回复不报错 | PASS：2026-05-08 16:24，在 `OpenClaw Testing` 的 `MC-THR-ROOT-01` thread 中用真实 `@Xiaoyu No.2` token 发送约 4.1k chars 文本，含 `EDGE_LONG_START` / `EDGE_LONG_END`；Hermes 同 thread 回复 `long-ish text: yes / start marker: yes / end marker: yes / thread: yes`。备注：16:23 有一次同编号截断重试也收到 marker 确认，但以 16:24 完整回包为准。 |
| MC-EDGE-MEDIA-FAIL-01 | DM 或 Group | 发送无法下载或权限失效的图片 | 文本占位 `<media:image>` 可见，gateway 记录 media error | PENDING：需要制造 SeaTalk media 下载失败或查看 gateway 日志；当前 Web UI 只能发送正常上传图片。 |
| MC-EDGE-MEDIA-FAIL-02 | DM 或 Group | 发送无法下载或权限失效的文件 | 文本占位 `<media:document>` 可见，gateway 记录 media error | PENDING：需要制造 SeaTalk media 下载失败或查看 gateway 日志；当前 Web UI 只能发送正常上传文件。 |
| MC-EDGE-UNSUP-01 | DM 或 Group | 发送 SeaTalk 支持但 plugin 未支持的消息类型 | Hermes 输入含 `<unsupported:...>` 或日志可定位，不崩溃 | PENDING：需要明确一个当前 plugin 未支持且 SeaTalk Web 可发送的消息类型，并可观察 Hermes/gateway 日志。 |
| MC-EDGE-DUP-01 | DM 或 Group | 通过重发或 relay/webhook 双投制造同 event id | Hermes 只处理一次 | PENDING：需要 webhook/relay 层双投同 event id，不能仅通过 SeaTalk Web 构造。 |
| MC-EDGE-BURST-01 | DM 或 Group | 5 秒内连续发送 3 条文本 | Hermes 合并为一次输入，文本顺序正确 | PENDING：2026-05-07 16:12 尝试自动连续发送失败，仅第一条 `MC-EDGE-BURST-01 part 1/3 order=A` 发出并收到普通文本回包，后续文本停留在输入框后已清空；该次不满足 burst 条件，需人工或更可靠脚本重跑。 |
| MC-EDGE-BURST-MEDIA-01 | DM 或 Group | 短时间连续发送文本、图片、文本 | 按 SeaTalk 拆分后的多条消息验证顺序；DM 图片不丢失，Group 图片需 quote/thread @bot 后验证可见性 | PENDING：需要可靠连续发送控制；建议先在 DM 重跑，再用 group quote/thread 路径补充 media 可见性。 |

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

`MC-DM-TXT-01`、`MC-DM-LONG-01`、`MC-DM-IMG-02`、`MC-DM-FILE-02`、`MC-GRP-TXT-01`、`MC-GRP-LONG-01`、`MC-GRP-IMG-02`、`MC-GRP-FILE-02`、`MC-GRP-Q-IMG-TRIGGER-01`、`MC-GRP-Q-FILE-TRIGGER-01`、`MC-THR-TXT-01`、`MC-THR-LONG-01`、`MC-THR-GRP-IMG-TRIGGER-01`、`MC-THR-GRP-FILE-TRIGGER-01`、`MC-DM-Q-TXT-01`、`MC-DM-Q-IMG-01`、`MC-DM-FWD-MIX-01`、`MC-FWD-NEST-02`、`MC-DM-QF-02`、`MC-THR-QF-02`、`MC-THR-ISO-01`、`MC-AUTH-GRP-04`、`MC-EDGE-MEDIA-FAIL-01`、`MC-EDGE-BURST-MEDIA-01`、`MC-OUT-DM-TXT-01`、`MC-OUT-DM-LONG-01`、`MC-OUT-THR-TXT-01`、`MC-OUT-THR-LONG-01`。
