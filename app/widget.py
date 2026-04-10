from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from app.models import TaigaProject, TaigaStatus, TaigaUserStory
from app.widget_i18n import localize_embed_reason, localize_status_name, tr


@dataclass(slots=True)
class EmbedSupport:
    is_allowed: bool
    reason: str
    x_frame_options: str | None = None
    frame_ancestors: str | None = None


@dataclass(slots=True)
class WidgetStatusColumn:
    status: TaigaStatus
    stories: list[TaigaUserStory]
    count: int


@dataclass(slots=True)
class WidgetViewModel:
    slug: str
    project: TaigaProject
    room_id: str
    board_url: str
    project_url: str
    create_url: str
    recent_stories: list[TaigaUserStory]
    columns: list[WidgetStatusColumn]
    embed_support: EmbedSupport
    bridge_ok: bool
    load_error: str | None = None

    @property
    def total_stories(self) -> int:
        return len(self.recent_stories)

    @property
    def done_stories(self) -> int:
        return sum(1 for story in self.recent_stories if story.is_closed)

    @property
    def active_stories(self) -> int:
        return self.total_stories - self.done_stories

    def count_by_status_slugs(self, *slugs: str) -> int:
        slug_set = {slug for slug in slugs if slug}
        return sum(column.count for column in self.columns if column.status.slug in slug_set)

    def stories_for_statuses(self, *slugs: str) -> list[TaigaUserStory]:
        slug_set = {slug for slug in slugs if slug}
        stories = [story for column in self.columns if column.status.slug in slug_set for story in column.stories]
        return sorted(stories, key=lambda story: story.modified_date or story.created_date or "", reverse=True)


async def inspect_embed_support(target_url: str, allowed_frame_ancestors: list[str]) -> EmbedSupport:
    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
        response = await client.get(target_url)

    x_frame_options = response.headers.get("x-frame-options")
    csp = response.headers.get("content-security-policy")
    frame_ancestors = _extract_frame_ancestors(csp)

    if x_frame_options:
        normalized = x_frame_options.upper()
        if "DENY" in normalized:
            return EmbedSupport(
                is_allowed=False,
                reason="x-frame-options: deny",
                x_frame_options=x_frame_options,
                frame_ancestors=frame_ancestors,
            )
        if "SAMEORIGIN" in normalized:
            return EmbedSupport(
                is_allowed=False,
                reason="x-frame-options: sameorigin",
                x_frame_options=x_frame_options,
                frame_ancestors=frame_ancestors,
            )

    if frame_ancestors:
        tokens = frame_ancestors.split()
        if "'none'" in tokens:
            return EmbedSupport(
                is_allowed=False,
                reason="frame-ancestors 'none'",
                x_frame_options=x_frame_options,
                frame_ancestors=frame_ancestors,
            )

        allowed_tokens = {"*", "'self'"}
        allowed_tokens.update(allowed_frame_ancestors)
        if not any(token in allowed_tokens for token in tokens):
            return EmbedSupport(
                is_allowed=False,
                reason="frame-ancestors restricted",
                x_frame_options=x_frame_options,
                frame_ancestors=frame_ancestors,
            )

    return EmbedSupport(
        is_allowed=True,
        reason="allowed",
        x_frame_options=x_frame_options,
        frame_ancestors=frame_ancestors,
    )


