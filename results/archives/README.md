# 实验原始记录归档

`experiments_20261008.zip` 保存截至 2026-10-08 已完成工作的全部原始实验记录，包括中断运行、服务探测、冻结快照、模型响应及工具轨迹。共 2,268 个文件、80,161,778 个未压缩字节；ZIP 为 9,249,607 bytes。11 个生成的 Python 缓存文件未归档。

对应 `.manifest.json` 记录 ZIP 和每个原始文件的 SHA256、大小及仓库相对路径。归档不含 `.env`、API Key、虚拟环境或 Git 凭据。`fixtures_private.json` 等是合成 benchmark 的隐藏评分数据，名称中的 private 指模型不可见，不是个人隐私资料。

## 从 GitHub 拉取后恢复

在仓库根目录，使用 Python >=3.10：

```bash
python scripts/restore_experiment_records.py --verify-only
python scripts/restore_experiment_records.py
```

脚本先核验归档及全部文件，再恢复到 `results/raw/`。已有相同内容会跳过；已有不同内容会拒绝覆盖。原始目录继续受 `.gitignore` 忽略，版本控制保存的是归档及清单。

`.gitattributes` 禁止自动换行转换，以保留历史冻结文件的字节哈希。运行冻结审计还需匹配 `requirements-cycle4.txt` 中的依赖。部分 review/gate 保存 Windows 绝对路径；Ubuntu 上的行为回放仍需在独立映射层处理路径，不能改写冻结原件或把恢复文件成功称为 Ubuntu 全流程验证。真实模型调用需另行配置本地环境凭据。
