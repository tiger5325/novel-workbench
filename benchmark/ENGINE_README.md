# 顶流对标 · 原生引擎说明（请先读）

## 一句话

`文风提炼` 和 `拆解模仿` 这两个能力，**已经融合成本工作台自己的东西**，不再属于「小说连载工坊」那个网站。你不用登录它、不用在浏览器里点按钮。

## 两种跑法

### A. 交给 agent 跑 —— 最常用
直接在对话里把范文贴给 agent，说一句「跑文风提炼 / 跑拆解」，它按 `06` 的口径产出：
- 文风向量（6 维 + 语言铁律）→ 落 `03`
- 拆解实例 json → 落 `benchmark/`

这就是「原生融合」的本意：agent 在工作台语境里调用这些能力，原 app 只是方法来源。

### B. 用脚本批量跑 —— `engine.py`
适合你有几十章范文要批量处理、或想脱离对话跑：

```bash
# 自动模式（需配置 LLM 后端）
export LLM_BASE="https://your-endpoint/v1"
export LLM_KEY="sk-xxxx"
export LLM_MODEL="gpt-4o-mini"
python engine.py --fanwen 范文.md --name "最强毒士" --out .

# 手动模式（无 API 也能用，打印 prompt 你自己贴 AI）
python engine.py --fanwen 范文.md --name "最强毒士" --manual
```

产出：`文风向量_<name>.md` + `拆解实例_<name>_<seg>.json`，自动归档到 `benchmark/`。

## 为什么这样设计

- 那 6 个远程 app 是**方法来源**，不是运行环境。融合 = 把它们的好功能抽出来，用咱们的 agent + 本地脚本重做一遍。
- `benchmark/` 里现有的 6 个文件，就是之前「在咱们项目里跑出来的」结果，不是从原 app 导出的。
- 红线不变：只拆技法、不抄剧情（见 `06` §8）。
