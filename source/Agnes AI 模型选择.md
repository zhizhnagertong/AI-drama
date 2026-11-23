# Agnes AI 模型选择

官网：https://agnes-ai.com/zh-Hans/docs/pricing

基于你选择的 Agnes AI 模型，可以将之前的漫剧制作流程具体落地。这些模型目前大多处于免费阶段，非常适合用来快速搭建和验证你的平台原型。

下面是每个模型的具体能力、API用法，以及如何在你的AI漫剧平台中集成它们。

### 📝 文本模型：agnes-2.5-flash

这个模型是平台的“大脑”，负责创意生成、剧本编写和分镜设计等核心文本任务。

*   **核心能力**：它是一个高性能的文本生成模型，支持**多轮对话、代码生成、工具调用（Function Calling）和推理**。其上下文窗口高达**512K**，单次可处理约**65.5K**的输出，足以应对长篇剧本的生成。并且，它也支持**图像理解**，可以根据角色设定图来生成更准确的描述。
*   **API 用法**：接口兼容 OpenAI 格式。
    *   **Endpoint**: `POST https://apihub.agnes-ai.com/v1/chat/completions`
    *   **请求示例**:
        ```bash
        curl https://apihub.agnes-ai.com/v1/chat/completions \
          -H "Authorization: Bearer YOUR_API_KEY" \
          -H "Content-Type: application/json" \
          -d '{
            "model": "agnes-2.5-flash",
            "messages": [
              {"role": "system", "content": "你是一个专业的AI漫剧编剧。"},
              {"role": "user", "content": "请为一个关于未来城市侦探的漫剧写一个开头。"}
            ]
          }'
        ```
*   **集成到平台**：
    *   **剧本创作**：将用户输入的简单创意，通过精心设计的提示词（Prompt），让模型生成包含角色、场景和对话的结构化剧本。
    *   **分镜设计**：将剧本分段输入，让模型为每一段生成详细的镜头描述，包括景别、运镜方式和画面内容。
    *   **角色与场景描述生成**：根据剧本生成用于图像模型（`agnes-image-2.1-flash`）的、富含细节的提示词。

### 🎨 图片模型：agnes-image-2.1-flash

这个模型是“画师”，负责将文本描述转化为高质量的静态画面，即漫剧的关键帧。

*   **核心能力**：支持**文生图、图生图和多图合成**。它特别优化了**高信息密度图像**的生成，能处理复杂构图和丰富细节，非常适合生成漫剧中细节繁多的场景。输出尺寸支持从**1K到4K**。
*   **API 用法**：
    *   **Endpoint**: `POST https://apihub.agnes-ai.com/v1/images/generations`
    *   **核心参数**:
        *   `model`: `agnes-image-2.1-flash`
        *   `prompt`: 你的图像描述文本。
        *   `size`: 输出尺寸，推荐 `1K`, `2K`, `3K`, `4K`。
        *   `ratio`: 画面比例，如 `16:9`, `9:16`。
        *   `image` (可选): 图生图时传入，支持URL或Base64。
    *   **请求示例 (文生图)**:
        ```bash
        curl https://apihub.agnes-ai.com/v1/images/generations \
          -H "Authorization: Bearer YOUR_API_KEY" \
          -H "Content-Type: application/json" \
          -d '{
            "model": "agnes-image-2.1-flash",
            "prompt": "A futuristic detective, wearing a trench coat, standing on a rain-soaked neon-lit city street at night, cyberpunk style, highly detailed, 4k",
            "size": "2K",
            "ratio": "16:9"
          }'
        ```
*   **集成到平台**：
    *   **角色与场景定稿**：在剧本阶段，使用此模型根据描述生成角色的初始形象和主要场景图，供用户确认。
    *   **关键帧生成**：在分镜阶段，为每一个镜头生成对应的、符合角色形象和场景设定的关键帧画面。

### 🎬 视频模型：agnes-video-2.5-flash

这个模型是“导演”和“剪辑师”，负责将静态的关键帧或文本描述变为动态视频。

*   **核心能力**：支持**文生视频、图生视频（参考图生成）** 等。生成的视频为**720P**分辨率，时长可在**4到12秒**之间。
*   **API 用法**：采用异步任务模式。
    *   **创建任务 Endpoint**: `POST https://api.agnes-ai.cn/v1/videos`
    *   **查询任务 Endpoint**: `GET https://api.agnes-ai.cn/agnesapi?video_id=<VIDEO_ID>&model_name=agnes-video-2.5-flash`
    *   **核心参数**:
        *   `model`: `agnes-video-2.5-flash`
        *   `prompt`: 视频内容描述。
        *   `mode`: `text` (文生视频), `keyframe`, 或 `reference` (参考图生视频)。
        *   `seconds`: 视频时长， `"4"` 到 `"12"`。
        *   `aspect_ratio`: 画面比例，如 `"16:9"`。
    *   **请求示例 (参考图生视频)**:
        ```bash
        curl -X POST "https://api.agnes-ai.cn/v1/videos" \
          -H "Authorization: Bearer $AGNES_API_KEY" \
          -H "Content-Type: application/json" \
          -d '{
            "model": "agnes-video-2.5-flash",
            "prompt": "The detective walks slowly through the rain, looking around cautiously. <Picture 1>",
            "mode": "reference",
            "seconds": "5",
            "aspect_ratio": "16:9",
            "images": ["<YOUR_GENERATED_IMAGE_URL_1>"]
          }'
        ```
        之后需要轮询查询接口，直到任务状态变为 `completed`，即可获取视频链接。
*   **集成到平台**：
    *   **视频片段生成**：将分镜脚本中的关键帧和对应的运镜描述作为输入，生成一系列4-12秒的视频片段。
    *   **视频片段拼接**：在获取所有视频片段后，你的后端（FastAPI）可以使用 `ffmpeg` 等工具将它们按顺序拼接，并添加配音和字幕，形成最终成片。

### 💎 总结与工作流串联

在你的 **FastAPI** 后端中，可以这样串联整个流程：

1.  **用户输入创意** -> **agnes-2.5-flash** 生成完整剧本和角色/场景描述。
2.  **角色/场景描述** -> **agnes-image-2.1-flash** 生成角色设定图和主要场景图，供用户确认。
3.  **用户确认后的剧本** -> **agnes-2.5-flash** 拆解为详细分镜脚本（含画面描述）。
4.  **分镜脚本 + 角色/场景图** -> **agnes-image-2.1-flash** 批量生成每个镜头的关键帧。
5.  **关键帧 + 分镜运镜描述** -> **agnes-video-2.5-flash** 异步生成每个镜头的短视频片段。
6.  **所有视频片段 + 配音** -> **FastAPI 后端** 进行最终合成，生成完整漫剧。

> **注意**：视频生成是异步任务，你的后端需要设计合理的任务队列和状态管理机制来处理。