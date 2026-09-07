# ComfyUI_NAIDGenerator-neo

面向 ComfyUI 的 NovelAI 图像生成节点。项目使用独立的节点命名空间和模块化实现，支持文本生成、图生图、局部重绘、V3/V4 Vibe Transfer 以及 Director Tools。

## 安装

在 ComfyUI 的 `custom_nodes` 目录执行：

```bash
git clone https://github.com/chen079/ComfyUI_NAIDGenerator-neo.git
```

安装 `requirements.txt` 后重启 ComfyUI。节点位于 `NAI Neo` 分类。

## 配置

在 ComfyUI 的 `.env` 文件中设置 NovelAI Persistent API Token：

```dotenv
NAI_ACCESS_TOKEN=你的令牌
```

项目只支持 `NAI_ACCESS_TOKEN`，不会在导入节点时自动安装依赖，也不会通过用户名和密码登录。

## 节点

- `NAI Neo · Generate`：生成图片，只返回 ComfyUI `IMAGE`，不会自动保存文件。
- `NAI Neo · ModelOption`：选择 NovelAI 模型。
- `NAI Neo · Img2ImgOption`：配置图生图。
- `NAI Neo · InpaintingOption`：配置局部重绘。
- `NAI Neo · EncodeVibe`：为 V4/V4.5 编码参考图。
- `NAI Neo · VibeTransferOption`：设置 Vibe 强度并组合多个参考。
- `NAI Neo · NetworkOption`：设置生成请求的超时、重试和错误忽略策略。
- `NAI Neo · RemoveBG`、`LineArt`、`Sketch`、`Colorize`、`Emotion`、`Declutter`：NovelAI Director Tools。

## V4 / V4.5 Vibe Transfer

```text
Load Image → NAI Neo · EncodeVibe
NAI Neo · EncodeVibe → NAI Neo · VibeTransferOption.encoded_vibe
NAI Neo · VibeTransferOption → NAI Neo · Generate.option
```

`information_extracted` 在 Encode Vibe 节点设置，修改它或参考图会重新编码。`strength` 在 Vibe Transfer Option 节点设置，修改它可以复用未失效的编码结果。NovelAI 通常对一次新编码收取 2 Anlas；ComfyUI 缓存失效或重启后可能再次编码。

V3 模型可以把原图直接连接到 Vibe Transfer Option 的 `image`。V4/V4.5 必须先经过 Encode Vibe。编码模型与生成模型必须一致。

## 保存图片

Generate 和 Director 节点不会写入 `output`。需要保存时，请连接 ComfyUI 自带的 `SaveImage` 节点；只想查看时可以连接预览节点。

## 迁移说明

本项目使用 `NAINeo...` 节点 ID 及 `NAI_NEO_OPTION`、`NAI_NEO_VIBE` 端口类型。原项目节点不会被注册，旧工作流需要重新添加并连接 NAI Neo 节点。

## 致谢与许可

本项目最初基于 [bedovyy/ComfyUI_NAIDGenerator](https://github.com/bedovyy/ComfyUI_NAIDGenerator) 开展，感谢原作者和贡献者提供的基础工作。

此后项目采用独立的节点标识、代码结构、请求模块、图片转换模块、提示词模块、测试和文档。项目仍按照原项目采用的 GNU GPL v3 发布；完整条款见 [LICENSE](LICENSE)。NovelAI、ComfyUI 及相关名称和商标归各自权利人所有，本项目不是 NovelAI 或 ComfyUI 官方项目。