def build_widget_page(view: WidgetViewModel) -> str:
    title = html.escape(view.project.name)
    description = html.escape(_summarize_text(view.project.description or tr("project_description_fallback"), 260))
    subtitle = tr("subtitle_live") if not view.load_error else tr("subtitle_error")
    integration_ok = view.bridge_ok and not view.load_error
    integration_label = tr("integration_badge_ok") if integration_ok else tr("integration_badge_problem")
    integration_class = "ok" if integration_ok else "warn"
    embed_mode = tr("technical_mode_direct") if view.embed_support.is_allowed else tr("technical_mode_fallback")
    embed_note = html.escape(localize_embed_reason(view.embed_support))
    error_banner = ""
    if view.load_error:
        error_banner = (
            '<section class="callout error">'
            f"<strong>{html.escape(tr('error_snapshot_title'))}</strong> {html.escape(view.load_error)}"
            "</section>"
        )

    new_focus_stories = view.stories_for_statuses("new", "ready")
    active_focus_stories = view.stories_for_statuses("in-progress", "ready-for-test")
    if not new_focus_stories:
        new_focus_stories = _fallback_focus_stories(view.columns, excluded_slugs={"in-progress", "ready-for-test"})
    if not active_focus_stories:
        active_focus_stories = _fallback_focus_stories(view.columns, excluded_slugs={"new", "ready"})

    summary_html = "".join(
        [
            _metric_card(tr("metric_total"), str(view.total_stories), tr("metric_total_hint")),
            _metric_card(tr("metric_new"), str(view.count_by_status_slugs("new", "ready")), tr("metric_new_hint")),
            _metric_card(
                tr("metric_in_progress"),
                str(view.count_by_status_slugs("in-progress", "ready-for-test")),
                tr("metric_in_progress_hint"),
            ),
            _metric_card(tr("metric_done"), str(view.done_stories), tr("metric_done_hint")),
        ]
    )

    columns_html = "".join(_render_status_column(column) for column in view.columns) or _empty_block(
        tr("stories_empty_title"),
        tr("stories_empty_body"),
    )
    status_summary_html = "".join(_render_status_summary(column) for column in view.columns)
    task_tabs = [
        _render_task_tab(
            tab_id="tab-new",
            label=tr("task_tab_new"),
            count=len(new_focus_stories),
            active=True,
        ),
        _render_task_tab(
            tab_id="tab-active",
            label=tr("task_tab_active"),
            count=len(active_focus_stories),
            active=False,
        ),
        _render_task_tab(
            tab_id="tab-recent",
            label=tr("task_tab_recent"),
            count=len(view.recent_stories),
            active=False,
        ),
    ]
    task_panes = [
        _render_task_pane(
            tab_id="tab-new",
            title=tr("task_tab_new"),
            description=tr("task_tab_new_description"),
            stories=new_focus_stories,
            empty_title=tr("lane_new_empty_title"),
            empty_body=tr("lane_new_empty_body"),
            active=True,
            show_status=False,
        ),
        _render_task_pane(
            tab_id="tab-active",
            title=tr("task_tab_active"),
            description=tr("task_tab_active_description"),
            stories=active_focus_stories,
            empty_title=tr("lane_active_empty_title"),
            empty_body=tr("lane_active_empty_body"),
            active=False,
            show_status=False,
        ),
        _render_task_pane(
            tab_id="tab-recent",
            title=tr("task_tab_recent"),
            description=tr("task_tab_recent_description"),
            stories=view.recent_stories,
            empty_title=tr("activity_empty_title"),
            empty_body=tr("activity_empty_body"),
            active=False,
            show_status=True,
        ),
    ]

    create_button_label = tr("create_button")
    create_loading_label = tr("create_button_loading")
    create_error_default = tr("create_error_default")
    create_error_unexpected = tr("create_error_unexpected")

    return f"""<!DOCTYPE html>
<html lang="{html.escape(tr('widget_html_lang'))}">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light">
    <title>{html.escape(tr('widget_page_title', project_name=view.project.name))}</title>
    <style>
      :root {{
        --paper: #f2ece2;
        --surface: rgba(255, 251, 245, 0.94);
        --surface-strong: #fffaf2;
        --surface-soft: rgba(255, 255, 255, 0.72);
        --ink: #1f1b16;
        --muted: #6a645a;
        --line: rgba(43, 39, 32, 0.12);
        --accent: #0e7c86;
        --accent-soft: rgba(14, 124, 134, 0.12);
        --accent-strong: #095b62;
        --alert: #b44747;
        --success: #17663c;
        --warn: #9a6b10;
        --shadow: 0 14px 42px rgba(41, 31, 12, 0.1);
        --radius-xl: 24px;
        --radius-lg: 18px;
        --radius-md: 14px;
      }}
      * {{ box-sizing: border-box; }}
      html, body {{ margin: 0; min-height: 100%; }}
      body {{
        font-family: "Trebuchet MS", "Segoe UI", sans-serif;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(228, 124, 64, 0.22), transparent 30%),
          radial-gradient(circle at top right, rgba(14, 124, 134, 0.18), transparent 28%),
          linear-gradient(180deg, #f7f1e7 0%, var(--paper) 100%);
      }}
      a {{ color: inherit; }}
      .shell {{
        max-width: 1220px;
        margin: 0 auto;
        padding: 18px;
        display: grid;
        gap: 16px;
      }}
      .hero {{
        background: linear-gradient(135deg, rgba(255, 248, 238, 0.96), rgba(255, 252, 247, 0.92));
        border: 1px solid rgba(255,255,255,0.75);
        border-radius: var(--radius-xl);
        box-shadow: var(--shadow);
        padding: 20px;
        position: relative;
        overflow: hidden;
      }}
      .hero::after {{
        content: "";
        position: absolute;
        inset: auto -60px -110px auto;
        width: 240px;
        height: 240px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(228, 124, 64, 0.16), transparent 72%);
      }}
      .hero-top {{
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
      }}
      .eyebrow {{
        display: inline-flex;
        gap: 10px;
        align-items: center;
        padding: 7px 12px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.72);
        border: 1px solid var(--line);
        color: var(--muted);
        font-size: 12px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }}
      h1, h2, h3 {{
        font-family: Georgia, "Times New Roman", serif;
        margin: 0;
      }}
      h1 {{
        font-size: clamp(1.9rem, 3vw, 2.8rem);
        line-height: 0.98;
        margin-top: 14px;
        max-width: 12ch;
      }}
      .hero .lead {{
        max-width: 70ch;
        color: var(--muted);
        margin: 10px 0 0;
        line-height: 1.5;
      }}
      .hero .subtle {{
        margin: 10px 0 0;
        color: var(--muted);
        line-height: 1.45;
      }}
      .integration-chip {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 8px 12px;
        border-radius: 999px;
        border: 1px solid rgba(30,27,22,0.1);
        background: rgba(255,255,255,0.72);
        font-size: 13px;
        white-space: nowrap;
      }}
      .integration-chip.ok {{
        color: var(--success);
        border-color: rgba(23, 102, 60, 0.18);
      }}
      .integration-chip.warn {{
        color: var(--warn);
        border-color: rgba(154, 107, 16, 0.18);
      }}
      .hero-meta {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 16px;
      }}
      .pill {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 8px 11px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.7);
        border: 1px solid var(--line);
        font-size: 13px;
      }}
      .layout {{
        display: grid;
        grid-template-columns: minmax(0, 1.42fr) minmax(320px, 0.98fr);
        gap: 16px;
      }}
      .stack {{
        display: grid;
        gap: 16px;
      }}
      .metrics {{
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
      }}
      .metric, .panel {{
        background: var(--surface);
        border: 1px solid rgba(255, 255, 255, 0.76);
        border-radius: var(--radius-lg);
        box-shadow: var(--shadow);
      }}
      .metric {{
        padding: 15px 16px;
      }}
      .metric strong {{
        display: block;
        font-size: 1.55rem;
        margin-top: 6px;
        font-family: Georgia, "Times New Roman", serif;
      }}
      .metric span {{
        color: var(--muted);
        font-size: 0.9rem;
      }}
      .panel {{
        padding: 18px;
      }}
      .section-head {{
        display: flex;
        justify-content: space-between;
        gap: 14px;
        align-items: flex-start;
        margin-bottom: 14px;
      }}
      .section-head p {{
        margin: 6px 0 0;
        color: var(--muted);
        line-height: 1.45;
      }}
      .action-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 16px;
      }}
      .button {{
        appearance: none;
        border: 0;
        border-radius: 999px;
        padding: 11px 15px;
        font: inherit;
        cursor: pointer;
        text-decoration: none;
        display: inline-flex;
        align-items: center;
        gap: 8px;
        transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
      }}
      .button:hover {{ transform: translateY(-1px); }}
      .button.primary {{
        background: var(--accent);
        color: white;
        box-shadow: 0 10px 24px rgba(14, 124, 134, 0.22);
      }}
      .button.secondary {{
        background: var(--surface-strong);
        color: var(--ink);
        border: 1px solid var(--line);
      }}
      .button.ghost {{
        background: rgba(255,255,255,0.58);
        color: var(--ink);
        border: 1px dashed rgba(30,27,22,0.18);
      }}
      .callout {{
        border-radius: var(--radius-md);
        padding: 14px 16px;
        line-height: 1.45;
      }}
      .callout.error {{
        background: rgba(180, 71, 71, 0.08);
        border: 1px solid rgba(180, 71, 71, 0.18);
      }}
      .task-tabs {{
        display: grid;
        gap: 12px;
      }}
      .tab-list {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }}
      .tab-button {{
        appearance: none;
        border: 1px solid rgba(30,27,22,0.1);
        background: rgba(255,255,255,0.58);
        color: var(--ink);
        padding: 9px 12px;
        border-radius: 999px;
        font: inherit;
        cursor: pointer;
      }}
      .tab-button.active {{
        background: var(--accent);
        color: white;
        border-color: transparent;
        box-shadow: 0 10px 24px rgba(14, 124, 134, 0.18);
      }}
      .tab-button strong {{
        margin-left: 6px;
        font-size: 12px;
      }}
      .tab-pane, .status-column {{
        background: rgba(255,255,255,0.64);
        border: 1px solid var(--line);
        border-radius: var(--radius-md);
        padding: 14px;
        display: grid;
        gap: 10px;
      }}
      .tab-pane {{
        display: none;
      }}
      .tab-pane.active {{
        display: grid;
      }}
      .tab-pane header, .status-column header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 10px;
      }}
      .tab-pane header strong, .status-column header strong {{
        display: block;
      }}
      .tab-pane header p {{
        margin: 4px 0 0;
        color: var(--muted);
        font-size: 13px;
        line-height: 1.45;
      }}
      .status-tag {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        font-size: 13px;
      }}
      .status-dot {{
        width: 10px;
        height: 10px;
        border-radius: 50%;
        flex: none;
      }}
      .list-scroll {{
        max-height: 430px;
        overflow-y: auto;
        padding-right: 4px;
      }}
      .story-list {{
        display: grid;
        gap: 10px;
      }}
      .story-mini {{
        border-top: 1px solid rgba(30, 27, 22, 0.08);
        padding-top: 10px;
        margin-top: 10px;
      }}
      .story-mini:first-of-type {{
        border-top: 0;
        padding-top: 0;
        margin-top: 0;
      }}
      .story-mini a, .story-row a {{
        text-decoration: none;
      }}
      .story-title {{
        font-weight: 600;
        line-height: 1.35;
      }}
      .story-meta {{
        margin-top: 6px;
        color: var(--muted);
        font-size: 13px;
        display: flex;
        flex-wrap: wrap;
        gap: 8px 10px;
      }}
      .story-link {{
        margin-top: 8px;
        font-size: 12px;
        color: var(--accent-strong);
      }}
      .story-status-inline {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 5px 9px;
        border-radius: 999px;
        background: rgba(255,255,255,0.76);
        border: 1px solid rgba(30,27,22,0.1);
        font-size: 12px;
        white-space: nowrap;
        margin-top: 8px;
      }}
      .status-summary {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 12px;
      }}
      .status-summary-pill {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 7px 11px;
        border-radius: 999px;
        background: var(--surface-soft);
        border: 1px solid rgba(30,27,22,0.08);
        font-size: 12px;
      }}
      .board-columns {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
        gap: 12px;
      }}
      .column-list {{
        max-height: 280px;
        overflow-y: auto;
        padding-right: 4px;
      }}
      .form-grid {{
        display: grid;
        gap: 12px;
      }}
      .field {{
        display: grid;
        gap: 7px;
      }}
      .field label {{
        font-size: 13px;
        color: var(--muted);
      }}
      .field input, .field textarea {{
        width: 100%;
        border: 1px solid rgba(30,27,22,0.12);
        background: rgba(255, 255, 255, 0.86);
        border-radius: 14px;
        padding: 12px 14px;
        font: inherit;
        color: var(--ink);
        resize: vertical;
      }}
      .field input:focus, .field textarea:focus {{
        outline: 2px solid rgba(14,124,134,0.16);
        border-color: rgba(14,124,134,0.34);
      }}
      .helper {{
        color: var(--muted);
        font-size: 13px;
        line-height: 1.45;
      }}
      .guide-list {{
        margin: 0;
        padding-left: 18px;
        display: grid;
        gap: 8px;
        line-height: 1.45;
      }}
      .command-block {{
        margin-top: 14px;
        padding: 14px;
        border-radius: var(--radius-md);
        background: var(--surface-soft);
        border: 1px solid rgba(30,27,22,0.08);
      }}
      .command-title {{
        font-weight: 600;
        margin-bottom: 8px;
      }}
      .command-list {{
        display: grid;
        gap: 8px;
      }}
      .command-list code {{
        display: block;
        padding: 10px 12px;
        border-radius: 12px;
        background: rgba(30,27,22,0.05);
        overflow-x: auto;
      }}
      .flash {{
        min-height: 22px;
        font-size: 14px;
      }}
      .flash.error {{ color: var(--alert); }}
      .flash.success {{ color: var(--success); }}
      .empty {{
        border: 1px dashed rgba(30,27,22,0.16);
        border-radius: var(--radius-md);
        padding: 18px;
        background: rgba(255,255,255,0.48);
      }}
      .technical-panel {{
        padding: 0;
        overflow: hidden;
      }}
      .technical-panel summary {{
        list-style: none;
        cursor: pointer;
        padding: 18px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
      }}
      .technical-panel summary::-webkit-details-marker {{
        display: none;
      }}
      .summary-pill {{
        display: inline-flex;
        align-items: center;
        padding: 6px 10px;
        border-radius: 999px;
        background: rgba(30,27,22,0.05);
        border: 1px solid rgba(30,27,22,0.08);
        font-size: 12px;
        color: var(--muted);
      }}
      .technical-body {{
        padding: 0 18px 18px;
        display: grid;
        gap: 10px;
      }}
      .technical-grid {{
        display: grid;
        gap: 10px;
      }}
      .technical-row {{
        display: grid;
        gap: 4px;
        padding-top: 10px;
        border-top: 1px solid rgba(30,27,22,0.08);
      }}
      .technical-row:first-child {{
        border-top: 0;
        padding-top: 0;
      }}
      .technical-row strong {{
        font-size: 12px;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }}
      .technical-row span, .technical-row a {{
        line-height: 1.45;
        word-break: break-word;
      }}
      @keyframes fadeUp {{
        from {{ opacity: 0; transform: translateY(10px); }}
        to {{ opacity: 1; transform: translateY(0); }}
      }}
      .hero, .metric, .panel {{ animation: fadeUp 0.34s ease; }}
      @media (max-width: 1080px) {{
        .layout {{ grid-template-columns: 1fr; }}
        .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      }}
      @media (max-width: 640px) {{
        .shell {{ padding: 14px; }}
        .hero {{ padding: 16px; }}
        .panel {{ padding: 16px; }}
        .technical-panel summary {{ padding: 16px; }}
        .technical-body {{ padding: 0 16px 16px; }}
        .metrics {{ grid-template-columns: 1fr; }}
        .section-head {{ flex-direction: column; }}
        .hero-top {{ flex-direction: column; }}
      }}
    </style>
  </head>
  <body>
    <main class="shell">
      <section class="hero">
        <div class="hero-top">
          <div>
            <div class="eyebrow">{html.escape(tr("hero_eyebrow"))}</div>
            <h1>{title}</h1>
            <p class="lead">{description}</p>
            <p class="subtle">{html.escape(subtitle)}</p>
          </div>
          <span class="integration-chip {integration_class}">{html.escape(integration_label)}</span>
        </div>
        <div class="hero-meta">
          <span class="pill">{html.escape(tr("hero_project_slug"))}: <strong>{html.escape(view.project.slug)}</strong></span>
          <span class="pill">{html.escape(tr("hero_project_id"))}: <strong>{view.project.id}</strong></span>
          <span class="pill">{html.escape(tr("hero_room"))}: <strong>{html.escape(view.room_id)}</strong></span>
          <span class="pill">{html.escape(tr("hero_bridge"))}: <strong>{html.escape(tr("hero_bridge_online") if view.bridge_ok else tr("hero_bridge_degraded"))}</strong></span>
        </div>
        <div class="action-row">
          <a class="button primary" href="{html.escape(view.board_url)}" target="_blank" rel="noopener noreferrer">{html.escape(tr("open_board"))}</a>
          <a class="button secondary" href="{html.escape(view.project_url)}" target="_blank" rel="noopener noreferrer">{html.escape(tr("open_project"))}</a>
          <button class="button ghost" type="button" onclick="window.location.reload()">{html.escape(tr("refresh_snapshot"))}</button>
        </div>
      </section>

      {error_banner}

      <section class="metrics">{summary_html}</section>

      <div class="layout">
        <div class="stack">
          <section class="panel">
            <div class="section-head">
              <div>
                <h2>{html.escape(tr("tasks_heading"))}</h2>
                <p>{html.escape(tr("tasks_description"))}</p>
              </div>
            </div>
            <div class="task-tabs">
              <div class="tab-list" role="tablist" aria-label="{html.escape(tr('tasks_heading'))}">
                {''.join(task_tabs)}
              </div>
              <div class="tab-panels">
                {''.join(task_panes)}
              </div>
            </div>
          </section>

          <section class="panel">
            <div class="section-head">
              <div>
                <h2>{html.escape(tr("statuses_heading"))}</h2>
                <p>{html.escape(tr("statuses_description"))}</p>
              </div>
            </div>
            <div class="status-summary">{status_summary_html}</div>
            <div class="board-columns">{columns_html}</div>
          </section>
        </div>

        <div class="stack">
          <section class="panel">
            <div class="section-head">
              <div>
                <h2>{html.escape(tr("help_heading"))}</h2>
                <p>{html.escape(tr("help_description"))}</p>
              </div>
            </div>
            <ol class="guide-list">
              <li>{html.escape(tr("help_step_1"))}</li>
              <li>{html.escape(tr("help_step_2"))}</li>
              <li>{html.escape(tr("help_step_3"))}</li>
              <li>{html.escape(tr("help_step_4"))}</li>
            </ol>
            <div class="command-block">
              <div class="command-title">{html.escape(tr("chat_heading"))}</div>
              <div class="command-list">
                <code>!task Заголовок | описание</code>
                <code>!задача Заголовок | описание</code>
                <code>!tasks</code>
                <code>!open</code>
                <code>!my</code>
                <code>!comment 123 | текст</code>
              </div>
              <p class="helper" style="margin:10px 0 0;">{html.escape(tr("chat_sync_hint"))}</p>
            </div>
          </section>

          <section class="panel">
            <div class="section-head">
              <div>
                <h2>{html.escape(tr("create_heading"))}</h2>
                <p>{html.escape(tr("create_description"))}</p>
              </div>
            </div>
            <form id="create-story-form" class="form-grid" action="{html.escape(view.create_url)}">
              <div class="field">
                <label for="title">{html.escape(tr("field_title"))}</label>
                <input id="title" name="title" maxlength="240" placeholder="{html.escape(tr("field_title_placeholder"))}" required>
              </div>
              <div class="field">
                <label for="description">{html.escape(tr("field_description"))}</label>
                <textarea id="description" name="description" rows="4" maxlength="4000" placeholder="{html.escape(tr("field_description_placeholder"))}"></textarea>
              </div>
              <div class="helper">{html.escape(tr("create_helper"))}</div>
              <div class="action-row">
                <button class="button primary" type="submit">{html.escape(create_button_label)}</button>
              </div>
              <div id="flash" class="flash" aria-live="polite"></div>
            </form>
          </section>

          <details class="panel technical-panel">
            <summary>
              <span>{html.escape(tr("technical_heading"))}</span>
              <span class="summary-pill">{html.escape(tr("technical_summary_pill"))}</span>
            </summary>
            <div class="technical-body">
              <p class="helper" style="margin:0;">{html.escape(tr("technical_description"))}</p>
              <div class="technical-grid">
                {_technical_row(tr("technical_mode"), embed_mode)}
                {_technical_row(tr("technical_bridge_state"), tr("technical_bridge_ok") if view.bridge_ok else tr("technical_bridge_problem"))}
                {_technical_row(tr("technical_embed_reason"), embed_note)}
                {_technical_row(tr("technical_project_slug"), html.escape(view.project.slug))}
                {_technical_row(tr("technical_project_id"), str(view.project.id))}
                {_technical_row(tr("technical_room"), html.escape(view.room_id))}
                {_technical_row(tr("technical_frame_options"), html.escape(view.embed_support.x_frame_options or tr("technical_value_missing")))}
                {_technical_row(tr("technical_frame_ancestors"), html.escape(view.embed_support.frame_ancestors or tr("technical_value_missing")))}
                {_technical_row(tr("technical_board_link"), html.escape(view.board_url), href=view.board_url)}
                {_technical_row(tr("technical_project_link"), html.escape(view.project_url), href=view.project_url)}
              </div>
            </div>
          </details>
        </div>
      </div>
    </main>
    <script>
      const escapeHtml = (value) =>
        String(value).replace(/[&<>"']/g, (char) => {{
          const entities = {{
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;",
          }};
          return entities[char] || char;
        }});
      const form = document.getElementById("create-story-form");
      const flash = document.getElementById("flash");
      const createSuccessPrefix = {json.dumps(tr("create_success_prefix"))};
      const createSuccessSuffix = {json.dumps(tr("create_success_suffix"))};
      form.addEventListener("submit", async (event) => {{
        event.preventDefault();
        flash.textContent = "";
        flash.className = "flash";

        const submitButton = form.querySelector('button[type="submit"]');
        submitButton.disabled = true;
        submitButton.textContent = {json.dumps(create_loading_label)};

        const payload = {{
          title: form.title.value.trim(),
          description: form.description.value.trim(),
        }};

        try {{
          const response = await fetch(form.action, {{
            method: "POST",
            headers: {{
              "Content-Type": "application/json",
            }},
            body: JSON.stringify(payload),
          }});

          const data = await response.json();
          if (!response.ok) {{
            throw new Error(data.detail || data.error || {json.dumps(create_error_default)});
          }}

          flash.className = "flash success";
          const storyUrl = escapeHtml(data.story.permalink || "#");
          const storyLabel = `#${{escapeHtml(data.story.ref)}} ${{escapeHtml(data.story.subject)}}`;
          flash.innerHTML =
            createSuccessPrefix +
            `<a href="${{storyUrl}}" target="_blank" rel="noopener noreferrer">${{storyLabel}}</a>` +
            createSuccessSuffix;
          form.reset();
          window.setTimeout(() => window.location.reload(), 850);
        }} catch (error) {{
          flash.className = "flash error";
          flash.textContent = error.message || {json.dumps(create_error_unexpected)};
        }} finally {{
          submitButton.disabled = false;
          submitButton.textContent = {json.dumps(create_button_label)};
        }}
      }});

      const tabButtons = Array.from(document.querySelectorAll(".tab-button"));
      const tabPanes = Array.from(document.querySelectorAll(".tab-pane"));
      const activateTab = (tabId) => {{
        tabButtons.forEach((button) => {{
          const isActive = button.dataset.tab === tabId;
          button.classList.toggle("active", isActive);
          button.setAttribute("aria-selected", String(isActive));
        }});
        tabPanes.forEach((pane) => {{
          pane.classList.toggle("active", pane.id === tabId);
        }});
      }};
      tabButtons.forEach((button) => {{
        button.addEventListener("click", () => activateTab(button.dataset.tab));
      }});
    </script>
  </body>
</html>
"""


