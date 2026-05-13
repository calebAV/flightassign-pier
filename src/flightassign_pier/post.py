"""Slack delivery + scheduling."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from .api import fetch_outbound, list_in_scope_outbound, total_outbound
from .config import CONFIG, Config
from .format import build_message

log = logging.getLogger(__name__)

REFRESH_SECONDS = 20 * 60  # 20 minutes


def render_once(cfg: Config = CONFIG, *, now_utc: Optional[datetime] = None) -> str:
    """Fetch + filter + format. Returns the Slack-ready text. Does not post."""
    now_utc = now_utc or datetime.now(timezone.utc)
    payload = fetch_outbound(cfg)
    flights = list_in_scope_outbound(cfg, now_utc=now_utc, api_payload=payload)
    return build_message(
        flights,
        cfg=cfg,
        now_utc=now_utc,
        total_outbound_count=total_outbound(payload),
    )


def post_once(cfg: Config = CONFIG, *, dry_run: bool = False) -> str:
    """Build the message and post it (unless dry_run). Returns the message text."""
    text = render_once(cfg)
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
    """Run post_once every 20 minutes until interrupted.

    Use this for VM-style hosting. For GitHub Actions, prefer the cron workflow.
    """
    log.info("flightassign-pier loop starting (refresh=%ss)", REFRESH_SECONDS)
    while True:
        try:
            post_once(cfg, dry_run=dry_run)
        except Exception:  # noqa: BLE001
            # Don't crash the loop on transient errors — just log and try again.
            log.exception("post_once failed; will retry next cycle")
        time.sleep(REFRESH_SECONDS)
