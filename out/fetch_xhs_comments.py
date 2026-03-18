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


def _load_checkpoint(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding='utf-8'))


def _save_checkpoint(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def _merge_unique(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {item.get('id') for item in existing if isinstance(item, dict)}
    for item in incoming:
        if not isinstance(item, dict):
            continue
        item_id = item.get('id')
        if item_id in seen:
            continue
        existing.append(item)
        seen.add(item_id)
    return existing


def fetch_note_and_comments(
    url: str,
    max_pages: int | None,
    request_delay: float,
    with_subcomments: bool,
    subcomments_max_pages: int | None,
    per_sub_sleep: float,
    checkpoint_path: str | None = None,
    resume: bool = False,
    top_level_page_batch: int = 20,
    subcomment_thread_limit: int | None = None,
) -> dict[str, Any]:
    note_id, url_token = parse_note_url(url)
    checkpoint = _load_checkpoint(checkpoint_path) if resume else {}
    _browser, cookies = get_cookies('auto')
    with XhsClient(cookies, request_delay=request_delay, max_retries=3) as client:
        note = client.get_note_detail(note_id, xsec_token=url_token)

        all_comments: list[dict[str, Any]] = list(checkpoint.get('comments') or [])
        capture = dict(checkpoint.get('capture') or {})
        top_cursor = str(capture.get('top_level_cursor') or '')
        remaining_pages = max_pages

        capture.setdefault('top_level_pages_fetched', 0)
        capture.setdefault('top_level_comments_fetched', len(all_comments))
        capture.setdefault('top_level_cursor', top_cursor)
        capture.setdefault('top_level_complete', False)
        capture.setdefault('top_level_stopped_reason', '')
        capture.setdefault('top_level_verification_required', False)
        capture.setdefault('top_level_verify_message', '')
        capture.setdefault('subcomment_attempted', with_subcomments)
        capture.setdefault('subcomment_threads_completed', 0)
        capture.setdefault('subcomment_threads_skipped', [])
        capture.setdefault('subcomment_resume_queue', [])
        capture.setdefault('subcomment_completed_ids', [])

        while True:
            if remaining_pages is not None and remaining_pages <= 0:
                break
            batch_pages = top_level_page_batch
            if remaining_pages is not None:
                batch_pages = min(batch_pages, remaining_pages)
            page_data = client.get_all_comments(
                note_id,
                xsec_token=url_token,
                max_pages=batch_pages,
                start_cursor=top_cursor,
            )
            all_comments = _merge_unique(all_comments, page_data.get('comments', []))
            capture['top_level_pages_fetched'] += int(page_data.get('pages_fetched', 0) or 0)
            capture['top_level_comments_fetched'] = len(all_comments)
            top_cursor = str(page_data.get('cursor') or '')
            capture['top_level_cursor'] = top_cursor
            capture['top_level_stopped_reason'] = page_data.get('stopped_reason', '')
            capture['top_level_verification_required'] = bool(page_data.get('verification_required'))
            capture['top_level_verify_message'] = page_data.get('verify_message', '')
            capture['top_level_complete'] = not bool(page_data.get('has_more'))
            _save_checkpoint(checkpoint_path, {
                'note': note,
                'comments': all_comments,
                'capture': capture,
                'source_url': url,
                'note_id': note_id,
            })
            if remaining_pages is not None:
                remaining_pages -= int(page_data.get('pages_fetched', 0) or 0)
            if page_data.get('verification_required') or not page_data.get('has_more'):
                break

        if with_subcomments:
            completed_ids = set(capture.get('subcomment_completed_ids') or [])
            resume_queue = capture.get('subcomment_resume_queue') or []
            queue_by_id = {item.get('comment_id'): item for item in resume_queue if isinstance(item, dict) and item.get('comment_id')}

            eligible: list[dict[str, Any]] = []
            for comment in all_comments:
                comment_id = comment.get('id')
                if not comment_id or comment_id in completed_ids:
                    continue
                try:
                    sc_count = int(comment.get('sub_comment_count') or 0)
                except Exception:
                    sc_count = 0
                embedded = list(comment.get('sub_comments') or [])
                if sc_count > len(embedded) or comment.get('sub_comment_has_more'):
                    eligible.append(comment)

            if subcomment_thread_limit is not None:
                eligible = eligible[:subcomment_thread_limit]

            for comment in eligible:
                root_id = comment.get('id')
                try:
                    declared_count = int(comment.get('sub_comment_count') or 0)
                except Exception:
                    declared_count = 0
                embedded = list(comment.get('sub_comments') or [])
                state = queue_by_id.get(root_id, {})
                sub_cursor = str(state.get('cursor') or comment.get('sub_comment_cursor') or '')
                already_pages = int(state.get('pages_fetched', 0) or 0)
                max_pages_for_thread = subcomments_max_pages
                if max_pages_for_thread is not None:
                    remaining_thread_pages = max(0, max_pages_for_thread - already_pages)
                    if remaining_thread_pages == 0:
                        continue
                else:
                    remaining_thread_pages = None

                data = client.get_all_sub_comments(
                    note_id,
                    root_id,
                    max_pages=remaining_thread_pages,
                    start_cursor=sub_cursor,
                )
                embedded = _merge_unique(embedded, data.get('comments', []))
                comment['sub_comments'] = embedded
                comment['sub_comment_cursor'] = str(data.get('cursor') or '')
                comment['sub_comment_has_more'] = bool(data.get('has_more'))

                if data.get('verification_required'):
                    queue_by_id[root_id] = {
                        'comment_id': root_id,
                        'cursor': data.get('cursor', ''),
                        'pages_fetched': already_pages + int(data.get('pages_fetched', 0) or 0),
                        'existing_embedded': len(embedded),
                        'declared_sub_comment_count': declared_count,
                        'reason': data.get('verify_message', ''),
                    }
                    capture['subcomment_threads_skipped'].append({
                        'comment_id': root_id,
                        'reason': data.get('verify_message', ''),
                        'existing_embedded': len(embedded),
                        'declared_sub_comment_count': declared_count,
                    })
                    _save_checkpoint(checkpoint_path, {
                        'note': note,
                        'comments': all_comments,
                        'capture': {**capture, 'subcomment_resume_queue': list(queue_by_id.values())},
                        'source_url': url,
                        'note_id': note_id,
                    })
                    break

                if data.get('has_more'):
                    queue_by_id[root_id] = {
                        'comment_id': root_id,
                        'cursor': data.get('cursor', ''),
                        'pages_fetched': already_pages + int(data.get('pages_fetched', 0) or 0),
                        'existing_embedded': len(embedded),
                        'declared_sub_comment_count': declared_count,
                        'reason': data.get('stopped_reason', ''),
                    }
                else:
                    completed_ids.add(root_id)
                    queue_by_id.pop(root_id, None)
                    capture['subcomment_threads_completed'] += 1

                capture['subcomment_completed_ids'] = sorted(completed_ids)
                capture['subcomment_resume_queue'] = list(queue_by_id.values())
                _save_checkpoint(checkpoint_path, {
                    'note': note,
                    'comments': all_comments,
                    'capture': capture,
                    'source_url': url,
                    'note_id': note_id,
                })
                if per_sub_sleep > 0:
                    time.sleep(per_sub_sleep)

        capture['top_level_comments_fetched'] = len(all_comments)
        capture['subcomment_attempted'] = with_subcomments
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
    parser.add_argument('--max-pages', type=int, default=None)
    parser.add_argument('--request-delay', type=float, default=2.2)
    parser.add_argument('--with-subcomments', action='store_true')
    parser.add_argument('--subcomments-max-pages', type=int, default=None)
    parser.add_argument('--per-sub-sleep', type=float, default=2.5)
    parser.add_argument('--checkpoint', help='Checkpoint file path for resume-friendly progress saves')
    parser.add_argument('--resume', action='store_true', help='Resume from checkpoint if it exists')
    parser.add_argument('--top-level-page-batch', type=int, default=10, help='How many top-level pages to fetch per save cycle')
    parser.add_argument('--subcomment-thread-limit', type=int, default=None, help='Optional cap on how many root threads to deepen in one run')
    args = parser.parse_args()

    try:
        result = fetch_note_and_comments(
            url=args.url,
            max_pages=args.max_pages,
            request_delay=args.request_delay,
            with_subcomments=args.with_subcomments,
            subcomments_max_pages=args.subcomments_max_pages,
            per_sub_sleep=args.per_sub_sleep,
            checkpoint_path=args.checkpoint,
            resume=args.resume,
            top_level_page_batch=args.top_level_page_batch,
            subcomment_thread_limit=args.subcomment_thread_limit,
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
    if args.checkpoint:
        print(f'Checkpoint: {args.checkpoint}')


if __name__ == '__main__':
    main()