def build_widget_headers(frame_ancestors: str) -> dict[str, str]:
    return {
        "Cache-Control": "no-store",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "img-src 'self' https: data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; "
            "frame-src https://tree.taiga.io; "
            f"frame-ancestors 'self' {frame_ancestors}; "
            "base-uri 'none'; "
            "form-action 'self'"
        ),
    }


def _metric_card(label: str, value: str, hint: str) -> str:
    return (
        '<article class="metric">'
        f"<span>{html.escape(label)}</span>"
        f"<strong>{html.escape(value)}</strong>"
        f"<span>{html.escape(hint)}</span>"
        "</article>"
    )


def _render_status_column(column: WidgetStatusColumn) -> str:
    color = column.status.color or "#70728F"
    stories_html = "".join(_render_compact_story(story) for story in column.stories) or (
        f'<div class="story-mini"><span class="helper">{html.escape(tr("status_column_empty"))}</span></div>'
    )
    return (
        '<section class="status-column">'
        "<header>"
        '<div class="status-tag">'
        f'<span class="status-dot" style="background:{html.escape(color)}"></span>'
        f"<strong>{html.escape(localize_status_name(slug=column.status.slug, name=column.status.name))}</strong>"
        "</div>"
        f'<span class="pill">{column.count}</span>'
        "</header>"
        f'<div class="column-list">{stories_html}</div>'
        "</section>"
    )


