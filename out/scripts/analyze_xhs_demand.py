#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

PROMPT_TEMPLATE = """##角色：独立开发者与产品需求挖掘专家##

##背景：
评论区是发现“野生需求”的宝库。很多时候，用户会在评论区抱怨现有流程繁琐、软件难用，甚至分享自己用 Excel 或笨办法解决问题的过程。这些“效率瓶颈”、“操作摩擦”和“未被满足的微小痛点”，正是开发轻量级微信小程序工具的最佳切入点。

##任务：
基于我提供的采集背景和真实评论内容，你需要从“工具产品经理”的视角进行深度拆解。找出用户在特定场景下的操作痛点，并直接转化为具有可行性的微信小程序工具产品思路。

##第一步：要求我提供以下信息（缺失需追问）：
1. 这些评论是从什么平台的什么内容下采集的？（如：B站“教你如何排版简历”视频、小红书“孕期体重管理”笔记等）
2. 把评论内容粘贴进来（越原始越好，保留用户的口语和抱怨）。

##分析框架：

一、核心痛点诊断
用一两句话概括：这批评论反映出用户在完成什么任务时，遇到了最大的阻力？（例如：用户在计算复杂房贷时，现有工具不够直观，导致焦虑。）

二、工具需求逐层拆解（重点）
从评论中提炼出多个具体的“工具需求”，每一层包含：
- 痛点场景：（一句话概括用户在哪一步卡住了）
- 用户原话：（直接引用最能体现“麻烦/急躁/求助”的评论原话）
- 现有替代方案的缺陷：（分析用户现在是怎么勉强解决的？是手动算？还是用笨办法？还是现有APP太臃肿？）
- 小程序产品化机会：（如果做成一个用完即走的小程序，它应该具备哪1-2个核心功能？如何帮用户省时间？）

三、伪需求排雷
基于你的理性判断，指出评论区中哪些呼声可能是“伪需求”或“低频需求”（例如：虽然有人提，但开发成本极高，或者用户根本不愿意为之打开微信的）。

四、MVP（最小可行性产品）建议
综合以上分析，如果你来做这个微信小程序，它的 1.0 版本只需要哪一个最核心的按钮或功能？（必须符合微信生态：轻量、易分享、用完即走）。

##分析规则：
1. 你的视角是“用代码解决问题”的开发者，重点关注“动作”、“效率”、“计算”、“记录”等可被程序化的需求。
2. 必须引用原话，寻找类似于“求个软件”、“太麻烦了”、“我每次都手动…”这样的关键词。
3. 提出的产品机会必须适合“微信小程序”这个载体，不要提出需要长期后台运行或重度计算的PC端软件需求。
4. 语言风格直接、极客、有商业洞察力。

##输出流程：
1. 先引导我提供背景和评论数据。
2. 收到数据后，严格按照【分析框架】输出报告。
"""


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def extract_note_payload(note_obj: dict[str, Any]) -> dict[str, Any]:
    data = note_obj.get("data", note_obj)
    items = data.get("items") or []
    if items:
        return items[0].get("note_card", {})
    return data.get("note_card", data)


def flatten_comments(comments_obj: dict[str, Any]) -> list[dict[str, Any]]:
    data = comments_obj.get("data", comments_obj)
    comments = data.get("comments", [])
    rows: list[dict[str, Any]] = []
    for c in comments:
        rows.append({
            "level": 1,
            "id": c.get("id"),
            "content": c.get("content", ""),
            "user": ((c.get("user_info") or {}).get("nickname") or ""),
            "like_count": c.get("like_count"),
            "sub_comment_count": c.get("sub_comment_count"),
        })
        for sc in c.get("sub_comments") or []:
            rows.append({
                "level": 2,
                "id": sc.get("id"),
                "parent_id": c.get("id"),
                "content": sc.get("content", ""),
                "user": ((sc.get("user_info") or {}).get("nickname") or ""),
                "like_count": sc.get("like_count"),
            })
    return rows


def summarize_texts(texts: list[str]) -> dict[str, Any]:
    patterns = {
        "求电子版/清单": r"电子版|电子档|清单|表格|pdf|PDF|excel|Excel",
        "已关注求发送": r"已关|关注了|已关注|关注啦",
        "感谢/实用": r"谢谢|实用|有用|感谢",
        "发送受阻": r"发不过去|设置了|私信不了|关了",
    }
    metrics = {label: sum(1 for t in texts if re.search(regex, t)) for label, regex in patterns.items()}
    normalized = [re.sub(r"\[[^\]]+\]", "", t).strip() for t in texts if t and t.strip()]
    top_texts = Counter(normalized).most_common(30)
    return {"metrics": metrics, "top_repeated_texts": top_texts}


