import base64
import html
from pathlib import Path

import streamlit as st


EVERY_HOME_CSS = r"""
<style>
/* EVERY参考ホームはスマホ画面を主役にする。 */
div[data-testid="stAppViewContainer"] .block-container {
    max-width: 34rem;
    padding-top: 0.35rem;
}

.every-home-shell {
    width: min(100%, 31rem);
    margin: 0 auto;
}

.every-home-stage {
    position: relative;
    width: 100%;
    aspect-ratio: 9 / 16;
    overflow: hidden;
    border: 1px solid rgba(255, 255, 255, 0.78);
    border-radius: 1rem;
    background: #dce5ec;
    box-shadow: 0 0.9rem 2.4rem rgba(35, 48, 64, 0.16);
    isolation: isolate;
}

.every-home-stage__image {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center;
    z-index: -3;
}

.every-home-stage__veil {
    position: absolute;
    inset: 0;
    z-index: -2;
    background:
        linear-gradient(
            180deg,
            rgba(244, 251, 255, 0.34) 0%,
            rgba(244, 251, 255, 0.03) 24%,
            rgba(24, 36, 49, 0.02) 58%,
            rgba(24, 36, 49, 0.58) 100%
        );
}

.every-home-hud {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.55rem;
    align-items: center;
    padding: 0.65rem;
}

.every-home-date-badge {
    display: flex;
    min-width: 4.2rem;
    min-height: 4.2rem;
    padding: 0.45rem;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    border: 0.2rem solid rgba(255, 255, 255, 0.94);
    border-radius: 999px;
    background: rgba(42, 55, 72, 0.83);
    color: #fff;
    box-shadow: 0 0.25rem 0.7rem rgba(0, 0, 0, 0.16);
    text-align: center;
    backdrop-filter: blur(7px);
    -webkit-backdrop-filter: blur(7px);
}

.every-home-date-badge__date {
    font-size: 0.78rem;
    font-weight: 900;
    line-height: 1.2;
}

.every-home-date-badge__weekday {
    margin-top: 0.12rem;
    font-size: 0.58rem;
    font-weight: 800;
    opacity: 0.9;
}

.every-home-hud-bars {
    min-width: 0;
}

.every-home-hud-bar {
    display: flex;
    min-height: 1.55rem;
    align-items: center;
    gap: 0.45rem;
    padding: 0.2rem 0.55rem;
    border: 1px solid rgba(255, 255, 255, 0.78);
    border-radius: 999px;
    background: rgba(41, 53, 68, 0.76);
    color: #fff;
    box-shadow: 0 0.2rem 0.55rem rgba(0, 0, 0, 0.12);
    backdrop-filter: blur(7px);
    -webkit-backdrop-filter: blur(7px);
}

.every-home-hud-bar + .every-home-hud-bar {
    margin-top: 0.28rem;
}

.every-home-hud-bar__label {
    flex: 0 0 auto;
    font-size: 0.62rem;
    font-weight: 900;
    opacity: 0.88;
}

.every-home-hud-bar__value {
    min-width: 0;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.72rem;
    font-weight: 850;
    text-align: right;
}

.every-home-place {
    position: absolute;
    top: 5.45rem;
    right: 0.65rem;
    padding: 0.28rem 0.62rem;
    border: 1px solid rgba(255, 255, 255, 0.84);
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.84);
    color: #526173;
    font-size: 0.67rem;
    font-weight: 900;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
}

.every-home-message {
    position: absolute;
    right: 0.75rem;
    bottom: 7.6rem;
    left: 0.75rem;
    padding: 0.85rem 0.9rem;
    border: 1px solid rgba(255, 255, 255, 0.48);
    border-radius: 0.85rem;
    background: rgba(28, 40, 54, 0.7);
    color: #fff;
    box-shadow: 0 0.35rem 0.9rem rgba(0, 0, 0, 0.14);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
}

.every-home-message__label {
    margin-bottom: 0.22rem;
    font-size: 0.6rem;
    font-weight: 900;
    letter-spacing: 0.08em;
    opacity: 0.84;
}

.every-home-message__text {
    font-size: 0.86rem;
    font-weight: 700;
    line-height: 1.55;
}

.every-home-select-label {
    position: absolute;
    right: 0;
    bottom: 5.9rem;
    left: 0;
    color: rgba(255, 255, 255, 0.92);
    font-size: 0.62rem;
    font-weight: 900;
    text-align: center;
    letter-spacing: 0.14em;
    text-shadow: 0 1px 3px rgba(0, 0, 0, 0.38);
}

.every-home-command-base {
    position: absolute;
    right: 0;
    bottom: 0;
    left: 0;
    height: 6.5rem;
    background: linear-gradient(
        180deg,
        rgba(247, 252, 255, 0.04),
        rgba(247, 252, 255, 0.78) 38%,
        rgba(255, 255, 255, 0.97) 100%
    );
}

/* stage直後の3列ボタンを背景下部へ重ねる。ホーム以外ではこのCSSは存在しない。 */
div[data-testid="stHorizontalBlock"] {
    position: relative;
    z-index: 8;
    width: min(94%, 29rem);
    margin: -5.75rem auto 0;
    gap: 0.45rem;
}

div[data-testid="stHorizontalBlock"] .stButton > button {
    min-height: 4.9rem;
    padding: 0.35rem 0.25rem;
    border: 0.18rem solid rgba(255, 255, 255, 0.96);
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.94);
    color: #44566a;
    font-size: 0.73rem;
    font-weight: 900;
    line-height: 1.25;
    box-shadow: 0 0.24rem 0.8rem rgba(48, 72, 95, 0.2);
}

div[data-testid="stHorizontalBlock"] .stButton > button:hover {
    border-color: rgba(83, 190, 210, 0.8);
    color: #218298;
    transform: translateY(-1px);
}

.every-home-after-controls {
    height: 1.15rem;
}

.every-home-submenu {
    width: min(100%, 31rem);
    margin: 0 auto;
}

.every-home-submenu-title {
    margin: 0.25rem 0 0.3rem;
    color: #82909e;
    font-size: 0.64rem;
    font-weight: 850;
    text-align: center;
    letter-spacing: 0.08em;
}

@media (max-width: 640px) {
    div[data-testid="stAppViewContainer"] .block-container {
        padding-right: 0;
        padding-left: 0;
    }

    .every-home-shell,
    .every-home-submenu {
        width: 100%;
    }

    .every-home-stage {
        border-right: 0;
        border-left: 0;
        border-radius: 0;
        box-shadow: none;
    }

    div[data-testid="stHorizontalBlock"] {
        width: 94%;
    }

    div[data-testid="stHorizontalBlock"] .stButton > button {
        min-height: 4.55rem;
        font-size: 0.68rem;
    }
}
</style>
"""