def _render_status_summary(column: WidgetStatusColumn) -> str:
    color = column.status.color or "#70728F"
    label = localize_status_name(slug=column.status.slug, name=column.status.name)
    return (
        '<span class="status-summary-pill">'
        f'<span class="status-dot" style="background:{html.escape(color)}"></span>'
        f"{html.escape(label)}"
        f'<strong>{column.count}</strong>'
        "</span>"
    )


def _render_task_tab(*, tab_id: str, label: str, count: int, active: bool) -> str:
    active_class = " active" if active else ""
    selected = "true" if active else "false"
    return (
        f'<button class="tab-button{active_class}" type="button" role="tab" data-tab="{html.escape(tab_id)}" '
        f'aria-selected="{selected}" aria-controls="{html.escape(tab_id)}">'
        f"{html.escape(label)} <strong>{count}</strong>"
        "</button>"
    )


def _render_task_pane(
    *,
    tab_id: str,
    title: str,
    description: str,
    stories: list[TaigaUserStory],
    empty_title: str,
    empty_body: str,
    active: bool,
    show_status: bool,
) -> str:
    active_class = " active" if active else ""
    body = (
        f'<div class="story-list list-scroll">{"".join(_render_compact_story(story, show_status=show_status) for story in stories)}</div>'
        if stories
        else _empty_block(empty_title, empty_body)
    )
    return (
        f'<section class="tab-pane{active_class}" id="{html.escape(tab_id)}" role="tabpanel">'
        "<header>"
        "<div>"
        f"<strong>{html.escape(title)}</strong>"
        f"<p>{html.escape(description)}</p>"
        "</div>"
        f'<span class="pill">{len(stories)}</span>'
        "</header>"
        f"{body}"
        "</section>"
    )


