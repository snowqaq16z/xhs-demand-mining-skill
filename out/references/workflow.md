# Workflow

## End-to-end flow
1. Ask for a Xiaohongshu note URL.
2. Use `scripts/fetch_xhs_comments.py` to capture the note plus comments.
3. If captcha blocks deeper pagination, keep the partial capture, explicitly disclose the gap, and continue with first-pass analysis instead of stalling forever.
4. Infer the collection background from the note title/description when the user did not provide one.
5. Use `scripts/analyze_xhs_demand.py` to generate:
   - flattened comments JSON
   - summary JSON
   - markdown report
6. Return a concise Chinese summary to the user.

## Practical rules
- Prefer progress over perfection. If XHS risk control blocks strict full capture, deliver a first-pass report and label it clearly.
- Treat repeated phrases like “求电子版”, “求表格”, “已关注求发” as strong demand signals for toolized delivery.
- Focus on programmable demand: calculation, checklists, export, progress tracking, form filling, record keeping.
- Reject bloated ideas that obviously exceed the WeChat mini-program “lightweight, shareable, use-and-go” shape.

## Suggested output artifacts
- `out/<slug>/fetch.json`
- `out/<slug>/flat-comments.json`
- `out/<slug>/summary.json`
- `out/<slug>/report.md`
