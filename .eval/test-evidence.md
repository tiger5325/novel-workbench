# 测试验证证据 · 多轮测试（R8/R9）

> 评审要求 D8「测试验证通过度」需可复核证据。本文件记录实测结果与交叉核验。

## 一、sharecode 可达性实测（R8 · 2026-10-28 · WebFetch 成功即 HTTP 200）

| 工具 | 完整 URL | 返回标题 | 可达(HTTP 200) | 与我方描述匹配 |
|---|---|---|---|---|
| 小说连载工坊 | https://novel-studio-web.app.workbuddy.host/?sharecode=3KLOJHIPUP | 小说连载工坊 · Web 版 | ✅ | ✅ 文风特征/人物档案★/逐章大纲/章节摘要均存在 |
| 自进化控制台 | https://novel-factory-console.app.workbuddy.host/?sharecode=WIM5TXTM3Z | 自进化创作控制台 | ✅ | ✅ 7Agent×3台账锁×8步闭环/跨章连贯性/质量轨迹40-40-20/台账锁零写权限 |
| 砚田 | https://yantian-workbench.app.workbuddy.host/?sharecode=A3VR3TLPAQ | 砚田 · 网文创作工作台 | ✅ | ✅ 我的作品/字数追踪/示例(陈砚悬疑慢热) |
| 写作工具 | https://writer-tool-festival.app.workbuddy.host/?sharecode=PSRNKQHUC4 | 写作工具 | ✅ | ✅ 角色关系图谱/大纲时间轴/思维导图/番茄钟/发布日历 |
| 爽文写作Agent | https://shuangwen-agent.app.workbuddy.host/?sharecode=W4XTWPBVQH | 爽文写作Agent · 控制台 | ✅ | ✅ 题材预设(含自定义)/长篇6卷×15章/续写未完成 |
| 墨引（排除项） | https://novel-studio-64402.app.workbuddy.host/?sharecode=BKBVPR6P5Y | 墨引 · 爆款短剧小说工作台 | ✅ | ✅ 女频7公式·印证排除合理 |

**结论**：6/6 可达（HTTP 200）；路由表（00 §1/§1.1）功能描述与实测页面一致，无虚构功能。D3 与 D8 部分（可达性+功能核验）通过。

## 二、样例章节 dry-run（R9 · 见 dryrun-chapter1.md）

用「隋末·裴忌 第1章」走通 01→02→03→04→05 全流程模板，验证模板可填写、跨文件引用可解析、质检清单可勾验。详见同目录 `dryrun-chapter1.md`。
