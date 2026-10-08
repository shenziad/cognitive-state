# 验证记录：2026-10-01

本次交付覆盖实验协议、12 个合成任务与评分器、版本化提示与候选参考状态，以及可运行实验框架。候选状态均待研究者审核。

## 已完成的验证

使用 Windows 上的 Python 3.12.14：

```bash
python -m unittest discover -s tests -v
python scripts/run_experiment.py --output results/raw/exp001/review_20261001_final
python -m compileall -q src scripts tests
git diff --check
```

14 项检查通过，覆盖以下科研关键风险：

- 合理的不同修改顺序可成功；保护字段改后恢复仍记录违规。
- 未验证完成、验证后再次修改、错误工具参数和环境间串扰。
- 12 个候选状态的结构及截断前消息来源。
- 提取输入不含评分目标或后续手册，初次执行输入不含隐藏环境。
- 无效/超预算表示保留失败，绝不隐式回退完整历史。
- 配置、数据、提示、调用及结果保存，已有目录不覆盖。
- 成本比较包含自动提取成本，候选制作成本未知时不作端到端比较。
- API 请求字段、响应 usage 与请求数上限（本地模拟响应，无网络调用）。

完整 mock 运行共 48 个组合（12 × 4 × 1），运行错误为 0，Token 降幅与科学结论均为 null。脚本按照工具观察执行预设策略，这些分数只验证流程。

## 可查看的运行产物

- [运行配置](../results/raw/exp001/review_20261001_final/config.json)
- [版本与哈希记录](../results/raw/exp001/review_20261001_final/manifest.json)
- [全部实例结果](../results/raw/exp001/review_20261001_final/results.json)
- [mock 汇总](../results/raw/exp001/review_20261001_final/summary.json)
- [TLS 候选状态续做的调用与轨迹](../results/raw/exp001/review_20261001_final/instances/pilot06_tls_bundle_r0_reference_state.json)

这些 raw 文件保存在当前工作区，被 Git 忽略；克隆后可重新运行生成，不应期待随源码下载。

## 验证范围

尚未调用真实 LLM 服务，未测试特定服务商/模型兼容性，也未在 Ubuntu 上实跑。Python >=3.10 与相对路径为运行要求；Ubuntu 上可按实验 README 重现 mock。数据的研究价值和参考状态质量仍需人工审阅。