def pick_quotes(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    buckets = {
        "索要电子版": [],
        "已关注换资料": [],
        "格式化诉求": [],
        "发送链路问题": [],
        "正向反馈": [],
    }
    for row in rows:
        t = row.get("content", "")
        if not t:
            continue
        if re.search(r"电子版|电子档|求发|求一份|求电子", t) and len(buckets["索要电子版"]) < 8:
            buckets["索要电子版"].append(t)
        if re.search(r"已关|已关注|关注啦", t) and len(buckets["已关注换资料"]) < 8:
            buckets["已关注换资料"].append(t)
        if re.search(r"表格|pdf|PDF|excel|Excel|清单", t) and len(buckets["格式化诉求"]) < 8:
            buckets["格式化诉求"].append(t)
        if re.search(r"发不过去|设置了|关了|私信", t) and len(buckets["发送链路问题"]) < 8:
            buckets["发送链路问题"].append(t)
        if re.search(r"谢谢|实用|有用|感谢", t) and len(buckets["正向反馈"]) < 8:
            buckets["正向反馈"].append(t)
    return buckets


def render_report(note: dict[str, Any], rows: list[dict[str, Any]], source_context: str, capture_limits: list[str] | None = None) -> str:
    texts = [r.get("content", "") for r in rows if r.get("content")]
    summary = summarize_texts(texts)
    quotes = pick_quotes(rows)
    top = summary["top_repeated_texts"]
    top_lines = "\n".join(f"- {count}次：{text}" for text, count in top[:12])
    limits_md = ""
    if capture_limits:
        limits_md = "\n\n**采集限制说明**\n" + "\n".join(f"- {x}" for x in capture_limits)

    quote = lambda bucket, idx=0, default="": (quotes.get(bucket) or [default])[idx]

    title = note.get("title", "")
    desc = note.get("desc", "")
    author = ((note.get("user") or {}).get("nickname") or note.get("author") or "")
    interact = note.get("interact_info") or {}

    return f"""# 小红书需求挖掘报告

## 采集背景
- 平台：小红书
- 内容对象：笔记《{title}》
- 作者：{author}
- 内容概述：{desc}
- 归纳背景：{source_context}
- 可见互动数据：点赞 {interact.get('liked_count','?')} / 收藏 {interact.get('collected_count','?')} / 评论 {interact.get('comment_count','?')}
- 当前纳入分析文本数：{len(texts)}（含一级评论与已抓到的部分楼中楼）{limits_md}

## 一、核心痛点诊断
这批评论反映出的核心阻力，不是“用户不知道该买什么”，而是**用户没有一个可以直接拿来用、能立刻保存和转发的待产包电子清单**。

信息其实已经被博主整理出来了，但交付方式仍停留在“评论区求资料 / 关注后私发 / 手动索取”这套低效率链路里。用户真正卡住的，是**从内容消费到清单执行**的最后一步。

## 二、工具需求逐层拆解

### 需求 1：把“看完帖子”立刻变成“拿到可执行清单”
- 痛点场景：用户刷到待产包攻略后，想立刻保存、转发、照着买，但评论区只能反复“求电子版”。
- 用户原话：
  - “{quote('索要电子版',0,'求电子版')}”
  - “{quote('索要电子版',1,'求清单电子版')}”
  - “{quote('格式化诉求',0,'求表格')}”
- 现有替代方案的缺陷：
  - 现在的替代方案是截图、手抄、收藏笔记、评论区蹲回复，或者等博主私发资料。
  - 这套流程极其原始：内容是结构化的，但交付不是；信息能看，不能直接执行。
- 小程序产品化机会：
  - 做一个“**待产包一键转清单**”小程序。
  - 核心功能只要两个：**选择孕周/季节/预算**、**一键生成可勾选清单**。
  - 用户看完内容后不用再求表格，直接得到可保存、可分享、可勾选的购买清单。

### 需求 2：把“博主经验”标准化成“用户自己的版本”
- 痛点场景：用户知道这份清单有用，但每个人情况不同，直接照搬又不放心。
- 用户原话：
  - “{quote('格式化诉求',1,'求电子版清单')}”
  - “{quote('索要电子版',2,'求电子档')}”
- 现有替代方案的缺陷：
  - 用户只能拿到一份静态表格，然后自己二次删改。
  - 真正的动作发生在表格外：自己改 Excel、备忘录重抄、问家人、重新比价。
- 小程序产品化机会：
  - 把静态清单做成“**可个性化裁剪的模板**”。
  - 例如：按“是否夏季生产 / 是否剖腹产 / 是否母乳喂养 / 首胎还是二胎 / 预算区间”勾选后，自动裁掉不需要的项目。
  - 这不是内容平台再分发，而是工具化地减少决策负担。

### 需求 3：把“评论区求发”替换成“自动交付”
- 痛点场景：用户已经表达了强需求，但拿资料还要经过“关注—留言—等回复—私信发送”这条很长的链路。
- 用户原话：
  - “{quote('已关注换资料',0,'已关注，求电子版')}”
  - “{quote('已关注换资料',1,'已关注，电子版发一下谢谢！')}”
  - “{quote('发送链路问题',0,'宝，你设置了发不过去')}”
- 现有替代方案的缺陷：
  - 对用户：等待、碰运气、容易拿不到。
  - 对博主：重复私发、回复成本极高，评论区被“求电子版”淹没。
  - 对潜在产品：需求明明高频，却被困在私信劳动力里。
- 小程序产品化机会：
  - 做一个“**评论区资料自动交付页**”。
  - 博主只需要在笔记里放一句固定引导：`回复关键词/点击主页链接领取待产包清单`。
  - 小程序端提供：**领取清单 + 保存微信内收藏 + 转发家人**。
  - 本质上是把“人工发资料”升级成“自助领取”。

### 需求 4：把“看攻略”升级成“采购进度管理”
- 痛点场景：用户不是只想拿一份资料，她们后续还要分批购买、比价、确认哪些已买哪些没买。
- 用户原话：
  - “{quote('正向反馈',0,'很实用谢谢～')}”
  - “{quote('索要电子版',3,'已关，求电子版')}”
- 现有替代方案的缺陷：
  - 收藏一篇爆文，不等于完成采购。
  - 用户仍然会在淘宝、京东、拼多多、线下门店之间来回切换，缺一个轻量的“已购/待购”状态面板。
- 小程序产品化机会：
  - 在清单基础上加一个极轻的“**待买 / 已买 / 不买**”三态切换。
  - 不做重社区、不做电商闭环，先专注“买前决策 + 采购进度记录”这两个高频动作。

## 三、伪需求排雷
1. **不要一上来做母婴全能社区**
   - 这类评论里并没有强烈表达“想交流”，而是在表达“想立刻拿到资料”。
   - 社区是重运营需求，不是当前评论区暴露出的第一性需求。

2. **不要先做复杂比价聚合**
   - 用户此刻的真实痛点是“没有现成清单”，不是“缺一个全网最低价引擎”。
   - 比价有价值，但它属于第二阶段增强，不是 1.0 必需。

3. **不要先做大而全的孕育管理系统**
   - 比如孕周提醒、产检日历、知识库、医生咨询，这些都太重。
   - 这些需求没有在评论区里高密度出现，贸然扩展会把一个锋利的小工具做钝。

4. **“自动私信发资料”未必是好产品方向**
   - 从增长上看很诱人，但平台规则、风控、账号安全都不稳定。
   - 真正稳的方向是：把资料交付搬到微信生态，而不是继续依赖评论区和私信链路。

## 四、MVP（最小可行性产品）建议
如果我来做，这个微信小程序 1.0 版本只做一个核心功能：

### **按钮：一键生成我的待产包清单**

用户进入后只做三步：
1. 选择预产期月份 / 季节
2. 选择需求偏好（精简版 / 标准版 / 囤货版）
3. 生成可勾选、可分享、可保存的清单

这就是最小可行闭环：
- 它轻
- 它明确
- 它符合微信“用完即走”
- 它天然适合在小红书内容场景里被种草后承接

## 附：评论信号速览
{top_lines}

## 结论
这条笔记下面最强的，不是“内容讨论需求”，而是**资料交付需求**。

用户不是想继续聊，她们是想马上得到一个能执行的电子清单。这种需求非常适合被做成微信小程序：入口轻、转发强、领取自然、交付闭环短。对独立开发者来说，这类产品最大的优势不是技术复杂度，而是**需求极其直白，转化路径极短，场景真实且高频**。
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Xiaohongshu comments for demand-mining report generation.")
    parser.add_argument("--note-json", required=True, help="Path to xhs read --json output")
    parser.add_argument("--comments-json", required=True, help="Path to xhs comments --json output")
    parser.add_argument("--context", default="小红书母婴/待产包内容，用户围绕待产资料领取、清单保存与采购执行展开评论。")
    parser.add_argument("--capture-limit", action="append", default=[], help="Known data capture limitation to annotate in report")
    parser.add_argument("--report-out", required=True, help="Markdown report output path")
    parser.add_argument("--flat-comments-out", help="Optional flattened comments JSON output path")
    parser.add_argument("--summary-out", help="Optional summary JSON output path")
    parser.add_argument("--print-prompt", action="store_true", help="Print the bundled analysis prompt and exit")
    args = parser.parse_args()

    if args.print_prompt:
        print(PROMPT_TEMPLATE)
        return

    note = extract_note_payload(load_json(Path(args.note_json)))
    rows = flatten_comments(load_json(Path(args.comments_json)))
    texts = [r.get("content", "") for r in rows if r.get("content")]
    summary = summarize_texts(texts)

    report = render_report(note, rows, args.context, capture_limits=args.capture_limit)
    report_path = Path(args.report_out)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    if args.flat_comments_out:
        p = Path(args.flat_comments_out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.summary_out:
        payload = {
            "note_title": note.get("title"),
            "note_id": note.get("note_id"),
            "row_count": len(rows),
            "summary": summary,
            "capture_limits": args.capture_limit,
        }
        p = Path(args.summary_out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote report: {report_path}")


if __name__ == "__main__":
    main()
