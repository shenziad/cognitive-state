# A-v2 传输中断后的恢复边界审查备忘录

日期：2026-10-04。状态：**非冻结审查建议，不授权旧 run 重试，不表示恢复已执行**。

## 1. 已核验的中断事实

只读检查 `results/raw/cycle5/mechanism_v2_20261004` 的 manifest、准备分配 ID、请求状态与 usage；没有阅读表示内容、行为评分或 `.env`，没有调用 API。

- manifest 为 `aborted_api_error`，72 个分配中保存 31 个 preparation records；其中包含无模型调用的 Full/CS-text，不是 31 个行为样本。
- 26 个 attempts：25 个 response 与 1 个 API error；已知 provider Tokens 为 **78,153**，错误尝试的用量未知。因此本轮完整总 Tokens 未知。
- 最后安全错误记录为 `RuntimeError / provider_request_failed / http_status=null`。它不足以确认余额、限流、连接、超时或响应格式中的任一种原因。
- 没有 `results.json`，没有 A 执行器行为，也尚未完成全体来源审阅 gate。
- 现有 v2 冻结的 97 份资产逐文件 hash 检查通过。旧 run 和冻结文件均未修改。

当前只能报告设施中断、部分提取及已花成本，不能报告完整 A 性能，也不能将中断当作 Cognitive State 的语义负面结果。

## 2. “不自动恢复”的准确边界

冻结的 [v2 修订](cycle5_budget_amendment_v2.md) 明确规定：API/未知用量或设施失效时停止，不自动继续、补跑失败条件或扩大预算。[原执行前规范](cycle5_protocol_v01.md)同时规定：“中断后的完整恢复要另立事前计划并保留原轮，不拼接样本。”v2 release 还保存 `no_automatic_recovery_or_D_concatenation=true`。

因此，不能直接再次调用旧 run 的 `prepare`，把 manifest 改为 `prepared`，忽略错误请求，补剩下 41 个记录，或把旧 31 个表示注入新 run 后称为同一完整 A-v2。这些都会绕过冻结的停止条件或拼接样本。也不能给某一个条件加传输重试并把其额外/未知成本从比较中删除。

但这不是永久禁止继续研究。用户已授权继续本阶段研究和真实模型调用；在该持续授权下，可以完成一个新的、可审计的恢复计划、验证并冻结后执行 **一次有界的完整 A-v3 重启**。这是明确的新版本工作，既不是 SDK 自动 retry，也不是将旧 gate 追溯改为通过。规则来源是已冻结研究协议，不能把它误说成必须用户再次批准每次 API 请求的权限要求。

## 3. 建议的最小完成路径

### 3.1 先保存原轮及安全诊断

保存原 manifest、config、prepared、call ledger、task order、executor schedule 和执行 release 的 hash；原 A-v2 永久标为中断。将 31 个准备记录按实际产生情况索引，未完成来源标注不能冒称正确，也不选择其中“最好”的状态。

独立建立一次极小的同模型 SDK 服务探测，最大一次真实请求、零 SDK retry、低输出上限，不把模型响应内容或 key 打印到用户。只记录 allowlisted SDK 错误类别、HTTP status、usage/response ID 是否可得及模型/传输元数据。费用另入 campaign，不能算作某条件的任务成绩。

探测成功只说明当时小请求可用，不能保证大请求或接下来的 72 分配稳定。探测失败则停止依赖服务的恢复，完成离线审查与中断报告；根据明确错误处理凭据/额度/连接等实际阻断，不猜原因或循环探测。

现有客户端会把 SDK 异常转换为安全 `RuntimeError`，外层又只记录其类别与有限 HTTP 值，导致原 SDK 类别可能丢失。若需要改善错误诊断，在新 v3 transport/recording 文件中按 allowlist 提取类别或记录已有安全前缀；不能编辑已冻结 `src/llm/client.py`，也不保存任意 exception body、请求 header 或凭据。诊断的改善不应改变成功请求的模型、消息、参数与输出解析语义。

### 3.2 在任何新 A 请求前冻结恢复计划

建议新 ID 为 `cycle5-mechanism-transport-recovery-v3`，使用全新目录和 release。事前声明：

1. 旧 A-v2 保持中断，D 保持原未完成状态，原 gate failed；完整 24-cell 事前反事实子层工程 gate 可继续作为共同输入依据，无需重跑 D。
2. A 十二成员、六条件、提示、评分、表示预算、编码修复、调用上限、输出上限、模型、温度、thinking、顺序规则和 CS-text 转换保持原样，不根据旧 31 个表示内容调语义设计。
3. 不继承旧 31 个表示、planner 或 organizer；从全部原始公开输入重新准备 72 个分配，再对全部 60 份来源条目完成来源先行审阅，之后才执行 72 个分配。
4. 一次完整重启，不逐条件补跑、不选择性生成成功源。所有新 encoding/behavior failures留在新分母；CS1 源失败时两相关条件共同保留失败。
5. 新 run 仍然零隐式 retry；明确 API/unknown usage/设施失效和预算停止规则。此次有界恢复再次失败后不无限建立相同恢复版本，应先获得服务问题的可验证修复证据，再提出新的工作决定。
6. 恢复预算事前独立写清。可沿用 A 请求 cap 400、Tokens 阈值 750,000；这是新完整 run 的显式预算，**不改变旧 v2 的预算，也不表示 campaign 总支出仍受旧单轮阈值约束**。若决定按剩余 campaign 预算约束，则先把旧 78,153 已知 Tokens 和探测费用计入，并冻结新阈值；旧一次未知用量使严格总费用仍无法保证。不能在恢复结果出现后扩大阈值。
7. 记录旧中断数据、探测、恢复计划、代码和新 release 的来源 hash。SDK、base URL、调用设置及正常响应 metadata 与原设计一致，任何运输/错误日志变化单列；若须改变 timeout 等请求配置，同样在 v3 事前披露，不能说“完全相同执行版本”。

