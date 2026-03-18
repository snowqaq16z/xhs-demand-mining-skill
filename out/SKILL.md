---
name: xhs-demand-mining-skill
description: "Mine product demand from Xiaohongshu (小红书) note comments. Use when the user gives a Xiaohongshu link and wants you to: (1) capture note content and comments, including sub-comments when possible, (2) infer the collection background from the note if the user did not provide it, (3) turn raw comments into a demand-mining report for lightweight WeChat mini-program opportunities, or (4) package the whole workflow into reusable artifacts."
---

# xhs-demand-mining-skill

Use this skill to turn a Xiaohongshu note URL into a structured demand-mining workflow: fetch note data, capture comments, flatten usable text, and produce a report oriented toward lightweight WeChat mini-program opportunities.

## Quick start

When the user gives a Xiaohongshu note URL:

1. Capture the note + comments.
2. Infer collection background from the note title/description if the user did not provide one.
3. Generate the report in Chinese unless the user requests another language.
4. If XHS captcha/risk control blocks strict full capture, disclose the limitation and still produce a first-pass report from the captured sample.

## Workflow

Read `references/workflow.md` and follow it.

## Scripts

### `scripts/fetch_xhs_comments.py`
Fetch note data plus comments, with optional recursive sub-comment capture.

Example:

```bash
PYTHONPATH=/home/ubuntu/.openclaw/workspace/xiaohongshu-cli \
python3 scripts/fetch_xhs_comments.py \
  --url "<xiaohongshu-url>" \
  --out out/run/fetch.json \
  --checkpoint out/run/checkpoint.json \
  --resume \
  --max-pages 200 \
  --top-level-page-batch 10 \
  --with-subcomments \
  --subcomment-thread-limit 20
```

Notes:
- Requires local `xiaohongshu-cli` checkout importable via `PYTHONPATH` or installed package.
- Supports checkpointed progress via `--checkpoint` + `--resume`.
- If captcha appears, keep partial data and continue analysis instead of blocking forever.
- Prefer smaller batches (`--top-level-page-batch`, `--subcomment-thread-limit`) on high-risk notes.

### `scripts/analyze_xhs_demand.py`
Generate the markdown demand report plus optional flattened comment exports.

Example:

```bash
python3 scripts/analyze_xhs_demand.py \
  --note-json ../tmp_xhs_note.json \
  --comments-json ../tmp_xhs_comments.json \
  --context "小红书母婴/待产包内容，用户围绕待产资料领取、清单保存与采购执行展开评论。" \
  --capture-limit "当前抓取受 XHS 风控影响，报告基于已抓到的评论样本。" \
  --report-out out/run/report.md \
  --flat-comments-out out/run/flat-comments.json \
  --summary-out out/run/summary.json
```

## Analysis rules

- Prefer direct quotes from raw comments.
- Focus on operational friction, not vague sentiment.
- Translate repeated asks for templates, checklists, exports, calculators, or records into concrete mini-program ideas.
- Keep the MVP sharp: one core button/function first.
- Call out pseudo-demands that are too heavy, too low-frequency, or not a fit for WeChat mini-programs.

## References

- Prompt source: `references/prompt.md`
- Workflow guide: `references/workflow.md`
- Sample captured analysis: `references/sample-analysis.json`
