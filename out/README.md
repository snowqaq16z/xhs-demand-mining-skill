# xhs-demand-mining-skill

小红书评论区需求挖掘 skill：
- 输入小红书笔记链接
- 抓取笔记正文与评论
- 尝试递归抓取楼中楼
- 在风控阻断时保留样本并继续分析
- 输出适合微信小程序机会判断的需求挖掘报告

## Included
- `SKILL.md`
- `scripts/fetch_xhs_comments.py`
- `scripts/analyze_xhs_demand.py`
- `references/prompt.md`
- `references/workflow.md`
- `references/sample-analysis.json`
- first-pass sample outputs under `out/first-pass/`
- packaged skill under `dist/`

## Package
The packaged skill artifact is available at:
- `dist/xhs-demand-mining-skill.skill`
