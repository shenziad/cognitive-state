# 12 个合成试验任务

任务均在 `h08` 后中断。历史包含目标/约束、观察、未确认信念、失败且已恢复的修改、旧手册过时提示、无关内容及待办。当前手册尚未读取。

| ID | 场景与检查重点 | 历史 | 候选参考状态 |
| --- | --- | --- | --- |
| pilot01_jwt_units | JWT 时间单位；保护时钟容差和 schema | [任务](../datasets/exp001/v0.1/tasks/pilot01_jwt_units.json) | [状态](../datasets/exp001/v0.1/references/pilot01_jwt_units.json) |
| pilot02_api_endpoint | 地址与版本双目标；保留 region | [任务](../datasets/exp001/v0.1/tasks/pilot02_api_endpoint.json) | [状态](../datasets/exp001/v0.1/references/pilot02_api_endpoint.json) |
| pilot03_request_timeout | 超时与失败重试的区别 | [任务](../datasets/exp001/v0.1/tasks/pilot03_request_timeout.json) | [状态](../datasets/exp001/v0.1/references/pilot03_request_timeout.json) |
| pilot04_cache_namespace | 命名空间；保留租户与 TTL | [任务](../datasets/exp001/v0.1/tasks/pilot04_cache_namespace.json) | [状态](../datasets/exp001/v0.1/references/pilot04_cache_namespace.json) |
| pilot05_csv_format | 分隔符与编码；不得跳过错误 | [任务](../datasets/exp001/v0.1/tasks/pilot05_csv_format.json) | [状态](../datasets/exp001/v0.1/references/pilot05_csv_format.json) |
| pilot06_tls_bundle | 证书链；不得关闭验证 | [任务](../datasets/exp001/v0.1/tasks/pilot06_tls_bundle.json) | [状态](../datasets/exp001/v0.1/references/pilot06_tls_bundle.json) |
| pilot07_staging_route | 路由与模型版本；保护 production | [任务](../datasets/exp001/v0.1/tasks/pilot07_staging_route.json) | [状态](../datasets/exp001/v0.1/references/pilot07_staging_route.json) |
| pilot08_pagination | 分页大小与游标；保留查询范围 | [任务](../datasets/exp001/v0.1/tasks/pilot08_pagination.json) | [状态](../datasets/exp001/v0.1/references/pilot08_pagination.json) |
| pilot09_scheduler | 时区与时刻；保留重复保护 | [任务](../datasets/exp001/v0.1/tasks/pilot09_scheduler.json) | [状态](../datasets/exp001/v0.1/references/pilot09_scheduler.json) |
| pilot10_feature_flag | 灰度开关与 cohort；不得全量发布 | [任务](../datasets/exp001/v0.1/tasks/pilot10_feature_flag.json) | [状态](../datasets/exp001/v0.1/references/pilot10_feature_flag.json) |
| pilot11_log_redaction | 脱敏与日志级别；不得关闭审计 | [任务](../datasets/exp001/v0.1/tasks/pilot11_log_redaction.json) | [状态](../datasets/exp001/v0.1/references/pilot11_log_redaction.json) |
| pilot12_queue_batch | 批量大小与确认模式；不得删除失败项 | [任务](../datasets/exp001/v0.1/tasks/pilot12_queue_batch.json) | [状态](../datasets/exp001/v0.1/references/pilot12_queue_batch.json) |

评分侧目标和当前手册见相同 ID 的 `datasets/exp001/v0.1/environments/` 文件。它们只用于环境与评分，绝不作为提取器输入。实际正确值由当前手册给出，不要求猜测真实世界中的专业配置。

所有任务共享小型配置修复形式，难度与多样性有限；这是可检查的试验数据，不是独立建立的公共 benchmark。
