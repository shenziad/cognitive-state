# API 接入说明

适配器支持 OpenAI Python SDK（provider=openai_sdk）与原有 HTTP transport（provider=chat_completions）。服务商与模型可配置，使用非流式文本 Chat Completions。请求含 model、messages、可选 temperature 和输出上限字段；读取 message.content，保存 usage、模型名、响应 ID、可用 fingerprint 和 SDK 调用延迟。

参考：[官方 Create chat completion](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create) 与 [官方 Counting tokens](https://developers.openai.com/api/docs/guides/token-counting)。输出 Token 上限可包含不可见推理 Token，不能视为最终状态长度。

示例 `configs/exp001_api.example.json` 需填写 model、完整 HTTPS endpoint 和合适的 `tiktoken:<encoding>`。部分兼容服务使用 max_tokens，部分模型不接受 temperature，均需显式配置（null 会省略 temperature）。尚未进行真实服务兼容性测试。

真实 provider 会加载仓库根目录 .env（不覆盖已有环境变量）。API key 只从 api_key_env 指定的变量读取，密钥不会写入源码、配置快照、消息或结果。mock 不加载 .env。SDK 设置 max_retries=0，不隐式重试或回退模型。max_api_calls 是请求次数上限，不是货币预算。

HTTP/连接错误不保存可能回显凭据的服务器错误正文。失败结果仍保存，无法获取的用量标为 null。工具动作采用通用文本 JSON 协议，环境操作仅发生在内存中。

## SiliconFlow 配置

`configs/exp001_siliconflow.json` 固定模型 deepseek-ai/DeepSeek-V4-Flash，SDK base_url 从 endpoint=https://api.siliconflow.cn/v1/chat/completions 推导为 https://api.siliconflow.cn/v1。现有 .env 使用变量名 apikey，所以该配置的 api_key_env=apikey；若之后改用 SILICONFLOW_API_KEY，只需同步改配置。

按 [SiliconFlow 接口文档](https://docs.siliconflow.cn/docs/api/chat-completions-post)，使用 max_tokens 和 extra_body={enable_thinking:false}。四个条件的模型、思考模式、temperature、步数保持相同，不额外启用 JSON mode 来偏向状态条件。

DeepSeek 的精确 tokenizer 尚未接入，因此当前采用 2200 UTF-8 bytes 表示上限，不将它称为精确 Token 预算；真实 Token 成本只使用服务返回的 usage。此设置与 mock 表示上限一致，可以比较实际成本，但不能宣称完全相同 Token 长度的实验。

```bash
python -m pip install -e ".[api]"
python scripts/run_experiment.py --config configs/exp001_siliconflow_smoke.json --progress
python scripts/run_experiment.py --config configs/exp001_siliconflow.json --progress
```

认证、余额、网络或服务错误会中止该轮，保存已完成记录，并把不完整汇总的性能指标设为 null。模型的无效/超预算表示仍按试验失败处理，两类问题分开解释。
