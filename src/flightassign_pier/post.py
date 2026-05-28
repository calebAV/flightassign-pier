"""Slack delivery + scheduling."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from .api import fetch_outbound, list_in_scope_outbound, total_outbound
from .config import CONFIG, Config
from .format import build_message

log = logging.getLogger(__name__)

REFRESH_SECONDS = 20 * 60


def render_once(cfg: Config = CONFIG, *, now_utc: Optional[datetime] = None) -> Optional[str]:
    """Fetch + filter + format for the current shift window.

    Returns the Slack-ready text, OR ``None`` if we're outside a shift message
    window (in which case nothing should be posted).
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    shift = cfg.current_shift(now_utc)
    if shift is None:
        local = now_utc.astimezone(ZoneInfo(cfg.display_tz))
        log.info("Outside shift message window (now=%s). No post.", local.strftime("%-I:%M %p %Z"))
        return None

    payload = fetch_outbound(cfg)
    flights = list_in_scope_outbound(
        cfg,
        now_utc=now_utc,
        haulout_end_utc=shift.haulout_end_utc,
        api_payload=payload,
    )
    return build_message(
        flights,
        cfg=cfg,
        now_utc=now_utc,
        total_outbound_count=total_outbound(payload),
        shift=shift,
    )


def post_once(cfg: Config = CONFIG, *, dry_run: bool = False) -> Optional[str]:
    """Build and post a message for the current shift window. No-op outside windows."""
    text = render_once(cfg)
    if text is None:
        if dry_run:
            print("(no post — outside shift message window)")
        return None
    if dry_run:
        print(text)
        return text
    if not cfg.slack_bot_token:
        raise RuntimeError("SLACK_BOT_TOKEN is not set")
    client = WebClient(token=cfg.slack_bot_token)
    try:
        client.chat_postMessage(
            channel=cfg.slack_channel,
            text=text,
            unfurl_links=False,
            unfurl_media=False,
        )
        log.info("Posted pier view to %s (%d chars)", cfg.slack_channel, len(text))
    except SlackApiError as e:
        log.error("Slack post failed: %s", e.response.get("error"))
        raise
    return text


def loop(cfg: Config = CONFIG, *, dry_run: bool = False) -> None:
    log.info("flightassign-pier loop starting (refresh=%ss)", REFRESH_SECONDS)
    while True:
        try:
            post_once(cfg, dry_run=dry_run)
        except Exception:
            log.exception("post_once failed; will retry next cycle")
        time.sleep(REFRESH_SECONDS)