建立恢复文档与冻结资产是可以先完成的具体工作。源代码/配置/文件 hash 和最小离线生命周期测试通过之后，再发送新 run 的第一条请求；此备忘录本身不是恢复 gate。

### 3.3 报告方式

旧 A-v2 的 31 个准备记录及 26 个 attempts 单独报告，不和 A-v3 分母合并，也不替代缺失项。完整 A-v3 若成功，行为成绩、来源正确性、提取有效率与各策略成本由新 run 全分配得出。

全 campaign 实际调用包括 D 的 113、旧 A-v2 的 26、独立探测与新恢复 run。已知成本可给小计；旧 A-v2 一次 unknown usage 继续使完整 campaign 总 Tokens 未知，不用估计或零填补。策略部署成本和 campaign 沉没成本分表；共享 CS 源在真实账本只计一次，两策略归属仍各计完整源提取。

此恢复过程在已产生开发输出之后声明，不能称原协议的无中断执行或纯事前验证。保留事前锁定的比较设计仍能给出开发机制诊断，但不能抹去此次设施选择、单次条件、简单二选一任务与助手审阅的限制。

## 4. 不建议采用的快捷路径

- 将旧 31 个表示与剩余新表示拼成 72 个完整 A-v2，省掉完整重新生成的代价。
- 只重试最后的 planner 或只给失败条件增加重试机会。
- 服务故障时换模型、改提示、降低输出预算后合并到原比较。
- 先读部分表示质量，再挑任务、状态或恢复顺序。
- 将错误尝试的费用记零或从任何实际花费账本删除。
- 多次 probe/restart 直到成功，最后只报告最后一次正常结果。

若将来专门研究“跨运行复用已生成状态”或有界传输 retry，它们可以成为另立版本的部署策略；本次冻结比較没有包含这些策略，不能作为隐含恢复行为。

## 5. 审查结论

**一次独立的小服务诊断已完成，可在新 V3 冻结验证后执行一次完整 A-v3 恢复。** 用户持续研究授权与原协议允许另立完整恢复计划相容；需要保留的是停止规则、版本和数据诚实性，而不是永久停止研究。小探测成功不保证后续稳定；若恢复再次失败，仍须按已声明规则停止。

## 6. V3 实际资产的追加只读核验

在 A-v3 第一条模型调用前，读取并对照了以下新文件：

- 恢复计划：`docs/cycle5_recovery_v3.md`。
- 配置：`configs/cycle5_mechanism_v3.json`。
- 运行器：`experiments/exp004_mechanism/runtime_v3.py`。
- 入口/分析/冻结：`scripts/run_cycle5_v3.py`、`scripts/analyze_cycle5_v3.py`、`scripts/freeze_cycle5_v3.py`。
- 独立探测记录：`results/raw/cycle5/service_probe_20261004.json`，只读取 status、model、attempts、usage 等安全元数据，没有读取或输出响应文本。

核验结果：

1. v3 config 相对 v2 **仅** `execution_version`、`experiment_id`、`config_path` 三项身份变化。task IDs、六条件、提示路径、incoming 配对子层 gate、400 请求上限、750,000 Tokens 停止阈值、6000 bytes、四步、60 秒及其他请求配置完全一致。
2. `runtime_v3.py` 相对 v2 的完整文本差异 **仅** release 路径由 `cycle5_execution_v2.json` 改为 `cycle5_execution_v3.json`。没有来源、语义、行为、错误处理或传输 retry 变化。
3. 初始化仍要求全新输出目录 `exist_ok=False`，prepare 从空 records/ledger 开始；不读取或注入旧 A-v2 的 31 个准备表示。保留原 StopRun 停止路径；恢复计划明确再次失败整阶段停止，没有追加恢复授权。
4. 一次服务探测记录为 `response_received`，`request_attempts=1`、`total_tokens=10`、`unknown_usage_attempts=0`。它是另一个独立记录，不属于新 A 分配。
5. 恢复计划正确保留旧 A-v2 的一次 unknown usage、原 D 未完成/旧 gate failed，约定新 72 分配和全体 60 来源审阅，并明确保护旧资产、旧 A 输出及探测来源。

根执行者报告新复制版本与原机制/运行器 20 项离线测试通过，冻结脚本将保护原 97 份 V2 资产、旧 A 输出及探测。此备忘录未重新调用模型；上述实际文件核验足以支持 **先冻结 V3，再启动一次完整恢复** 的决定，不是对旧 A-v2 自动重试的许可，也不保证真实服务一定成功。新冻结清单实际生成和验证是调用前的最后工程门槛。
