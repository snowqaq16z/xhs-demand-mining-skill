#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from xhs_cli.client import XhsClient
from xhs_cli.cookies import get_cookies
from xhs_cli.exceptions import NeedVerifyError, NoCookieError, SessionExpiredError, XhsApiError
from xhs_cli.formatter import parse_note_url


def fetch_note_and_comments(url: str, max_pages: int, request_delay: float, with_subcomments: bool, subcomments_max_pages: int, per_sub_sleep: float) -> dict[str, Any]:
    note_id, url_token = parse_note_url(url)
    _browser, cookies = get_cookies('auto')
    with XhsClient(cookies, request_delay=request_delay, max_retries=3) as client:
        note = client.get_note_detail(note_id, xsec_token=url_token)

        all_comments: list[dict[str, Any]] = []
        cursor = ""
        pages = 0
        while pages < max_pages:
            page = client.get_comments(note_id, cursor=cursor, xsec_token=url_token)
            if not isinstance(page, dict):
                break
            batch = page.get('comments', [])
            all_comments.extend(batch)
            pages += 1
            has_more = bool(page.get('has_more', False))
            next_cursor = page.get('cursor', '')
            if not has_more or not next_cursor:
                break
            cursor = next_cursor

        capture = {
            'top_level_pages_fetched': pages,
            'top_level_comments_fetched': len(all_comments),
            'subcomment_attempted': with_subcomments,
            'subcomment_threads_completed': 0,
            'subcomment_threads_skipped': [],
        }

        if with_subcomments:
            for comment in all_comments:
                need = False
                try:
                    sc_count = int(comment.get('sub_comment_count') or 0)
                except Exception:
                    sc_count = 0
                embedded = list(comment.get('sub_comments') or [])
                if sc_count > len(embedded) or comment.get('sub_comment_has_more'):
                    need = True
                if not need:
                    continue

                root_id = comment.get('id')
                sub_cursor = comment.get('sub_comment_cursor', '')
                pages_done = 0
                try:
                    while pages_done < subcomments_max_pages:
                        data = client.get_sub_comments(note_id, root_id, cursor=sub_cursor)
                        sub_items = data.get('comments') or data.get('sub_comments') or []
                        if sub_items:
                            existing_ids = {x.get('id') for x in embedded if isinstance(x, dict)}
                            for item in sub_items:
                                if item.get('id') not in existing_ids:
                                    embedded.append(item)
                                    existing_ids.add(item.get('id'))
                        pages_done += 1
                        has_more = bool(data.get('has_more', False))
                        next_cursor = data.get('cursor', '')
                        if not has_more or not next_cursor:
                            break
                        sub_cursor = next_cursor
                        if per_sub_sleep > 0:
                            time.sleep(per_sub_sleep)
                    comment['sub_comments'] = embedded
                    comment['sub_comment_has_more'] = False
                    comment['sub_comment_cursor'] = ''
                    capture['subcomment_threads_completed'] += 1
                except NeedVerifyError as exc:
                    capture['subcomment_threads_skipped'].append({
                        'comment_id': root_id,
                        'reason': str(exc),
                        'existing_embedded': len(embedded),
                        'declared_sub_comment_count': sc_count,
                    })
                    comment['sub_comments'] = embedded
                    break

        return {
            'note': note,
            'comments': all_comments,
            'capture': capture,
            'source_url': url,
            'note_id': note_id,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description='Fetch Xiaohongshu note and comments, with optional recursive sub-comments.')
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--max-pages', type=int, default=200)
    parser.add_argument('--request-delay', type=float, default=1.6)
    parser.add_argument('--with-subcomments', action='store_true')
    parser.add_argument('--subcomments-max-pages', type=int, default=20)
    parser.add_argument('--per-sub-sleep', type=float, default=1.0)
    args = parser.parse_args()

    try:
        result = fetch_note_and_comments(
            url=args.url,
            max_pages=args.max_pages,
            request_delay=args.request_delay,
            with_subcomments=args.with_subcomments,
            subcomments_max_pages=args.subcomments_max_pages,
            per_sub_sleep=args.per_sub_sleep,
        )
    except (NoCookieError, SessionExpiredError, NeedVerifyError, XhsApiError) as exc:
        print(json.dumps({
            'ok': False,
            'error': str(exc),
            'type': type(exc).__name__,
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Wrote fetch result: {out}')


if __name__ == '__main__':
    main()
