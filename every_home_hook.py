import inspect

import streamlit as st

from every_home_ui import render_every_home


_ORIGINAL_TITLE = st.title
_HOOK_INSTALLED = False


def _compact_date_label(scene_state: dict, fallback: object) -> str:
    game_date = str(scene_state.get("game_date", ""))
    try:
        _, month, day = game_date.split("-", 2)
        return f"{month}月{day}日"
    except ValueError:
        return str(fallback or game_date)


def _render_home_from_frame(frame) -> bool:
    """旧appのホーム描画直前の状態を使ってEVERY風ホームへ差し替える。"""
    globals_ = frame.f_globals
    locals_ = frame.f_locals

    required_globals = (
        "CHARACTERS",
        "SCENE_ACTIONS",
        "resolve_scene_background_path",
        "is_free_talk_unlocked",
        "get_love_level",
        "build_action_scene_state",
        "build_free_talk_scene_state",
        "enter_scene",
    )
    if any(name not in globals_ for name in required_globals):
        return False

    daily_scene_state = locals_.get("daily_scene_state")
    current_location = locals_.get("current_location")
    source_date_label = locals_.get("date_label")
    if not isinstance(daily_scene_state, dict):
        return False
    if not isinstance(current_location, dict):
        return False

    background_path = globals_["resolve_scene_background_path"](
        daily_scene_state
    )
    if background_path is None:
        return False

    game_state = st.session_state.get("game_state", {})
    unlocked_characters = [
        name
        for name in globals_["CHARACTERS"]
        if name in game_state
        and globals_["is_free_talk_unlocked"](
            game_state[name].get("love_points", 0)
        )
    ]

    relationship_rows = []
    for name in globals_["CHARACTERS"]:
        character_state = game_state.get(name, {})
        points = int(character_state.get("love_points", 0))
        relationship, _ = globals_["get_love_level"](points)
        relationship_rows.append((name, relationship, points))

    def on_action(action_id: str) -> None:
        globals_["enter_scene"](
            globals_["build_action_scene_state"](
                action_id,
                daily_scene_state,
            )
        )

    def on_free_talk(character_name: str) -> None:
        globals_["enter_scene"](
            globals_["build_free_talk_scene_state"](
                character_name,
                daily_scene_state,
            )
        )

    render_every_home(
        background_path=background_path,
        date_label=_compact_date_label(
            daily_scene_state,
            source_date_label,
        ),
        weekday=str(daily_scene_state.get("weekday", "")),
        time_slot=str(daily_scene_state.get("time_slot", "")),
        weather=str(daily_scene_state.get("weather", "")),
        location_name=str(current_location.get("name", "自宅")),
        intro=str(daily_scene_state.get("intro", "")),
        actions=list(globals_["SCENE_ACTIONS"].items()),
        on_action=on_action,
        unlocked_characters=unlocked_characters,
        on_free_talk=on_free_talk,
        relationship_rows=relationship_rows,
    )
    return True


def install_every_home_hook() -> None:
    """「今日の行動」だけをEVERY風ホームに置換し、他画面は従来どおりにする。"""
    global _HOOK_INSTALLED
    if _HOOK_INSTALLED:
        return

    def patched_title(body, *args, **kwargs):
        if str(body) == "今日の行動":
            caller_frame = inspect.currentframe().f_back
            rendered = False
            try:
                if caller_frame is not None:
                    rendered = _render_home_from_frame(caller_frame)
            except Exception as error:
                _ORIGINAL_TITLE(body, *args, **kwargs)
                st.warning(
                    "EVERY風ホームUIの表示に失敗したため、従来画面へ戻しました。"
                )
                st.caption(f"エラー種別: {type(error).__name__}")
                return None

            if rendered:
                st.stop()
                return None

        return _ORIGINAL_TITLE(body, *args, **kwargs)

    st.title = patched_title
    _HOOK_INSTALLED = True
