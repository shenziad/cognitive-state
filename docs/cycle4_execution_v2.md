# 第四轮执行版本 v2：实现、验证与运行

2026-10-03。执行版本 `cycle4-execution-v2` 已冻结，匹配研究协议 `cycle4-scoped-lifecycle-v1`。**真实预检已具备启动条件；本次没有调用模型。** 回归和连续交接仍需前一阶段的真实、完整、经过审阅且复核通过的 gate。

## 实现内容

| 文件/目录 | 职责 |
|---|---|
| `src/state/v031.py` | v0.3.1 Schema 编码检查、活动引用、来源类别继承、最多一次编码修复；不以语义正确性筛选状态 |
| `src/evaluation/lifecycle.py` | 所有条件共享公开对象契约；实际执行才返回 lifecycle 回执；未读 observation 和隐藏评分不进入公开接口 |
| `src/evaluation/cycle4.py` | 三阶段运行、真实世界继承、压缩历史边界、直接对象消息封装、每次请求账本、异常停止和版本校验 |
| `src/evaluation/cycle4_audit.py` | 从冻结输入重建消息与轨迹、评分回放、成本/整链汇总、来源优先的审阅包、可重算 gate |
| `datasets/cycle4_v1/` | 12 个预检实例、14 个已知回归实例、2 条四段交接链以及冻结运行顺序 |
| `prompts/cycle4/` | 共同语义附录及四份完整提示；所有执行条件和三个压缩提示获得相同生命周期原则 |
| `configs/cycle4_*_v1.json` | preflight、regression、longitudinal 的实际运行配置 |

`source_authority` 是运行器保留的来源 ID→类别映射，只保留表示中实际出现的来源 ID，适用于所有压缩格式。它不提供丢弃的历史内容，不把工具来源升为用户权威；该元数据随实际消息发送并计入 Token 用量，6000 bytes 上限仅约束保留表示本身。原有 G/W/F 来源标签不是事实正确性保证。

未通过编码检查的输出保留原文，只允许一次有记录的修复。候选行动未知、目标过期、价格不合理、来源类别与内容不相符等语义问题，不触发额外提取修复；它们由内容审阅和共同环境的实际反馈评价。

同步成功回执使用本次动作的确定性身份；异步回执的对象来自人工明确编写的公开契约。回归任务中的两个 reservation 实例新增相同的 broker 身份别名契约，它不声称任何 broker 已接受或完成。底稿的世界、预算、评分、原有观察和操作效果保持一致，差异说明见 [adaptation.json](../datasets/cycle4_v1/adaptation.json)。这些仍是已知开发任务，不是未见测试。

## 执行修订记录

v1 在真实调用前被撤回：最后复核发现步数耗尽时，操作前提不满足可能被误归为格式错误并停止该链。v2 将它归为行为性的 step_limit，按协议继续后续交接，并增加反例测试。v1 的 55 份原始资产与清单保存在 `docs/freezes/archive/cycle4_execution_v1/`；没有任何真实模型调用使用 v1，研究协议和预检门槛均未改变。

## 验证结果

- 仓库 **117 项离线测试全部通过**，其中第四轮专项 17 项。
- 覆盖 12 个生命周期规范例子的编码/引用，以及 20 个冻结门槛决策案例。
- 用专供离线检查的、能看到 fixture 的模拟器运行并回放 **96 + 56 + 32 = 184** 个分配组合，验证任务可解、消息边界、评分和链继承；另验证提取失败后的跳过与服务中断。
- 模拟器不是模型基线，不衡量真实提取、压缩或长期行为能力；零模拟 Token 不能用于成本结论。模拟证据不能生成解锁真实比较的 gate。
- 检查任务生成可重复、共同语义提示一致、隐藏世界/评分/未读值不进入目录；篡改实际公开输入会被回放拒绝。