def _render_compact_story(story: TaigaUserStory, *, show_status: bool = False) -> str:
    owner = story.owner.display_name if story.owner else tr("story_owner_missing")
    href = html.escape(story.permalink or "#")
    status_html = ""
    if show_status:
        color = story.status_color or "#70728F"
        status_name = localize_status_name(slug=None, name=story.status_name)
        status_html = (
            f'<div class="story-status-inline"><span class="status-dot" style="background:{html.escape(color)}"></span>'
            f"{html.escape(status_name)}</div>"
        )
    return (
        '<article class="story-mini">'
        f'<a href="{href}" target="_blank" rel="noopener noreferrer">'
        f'<div class="story-title">#{story.ref} {html.escape(story.subject)}</div>'
        "</a>"
        f'<div class="story-meta"><span>{html.escape(owner)}</span><span>{html.escape(_format_story_timestamp(story))}</span></div>'
        f"{status_html}"
        f'<div class="story-link">{html.escape(tr("story_open_link"))}</div>'
        "</article>"
    )


def _empty_block(title: str, body: str) -> str:
    return f'<div class="empty"><strong>{html.escape(title)}</strong><div class="helper">{html.escape(body)}</div></div>'


def _technical_row(label: str, value: str, *, href: str | None = None) -> str:
    rendered_value = (
        f'<a href="{html.escape(href)}" target="_blank" rel="noopener noreferrer">{value}</a>'
        if href
        else f"<span>{value}</span>"
    )
    return f'<div class="technical-row"><strong>{html.escape(label)}</strong>{rendered_value}</div>'


def _fallback_focus_stories(
    columns: list[WidgetStatusColumn],
    *,
    excluded_slugs: set[str],
) -> list[TaigaUserStory]:
    stories = [
        story
        for column in columns
        if not column.status.is_closed and column.status.slug not in excluded_slugs
        for story in column.stories
    ]
    return sorted(stories, key=lambda story: story.modified_date or story.created_date or "", reverse=True)


def _extract_frame_ancestors(csp: str | None) -> str | None:
    if not csp:
        return None
    for directive in csp.split(";"):
        stripped = directive.strip()
        if stripped.startswith("frame-ancestors "):
            return stripped.split(" ", 1)[1].strip()
    return None


def _format_story_timestamp(story: TaigaUserStory) -> str:
    candidate = story.modified_date or story.created_date
    if not candidate:
        return tr("story_updated_recently")
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return candidate
    return parsed.strftime("%d.%m.%Y %H:%M UTC")


TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


def _summarize_text(value: str, limit: int) -> str:
    cleaned = WHITESPACE_RE.sub(" ", TAG_RE.sub(" ", value)).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."
