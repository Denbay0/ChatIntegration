from __future__ import annotations

import html
import json
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
    description = html.escape(view.project.description or tr("project_description_fallback"))
    subtitle = tr("subtitle_live") if not view.load_error else tr("subtitle_error")
    embed_mode = tr("mode_direct") if view.embed_support.is_allowed else tr("mode_fallback")
    embed_note = html.escape(localize_embed_reason(view.embed_support))
    error_banner = ""
    if view.load_error:
        error_banner = (
            '<section class="callout error">'
            f"<strong>{html.escape(tr('error_snapshot_title'))}</strong> {html.escape(view.load_error)}"
            "</section>"
        )

    summary_html = "".join(
        [
            _metric_card(tr("metric_mode"), embed_mode, tr("metric_mode_hint")),
            _metric_card(tr("metric_stories"), str(view.total_stories), tr("metric_stories_hint")),
            _metric_card(tr("metric_active"), str(view.active_stories), tr("metric_active_hint")),
            _metric_card(tr("metric_done"), str(view.done_stories), tr("metric_done_hint")),
        ]
    )

    columns_html = "".join(_render_status_column(column) for column in view.columns) or _empty_block(
        tr("stories_empty_title"),
        tr("stories_empty_body"),
    )
    recent_html = "".join(_render_recent_story(story) for story in view.recent_stories[:8]) or _empty_block(
        tr("activity_empty_title"),
        tr("activity_empty_body"),
    )

    board_panel = (
        '<section class="panel frame-panel">'
        f'<div class="section-head"><h2>{html.escape(tr("board_direct_heading"))}</h2><p>{html.escape(tr("board_direct_description"))}</p></div>'
        f'<iframe class="board-frame" src="{html.escape(view.board_url)}" title="{html.escape(tr("embedded_frame_title"))}"></iframe>'
        "</section>"
        if view.embed_support.is_allowed
        else (
            '<section class="panel frame-panel">'
            f'<div class="section-head"><h2>{html.escape(tr("board_fallback_heading"))}</h2><p>{embed_note}</p></div>'
            '<div class="status-grid">'
            f"{columns_html}"
            "</div>"
            "</section>"
        )
    )

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
        --paper: #f3ede4;
        --surface: rgba(255, 250, 243, 0.92);
        --surface-strong: #fffaf2;
        --ink: #1e1b16;
        --muted: #6b665d;
        --line: rgba(45, 41, 35, 0.12);
        --accent: #0e7c86;
        --accent-soft: rgba(14, 124, 134, 0.12);
        --alert: #b44747;
        --success: #17663c;
        --shadow: 0 18px 60px rgba(41, 31, 12, 0.12);
        --radius-xl: 26px;
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
        max-width: 1460px;
        margin: 0 auto;
        padding: 26px;
        display: grid;
        gap: 22px;
      }}
      .hero {{
        background: linear-gradient(135deg, rgba(255, 248, 238, 0.96), rgba(255, 252, 247, 0.92));
        border: 1px solid rgba(255,255,255,0.75);
        border-radius: var(--radius-xl);
        box-shadow: var(--shadow);
        padding: 26px;
        position: relative;
        overflow: hidden;
      }}
      .hero::after {{
        content: "";
        position: absolute;
        inset: auto -40px -70px auto;
        width: 220px;
        height: 220px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(228, 124, 64, 0.16), transparent 72%);
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
        font-size: clamp(2rem, 3vw, 3.2rem);
        line-height: 0.96;
        margin-top: 16px;
        max-width: 14ch;
      }}
      .hero p {{
        max-width: 70ch;
        color: var(--muted);
        margin: 12px 0 0;
        line-height: 1.5;
      }}
      .hero-meta {{
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        margin-top: 18px;
      }}
      .pill {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 9px 12px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.7);
        border: 1px solid var(--line);
        font-size: 13px;
      }}
      .grid {{
        display: grid;
        grid-template-columns: minmax(0, 1.55fr) minmax(320px, 0.95fr);
        gap: 22px;
      }}
      .stack {{
        display: grid;
        gap: 22px;
      }}
      .metrics {{
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 14px;
      }}
      .metric, .panel {{
        background: var(--surface);
        border: 1px solid rgba(255, 255, 255, 0.76);
        border-radius: var(--radius-lg);
        box-shadow: var(--shadow);
      }}
      .metric {{
        padding: 16px 18px;
      }}
      .metric strong {{
        display: block;
        font-size: 1.7rem;
        margin-top: 6px;
        font-family: Georgia, "Times New Roman", serif;
      }}
      .metric span {{
        color: var(--muted);
        font-size: 0.9rem;
      }}
      .panel {{
        padding: 20px;
      }}
      .section-head {{
        display: flex;
        justify-content: space-between;
        gap: 18px;
        align-items: flex-start;
        margin-bottom: 18px;
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
        margin-top: 18px;
      }}
      .button {{
        appearance: none;
        border: 0;
        border-radius: 999px;
        padding: 12px 16px;
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
      .callout.info {{
        background: var(--accent-soft);
        border: 1px solid rgba(14, 124, 134, 0.16);
      }}
      .callout.error {{
        background: rgba(180, 71, 71, 0.08);
        border: 1px solid rgba(180, 71, 71, 0.18);
      }}
      .status-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 14px;
      }}
      .status-column {{
        background: rgba(255,255,255,0.62);
        border: 1px solid var(--line);
        border-radius: var(--radius-md);
        padding: 14px;
      }}
      .status-column header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 10px;
        margin-bottom: 12px;
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
      .story-mini, .story-row {{
        border-top: 1px solid rgba(30, 27, 22, 0.08);
        padding-top: 10px;
        margin-top: 10px;
      }}
      .story-mini:first-of-type, .story-row:first-of-type {{
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
        gap: 10px;
      }}
      .recent-list {{
        display: grid;
        gap: 12px;
      }}
      .story-row {{
        background: rgba(255,255,255,0.58);
        border: 1px solid rgba(30,27,22,0.08);
        border-radius: var(--radius-md);
        padding: 14px;
      }}
      .story-head {{
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 14px;
      }}
      .status-pill {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 7px 10px;
        border-radius: 999px;
        background: rgba(255,255,255,0.76);
        border: 1px solid rgba(30,27,22,0.1);
        font-size: 12px;
        white-space: nowrap;
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
      .board-frame {{
        width: 100%;
        min-height: 860px;
        border: 1px solid var(--line);
        border-radius: calc(var(--radius-lg) - 6px);
        background: white;
      }}
      @keyframes fadeUp {{
        from {{ opacity: 0; transform: translateY(10px); }}
        to {{ opacity: 1; transform: translateY(0); }}
      }}
      .hero, .metric, .panel {{ animation: fadeUp 0.34s ease; }}
      @media (max-width: 1080px) {{
        .grid {{ grid-template-columns: 1fr; }}
        .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      }}
      @media (max-width: 640px) {{
        .shell {{ padding: 14px; }}
        .hero, .panel {{ padding: 16px; }}
        .metrics {{ grid-template-columns: 1fr; }}
        .section-head {{ flex-direction: column; }}
        .story-head {{ flex-direction: column; }}
      }}
    </style>
  </head>
  <body>
    <main class="shell">
      <section class="hero">
        <div class="eyebrow">{html.escape(tr("hero_eyebrow"))}</div>
        <h1>{title}</h1>
        <p>{description}</p>
        <p>{html.escape(subtitle)}</p>
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

      <div class="grid">
        <div class="stack">
          <section class="panel">
            <div class="section-head">
              <div>
                <h2>{html.escape(tr("embed_heading"))}</h2>
                <p>{html.escape(tr("embed_description"))}</p>
              </div>
            </div>
            <div class="callout info">
              <strong>{html.escape(embed_mode)}.</strong> {embed_note}
            </div>
          </section>

          {board_panel}
        </div>

        <div class="stack">
          <section class="panel">
            <div class="section-head">
              <div>
                <h2>{html.escape(tr("help_heading"))}</h2>
                <p>{html.escape(tr("project_description_fallback"))}</p>
              </div>
            </div>
            <div class="status-grid">
              <div class="status-column">
                <header><strong>{html.escape(tr("help_heading"))}</strong></header>
                <div class="helper">1. {html.escape(tr("help_step_1"))}</div>
                <div class="helper">2. {html.escape(tr("help_step_2"))}</div>
                <div class="helper">3. {html.escape(tr("help_step_3"))}</div>
                <div class="helper">4. {html.escape(tr("help_step_4"))}</div>
              </div>
              <div class="status-column">
                <header><strong>{html.escape(tr("chat_heading"))}</strong></header>
                <div class="helper">{html.escape(tr("chat_open"))}</div>
                <div class="helper" style="margin-top:10px;">{html.escape(tr("chat_close"))}</div>
                <div class="helper" style="margin-top:10px;">{html.escape(tr("chat_board"))}</div>
                <div class="helper" style="margin-top:10px;">{html.escape(tr("chat_lang"))}</div>
              </div>
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

          <section class="panel">
            <div class="section-head">
              <div>
                <h2>{html.escape(tr("recent_heading"))}</h2>
                <p>{html.escape(tr("recent_description"))}</p>
              </div>
            </div>
            <div class="recent-list">{recent_html}</div>
          </section>
        </div>
      </div>
    </main>
    <script>
      const form = document.getElementById("create-story-form");
      const flash = document.getElementById("flash");
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
          flash.innerHTML =
            "Задача " +
            `<a href="${{data.story.permalink}}" target="_blank" rel="noopener noreferrer">#${{data.story.ref}} ${{data.story.subject}}</a>` +
            " создана. Обновляем виджет...";
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
    stories_html = "".join(_render_compact_story(story) for story in column.stories[:4]) or (
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
        f"{stories_html}"
        "</section>"
    )


def _render_compact_story(story: TaigaUserStory) -> str:
    owner = story.owner.display_name if story.owner else tr("story_owner_missing")
    href = html.escape(story.permalink or "#")
    return (
        '<article class="story-mini">'
        f'<a href="{href}" target="_blank" rel="noopener noreferrer">'
        f'<div class="story-title">#{story.ref} {html.escape(story.subject)}</div>'
        "</a>"
        f'<div class="story-meta"><span>{html.escape(owner)}</span><span>{html.escape(_format_story_timestamp(story))}</span></div>'
        "</article>"
    )


def _render_recent_story(story: TaigaUserStory) -> str:
    owner = story.owner.display_name if story.owner else tr("story_owner_missing")
    color = story.status_color or "#70728F"
    href = html.escape(story.permalink or "#")
    status_name = localize_status_name(slug=None, name=story.status_name)
    return (
        '<article class="story-row">'
        '<div class="story-head">'
        '<div>'
        f'<a href="{href}" target="_blank" rel="noopener noreferrer"><div class="story-title">#{story.ref} {html.escape(story.subject)}</div></a>'
        f'<div class="story-meta"><span>{html.escape(owner)}</span><span>{html.escape(_format_story_timestamp(story))}</span></div>'
        "</div>"
        f'<span class="status-pill"><span class="status-dot" style="background:{html.escape(color)}"></span>{html.escape(status_name)}</span>'
        "</div>"
        "</article>"
    )


def _empty_block(title: str, body: str) -> str:
    return f'<div class="empty"><strong>{html.escape(title)}</strong><div class="helper">{html.escape(body)}</div></div>'


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