def _safe_text(value: object) -> str:
    return html.escape(str(value), quote=True)


@st.cache_data(show_spinner=False)
def _image_data_uri(path: str, modified_ns: int) -> str:
    del modified_ns
    image_path = Path(path)
    suffix = image_path.suffix.lower()
    mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _short_action_title(title: object) -> str:
    text = str(title or "行動")
    for suffix in ("へ行く", "に行く"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text


def render_every_home(
    *,
    background_path: Path,
    date_label: str,
    weekday: str,
    time_slot: str,
    weather: str,
    location_name: str,
    intro: str,
    actions: list[tuple[str, dict]],
    on_action,
    unlocked_characters: list[str],
    on_free_talk,
    relationship_rows: list[tuple[str, str, int]],
) -> None:
    """EVERYを参考に、実在するゲーム状態だけで自宅ホームを描画する。"""
    st.markdown(EVERY_HOME_CSS, unsafe_allow_html=True)

    image_uri = _image_data_uri(
        str(background_path),
        background_path.stat().st_mtime_ns,
    )

    stage_html = f"""
    <div class="every-home-shell">
      <div class="every-home-stage">
        <img class="every-home-stage__image"
             src="{html.escape(image_uri, quote=True)}"
             alt="{_safe_text(location_name)}">
        <div class="every-home-stage__veil"></div>

        <div class="every-home-hud">
          <div class="every-home-date-badge">
            <div class="every-home-date-badge__date">{_safe_text(date_label)}</div>
            <div class="every-home-date-badge__weekday">{_safe_text(weekday)}</div>
          </div>
          <div class="every-home-hud-bars">
            <div class="every-home-hud-bar">
              <div class="every-home-hud-bar__label">TIME</div>
              <div class="every-home-hud-bar__value">{_safe_text(time_slot)}</div>
            </div>
            <div class="every-home-hud-bar">
              <div class="every-home-hud-bar__label">WEATHER</div>
              <div class="every-home-hud-bar__value">{_safe_text(weather)}</div>
            </div>
          </div>
        </div>

        <div class="every-home-place">{_safe_text(location_name)}</div>

        <div class="every-home-message">
          <div class="every-home-message__label">TODAY</div>
          <div class="every-home-message__text">{_safe_text(intro)}</div>
        </div>

        <div class="every-home-select-label">SELECT ACTION</div>
        <div class="every-home-command-base"></div>
      </div>
    </div>
    """
    st.markdown(stage_html, unsafe_allow_html=True)

    visible_actions = actions[:3]
    columns = st.columns(max(1, len(visible_actions)))
    for column, (action_id, action) in zip(columns, visible_actions):
        icon = action.get("icon", "○")
        title = _short_action_title(action.get("title", "行動"))
        with column:
            if st.button(
                f"{icon}\n{title}",
                key=f"every_home_action_{action_id}",
                use_container_width=True,
            ):
                on_action(action_id)

    st.markdown(
        '<div class="every-home-after-controls"></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="every-home-submenu-title">HOME MENU</div>',
        unsafe_allow_html=True,
    )

    with st.expander("♡ カノジョに会う"):
        if unlocked_characters:
            st.caption("恋人になったカノジョに、好きなときに会いに行けます。")
            for character_name in unlocked_characters:
                if st.button(
                    f"{character_name}に会う",
                    key=f"every_home_free_talk_{character_name}",
                    use_container_width=True,
                ):
                    on_free_talk(character_name)
        else:
            st.caption("恋人になると『カノジョに会う』が解禁されます。")

    with st.expander("♡ みんなとの関係"):
        for character_name, relationship, points in relationship_rows:
            st.write(
                f"**{character_name}**：{relationship}（{points}pt）"
            )