完整测试记录见 [离线验证 JSON](freezes/cycle4_offline_validation_v2.json)。[执行清单](freezes/cycle4_execution_v2.json)锁定 55 个文件、协议清单 hash 和依赖版本。旧协议配置中的 `execution_ready=false` 是当时冻结的历史记录，不改写；本次执行清单提供后续的独立发布依据。cycle3 的 failed gate 仍不能解锁 cycle4。

## 启动前复核

在仓库根目录、Python ≥3.10 环境中运行。Windows 当前环境使用 `.venv/Scripts/python.exe`；Ubuntu 可使用虚拟环境的 `python`。

```bash
python scripts/check_cycle4_protocol.py
python -c "import sys; sys.path.insert(0, 'src'); from evaluation.cycle4 import verify_release; verify_release(); print('execution release verified')"
```

Ubuntu 新环境先按 [requirements-cycle4.txt](../requirements-cycle4.txt)安装冻结版本，再执行上述复核。运行器记录解释器版本，并检查冻结的直接及主要传输依赖；该文件不是完整操作系统/所有传递依赖的容器快照。Python `-O` 会被拒绝，以免关闭完整性断言。

API 凭据由仓库 `.env` 或环境变量 `apikey` 提供，不写入源码、提示、配置快照或日志。只运行 mock/检查脚本不会加载凭据或发送请求。

## 三阶段命令

以下运行命令会产生真实 API 用量，输出目录须全新。预检最多 720 请求，回归 420，连续交接 240；全轮上限 1,380，不做隐式重试或失败单元的选择性补跑。

```bash
python scripts/run_cycle4.py --stage preflight --output results/raw/cycle4/preflight_v1 --progress
```

首先导出仅含公开输入与最终表示的审阅包，不含后续动作、隐藏 fixture 和评分：

```bash
python scripts/audit_cycle4.py --run results/raw/cycle4/preflight_v1 --review-packet --output results/analysis/cycle4_preflight/review.json
```

审阅者填写 reviewer、每份状态的六个 assessment 和 evidence_notes。可用值为 correct/incorrect/ambiguous/not_observed；提取失败或跳过的表示必须标 not_observed。六个维度为对象/阶段混淆、无依据完成、新增要求、遗漏 pending 作业、无依据重开和决策依赖遗漏。Summary 按同一内容标准判断，不因缺少显式图结构自动判错。不能修改包中的输入和表示；审核工具会核对原始来源和 hash。

然后复核全部执行轨迹与账本，并据完整审阅生成 gate：

```bash
python scripts/audit_cycle4.py --run results/raw/cycle4/preflight_v1 --review results/analysis/cycle4_preflight/review.json --output results/analysis/cycle4_preflight/gate.json
python scripts/run_cycle4.py --stage regression --gate results/analysis/cycle4_preflight/gate.json --output results/raw/cycle4/regression_v1 --progress
```

回归也先导出/填写审阅包，再生成其 gate；两步同上，替换 run 和输出路径。回归完整且设施复核通过后运行：

```bash
python scripts/run_cycle4.py --stage longitudinal --gate results/analysis/cycle4_regression/gate.json --output results/raw/cycle4/longitudinal_v1 --progress
```

只读回放、细项成绩和 Token/缓存/延迟汇总，可省略 `--review`：

```bash
python scripts/audit_cycle4.py --run results/raw/cycle4/longitudinal_v1 --output results/analysis/cycle4_longitudinal/audit.json
```

工具拒绝覆盖现有审阅/分析文件。不同 condition 继承各自真实动作后的世界。步数耗尽是行为结果；若步数耗尽且存在未纠正工具格式错误，记录 executor_error 并停止该链，后续 skipped 保留分母；已 finish 的行为失败不因此跳过后续交接。服务错误/未知用量立即中止当前阶段，不发布完整性能结论。

## 维护边界

执行清单创建后，运行前及每个组合开始前均校验文件 hash。修改任何执行资产都会使旧清单失效；不能覆盖已冻结版本后继续当作同一次实验。协议本身的改变另建协议版本。原始完整调用保存在被 Git 忽略的 `results/raw/`，跨机器复核需另行转移；本次没有提交或推送仓库。
