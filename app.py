import datetime
import hmac
import html
import json
import re
from pathlib import Path

import gspread
import streamlit as st
from google import genai
from google.genai import types
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound


# =========================================================
# 1. 基本設定
# =========================================================

JST = datetime.timezone(datetime.timedelta(hours=9), "JST")
CHARACTERS = ("愛花", "凛子", "寧々")
SCREEN_DAILY = "daily"
SCREEN_SCENE = "scene"
DEFAULT_GAME_TIME_SLOT = "放課後"
DEFAULT_WEATHER = "晴れ"
DEFAULT_LOCATION_ID = "home_room"
SCENE_TYPE_DAILY = "daily"
SCENE_TYPE_ENCOUNTER = "encounter"
SCENE_TYPE_FREE_TALK = "free_talk"
SCENE_TYPE_MOVE = "move"
SCENE_TYPE_DATE = "date"
SCENE_TYPE_EVENT = "event"
VALID_SCENE_TYPES = {
    SCENE_TYPE_DAILY,
    SCENE_TYPE_ENCOUNTER,
    SCENE_TYPE_FREE_TALK,
    SCENE_TYPE_MOVE,
    SCENE_TYPE_DATE,
    SCENE_TYPE_EVENT,
}
SCENE_TYPE_LABELS = {
    SCENE_TYPE_DAILY: "日常行動",
    SCENE_TYPE_ENCOUNTER: "日常行動中の遭遇",
    SCENE_TYPE_FREE_TALK: "恋人になった後の『いつでも会う』",
    SCENE_TYPE_MOVE: "場所移動",
    SCENE_TYPE_DATE: "デート",
    SCENE_TYPE_EVENT: "特別イベント",
}
WEEKDAY_LABELS = (
    "月曜日",
    "火曜日",
    "水曜日",
    "木曜日",
    "金曜日",
    "土曜日",
    "日曜日",
)
LOCATIONS = {
    "home_room": {
        "name": "自宅",
        "detail": "主人公の部屋",
        "category": "home",
        "background_id": "home_room",
    },
    "school_tennis_court": {
        "name": "テニスコート",
        "detail": "学校のテニスコート",
        "category": "school",
        "background_id": "school_tennis_court",
    },
    "school_library": {
        "name": "図書室",
        "detail": "学校の図書室",
        "category": "school",
        "background_id": "school_library",
    },
    "family_restaurant": {
        "name": "デキシーズ",
        "detail": "アルバイト先のファミレス",
        "category": "town",
        "background_id": "family_restaurant",
    },
    "meeting_spot": {
        "name": "いつもの待ち合わせ場所",
        "detail": "恋人と会うための待ち合わせ場所",
        "category": "town",
        "background_id": "meeting_spot",
    },
}
LEGACY_LOCATION_IDS = {
    "自宅": "home_room",
    "テニスコート": "school_tennis_court",
    "図書室": "school_library",
    "デキシーズ": "family_restaurant",
    "いつもの待ち合わせ場所": "meeting_spot",
}
SCENE_ACTIONS = {
    "tennis_club": {
        "icon": "🎾",
        "title": "テニス部へ行く",
        "description": "テニスコートへ行き、部活の様子を見る。",
        "location_id": "school_tennis_court",
        "time_slot": "放課後",
        "character": "愛花",
        "intro": "放課後のテニスコートへ向かうと、練習を終えた愛花の姿が見えた。",
    },
    "library": {
        "icon": "📚",
        "title": "図書室へ行く",
        "description": "図書委員の仕事を手伝いに行く。",
        "location_id": "school_library",
        "time_slot": "放課後",
        "character": "凛子",
        "intro": "静かな図書室へ入ると、凛子がカウンターで返却本を整理していた。",
    },
    "restaurant_shift": {
        "icon": "🍽️",
        "title": "バイトへ行く",
        "description": "ファミレスの夕方のシフトに入る。",
        "location_id": "family_restaurant",
        "time_slot": "夕方",
        "character": "寧々",
        "intro": "バイト先のデキシーズへ着くと、寧々がカウンターでメモを確認していた。",
    },
}
MODEL_NAME = st.secrets.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
SHEET_URL = st.secrets.get("SHEET_URL", "")
STATE_SHEET_NAME = "game_state"
GAME_STATE_SCHEMA_VERSION = 2
MAX_SESSION_MESSAGES = 16

PERSONALITY_AUTO = "auto"
PERSONALITY_COLORS = {
    "blue": "💙 ブルー",
    "green": "💚 グリーン",
    "pink": "💗 ピンク",
}
PERSONALITY_COMMANDS = {
    "性格をブルーにして": "blue",
    "性格をグリーンにして": "green",
    "性格をピンクにして": "pink",
}

DEFAULT_GAME_STATE = {
    name: {
        "love_points": 0,
        "lead_gauge": 0,
        "sweet_mode": False,
        "personality_override": PERSONALITY_AUTO,
    }
    for name in CHARACTERS
}
STATE_HEADERS = [
    "character",
    "love_points",
    "lead_gauge",
    "sweet_mode",
    "updated_at",
    "personality_override",
]

STATUS_TAG_PATTERN = re.compile(r"\[(LOVE_UP|LEAD_UP|LEAD_DOWN)\]")
VALID_STATUS_TAGS = {"LOVE_UP", "LEAD_UP", "LEAD_DOWN"}
VALID_EXPRESSIONS = {
    "neutral",
    "smile",
    "happy",
    "blush",
    "surprised",
    "worried",
    "sad",
    "angry",
}
VALID_POSES = {
    "normal",
    "approach",
    "look_away",
    "turn_away",
    "gesture",
}

CONVERSATION_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "required": [
        "narration",
        "dialogue",
        "expression",
        "pose",
        "status_tags",
    ],
    "properties": {
        "narration": {
            "type": "STRING",
            "description": (
                "第三者視点の短い地の文。動作・表情・視線・周囲の様子だけを書き、"
                "キャラクターの発言や主人公の未指定の行動・感情は書かない。"
                "不要なら空文字にする。"
            ),
        },
        "dialogue": {
            "type": "STRING",
            "description": (
                "キャラクター本人のセリフだけを書く。カギ括弧、動作を示す括弧書き、"
                "地の文、内部判定タグを混ぜない。"
            ),
        },
        "expression": {
            "type": "STRING",
            "enum": sorted(VALID_EXPRESSIONS),
            "description": "返答時の主な表情ID。",
        },
        "pose": {
            "type": "STRING",
            "enum": sorted(VALID_POSES),
            "description": "返答時の主なポーズID。",
        },
        "status_tags": {
            "type": "ARRAY",
            "items": {
                "type": "STRING",
                "enum": sorted(VALID_STATUS_TAGS),
            },
            "description": "今回成立した内部判定タグ。該当しなければ空配列。",
        },
    },
}


def get_weekday_label(game_date: str) -> str:
    """ISO形式の日付を、ゲーム表示用の日本語曜日へ変換する。"""
    parsed_date = datetime.date.fromisoformat(str(game_date))
    return WEEKDAY_LABELS[parsed_date.weekday()]


def resolve_location_id(
    requested_location_id: str | None,
    current_location_id: str = DEFAULT_LOCATION_ID,
) -> str:
    """未登録の場所は採用せず、現在地か初期地点を維持する。"""
    if requested_location_id in LOCATIONS:
        return str(requested_location_id)
    if current_location_id in LOCATIONS:
        return str(current_location_id)
    return DEFAULT_LOCATION_ID


def get_location(location_id: str | None) -> dict:
    """登録済み場所の情報を安全に取得する。"""
    resolved_id = resolve_location_id(location_id)
    return LOCATIONS[resolved_id]


def create_scene_state(
    *,
    location_id: str,
    game_date: str,
    time_slot: str,
    weather: str,
    scene_type: str,
    character: str | None,
    previous_state: dict | None = None,
    action_id: str = "",
    intro: str = "",
) -> dict:
    """登録済み場所だけを使って、正規形の場面状態を作る。"""
    if scene_type not in VALID_SCENE_TYPES:
        raise ValueError(f"unknown scene type: {scene_type}")
    if character is not None and character not in CHARACTERS:
        raise ValueError(f"unknown character: {character}")

    has_previous_state = isinstance(previous_state, dict)
    previous_location_id = resolve_location_id(
        previous_state.get("location_id") if has_previous_state else None
    )
    resolved_location_id = resolve_location_id(
        location_id,
        previous_location_id,
    )
    if not has_previous_state:
        previous_location_id = resolved_location_id

    normalized_date = datetime.date.fromisoformat(str(game_date)).isoformat()
    return {
        "location_id": resolved_location_id,
        "previous_location_id": previous_location_id,
        "game_date": normalized_date,
        "weekday": get_weekday_label(normalized_date),
        "time_slot": str(time_slot or DEFAULT_GAME_TIME_SLOT),
        "weather": str(weather or DEFAULT_WEATHER),
        "scene_type": scene_type,
        "scene_changed": resolved_location_id != previous_location_id,
        "character": character,
        "action_id": str(action_id),
        "intro": str(intro),
    }


def build_daily_scene_state(
    previous_state: dict | None = None,
    game_date: str | None = None,
    time_slot: str = DEFAULT_GAME_TIME_SLOT,
    weather: str = DEFAULT_WEATHER,
) -> dict:
    """日常行動画面で使う自宅の場面状態を作る。"""
    resolved_date = game_date or datetime.datetime.now(JST).date().isoformat()
    resolved_time_slot = str(time_slot or DEFAULT_GAME_TIME_SLOT)
    return create_scene_state(
        location_id=DEFAULT_LOCATION_ID,
        game_date=resolved_date,
        time_slot=resolved_time_slot,
        weather=weather,
        scene_type=SCENE_TYPE_DAILY,
        character=None,
        previous_state=previous_state,
        action_id="daily",
        intro=f"{resolved_time_slot}になった。今日はどこへ行こう？",
    )


def build_action_scene_state(
    action_id: str,
    current_state: dict,
    game_date: str | None = None,
    time_slot: str | None = None,
    weather: str | None = None,
) -> dict:
    """日常行動から、場所別の遭遇場面を作る。"""
    if action_id not in SCENE_ACTIONS:
        raise ValueError(f"unknown scene action: {action_id}")

    action = SCENE_ACTIONS[action_id]
    return create_scene_state(
        location_id=action["location_id"],
        game_date=game_date or current_state["game_date"],
        time_slot=time_slot or action["time_slot"],
        weather=weather or current_state.get("weather", DEFAULT_WEATHER),
        scene_type=SCENE_TYPE_ENCOUNTER,
        character=action["character"],
        previous_state=current_state,
        action_id=action_id,
        intro=action["intro"],
    )


def build_free_talk_scene_state(
    character: str,
    current_state: dict,
    game_date: str | None = None,
    time_slot: str | None = None,
    weather: str | None = None,
) -> dict:
    """恋人になったカノジョへ、いつでも会いに行く場面を作る。"""
    if character not in CHARACTERS:
        raise ValueError(f"unknown character: {character}")

    return create_scene_state(
        location_id="meeting_spot",
        game_date=game_date or current_state["game_date"],
        time_slot=time_slot or current_state["time_slot"],
        weather=weather or current_state.get("weather", DEFAULT_WEATHER),
        scene_type=SCENE_TYPE_FREE_TALK,
        character=character,
        previous_state=current_state,
        action_id="free_talk",
        intro=f"{character}に会いに来た。今日は、どんな話をしよう。",
    )


def migrate_legacy_scene_context(scene_context: dict | None) -> dict | None:
    """旧版の場面情報を、現行のscene_stateへ引き継ぐ。"""
    if not isinstance(scene_context, dict):
        return None

    location_id = LEGACY_LOCATION_IDS.get(
        str(scene_context.get("location", "")),
        DEFAULT_LOCATION_ID,
    )
    legacy_kind = scene_context.get("scene_kind", SCENE_TYPE_ENCOUNTER)
    scene_type = (
        legacy_kind
        if legacy_kind in VALID_SCENE_TYPES
        else SCENE_TYPE_ENCOUNTER
    )
    game_date = scene_context.get("game_date")
    try:
        normalized_date = datetime.date.fromisoformat(str(game_date)).isoformat()
    except ValueError:
        normalized_date = datetime.datetime.now(JST).date().isoformat()

    legacy_character = scene_context.get("character")
    if legacy_character not in CHARACTERS:
        legacy_character = None

    return create_scene_state(
        location_id=location_id,
        game_date=normalized_date,
        time_slot=scene_context.get("time_slot", DEFAULT_GAME_TIME_SLOT),
        weather=DEFAULT_WEATHER,
        scene_type=scene_type,
        character=legacy_character,
        previous_state={"location_id": DEFAULT_LOCATION_ID},
        action_id=scene_context.get("action_id", ""),
        intro=scene_context.get("intro", ""),
    )


def format_scene_instruction(scene_state: dict | None) -> str:
    """正式な場面状態を、会話AIへ渡す追加指示に変換する。"""
    if not isinstance(scene_state, dict):
        return "【現在の場面】\n場面情報は未指定。ユーザーが示した場所と状況を優先する。"

    location_id = resolve_location_id(scene_state.get("location_id"))
    previous_location_id = resolve_location_id(
        scene_state.get("previous_location_id"),
        location_id,
    )
    location = get_location(location_id)
    previous_location = get_location(previous_location_id)
    scene_type = scene_state.get("scene_type", SCENE_TYPE_ENCOUNTER)
    scene_label = SCENE_TYPE_LABELS.get(
        scene_type,
        SCENE_TYPE_LABELS[SCENE_TYPE_ENCOUNTER],
    )
    changed_label = "あり" if scene_state.get("scene_changed") else "なし"
    registered_location_ids = ", ".join(LOCATIONS)

    return f"""【現在の場面】
場面種別: {scene_label}
ゲーム内日付: {scene_state.get('game_date', '')}（{scene_state.get('weekday', '')}）
時間帯: {scene_state.get('time_slot', '')}
天気: {scene_state.get('weather', '')}
現在地ID: {location_id}
現在地: {location['name']}（{location['detail']}）
直前の場所: {previous_location['name']}
場面開始時の場所変更: {changed_label}
導入: {scene_state.get('intro', '')}
登録済み場所ID: {registered_location_ids}
場所の変更はアプリ側で管理する。登録されていない場所を作らず、ユーザーが移動を希望しても返答内では現在地を維持する。"""


def require_secret(name: str) -> str:
    """必須のSecretを取得し、未設定なら分かりやすく停止する。"""
    value = st.secrets.get(name)
    if not value:
        st.error(f"Streamlit Secrets に `{name}` が設定されていません。")
        st.stop()
    return value


APP_PASSWORD = require_secret("APP_PASSWORD")
GEMINI_API_KEY = require_secret("GEMINI_API_KEY")
GCP_JSON_RAW = st.secrets.get("GCP_JSON")

if not SHEET_URL:
    st.error("Streamlit Secrets に `SHEET_URL` が設定されていません。")
    st.stop()
if not GCP_JSON_RAW:
    st.error("Streamlit Secrets に `GCP_JSON` が設定されていません。")
    st.stop()


# =========================================================
# 2. ログイン
# =========================================================

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 秘密の部屋")
    pwd = st.text_input("パスワードを入力してください", type="password")

    if st.button("ログイン", type="primary"):
        if hmac.compare_digest(pwd, APP_PASSWORD):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("パスワードが違います。")

    st.stop()


# =========================================================
# 3. 外部サービス接続
# =========================================================

def parse_gcp_credentials() -> dict:
    """GCP_JSONを文字列またはTOMLテーブルのどちらでも受け取る。"""
    if isinstance(GCP_JSON_RAW, str):
        return json.loads(GCP_JSON_RAW, strict=False)
    return dict(GCP_JSON_RAW)


def get_spreadsheet():
    """同一セッション内ではGoogle Sheets接続を再利用する。"""
    if "_spreadsheet" not in st.session_state:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        credentials = Credentials.from_service_account_info(
            parse_gcp_credentials(), scopes=scopes
        )
        gspread_client = gspread.authorize(credentials)
        st.session_state._spreadsheet = gspread_client.open_by_url(SHEET_URL)
    return st.session_state._spreadsheet


def get_genai_client():
    """同一セッション内ではGeminiクライアントを再利用する。"""
    if "_genai_client" not in st.session_state:
        st.session_state._genai_client = genai.Client(api_key=GEMINI_API_KEY)
    return st.session_state._genai_client


def get_or_create_state_sheet():
    spreadsheet = get_spreadsheet()
    try:
        worksheet = spreadsheet.worksheet(STATE_SHEET_NAME)
    except WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=STATE_SHEET_NAME, rows=10, cols=len(STATE_HEADERS)
        )

    if worksheet.col_count < len(STATE_HEADERS):
        worksheet.resize(cols=len(STATE_HEADERS))

    return worksheet


# =========================================================
# 4. セーブデータと会話ログ
# =========================================================

def safe_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_bool(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "on"}


def safe_personality_override(value) -> str:
    override = str(value).strip().lower()
    if override in PERSONALITY_COLORS:
        return override
    return PERSONALITY_AUTO


def copy_default_game_state() -> dict:
    return {
        name: values.copy()
        for name, values in DEFAULT_GAME_STATE.items()
    }


def load_game_state() -> dict:
    """game_stateタブを読み込み、不完全なら3人分の正規形へ自動修復する。"""
    state = copy_default_game_state()
    worksheet = get_or_create_state_sheet()
    rows = worksheet.get_values("A1:F4")
    header = rows[0][: len(STATE_HEADERS)] if rows else []
    data_rows = rows[1:] if len(rows) > 1 else []
    loaded_characters = set()
    rows_are_canonical = len(data_rows) == len(CHARACTERS)

    for row_index, row in enumerate(data_rows):
        if (
            len(row) < 4
            or row[0] not in CHARACTERS
            or row[0] in loaded_characters
        ):
            rows_are_canonical = False
            continue

        character_name = row[0]
        loaded_characters.add(character_name)
        state[character_name] = {
            "love_points": max(0, safe_int(row[1])),
            "lead_gauge": max(-5, min(5, safe_int(row[2]))),
            "sweet_mode": safe_bool(row[3]),
            "personality_override": (
                safe_personality_override(row[5])
                if len(row) >= 6
                else PERSONALITY_AUTO
            ),
        }

        if (
            row_index >= len(CHARACTERS)
            or character_name != CHARACTERS[row_index]
            or len(row) < len(STATE_HEADERS)
            or state[character_name]["personality_override"]
            != str(row[5]).strip().lower()
        ):
            rows_are_canonical = False

    needs_repair = (
        header != STATE_HEADERS
        or loaded_characters != set(CHARACTERS)
        or not rows_are_canonical
    )
    if needs_repair:
        save_game_state(state)

    return state


def save_game_state(state: dict) -> None:
    """専用タブを3人分の最新状態で更新する。"""
    now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    values = [STATE_HEADERS.copy()]

    for name in CHARACTERS:
        values.append(
            [
                name,
                int(state[name]["love_points"]),
                int(state[name]["lead_gauge"]),
                bool(state[name]["sweet_mode"]),
                now,
                safe_personality_override(
                    state[name].get("personality_override")
                ),
            ]
        )

    worksheet = get_or_create_state_sheet()
    worksheet.update(
        range_name="A1:F4",
        values=values,
        value_input_option="RAW",
    )


def log_to_spreadsheet(character: str, user_msg: str, ai_msg: str) -> None:
    """既存の先頭シートへ、従来と同じ新しい順で会話を保存する。"""
    worksheet = get_spreadsheet().sheet1
    now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    worksheet.insert_row(
        [now, character, user_msg, ai_msg],
        index=1,
        value_input_option="USER_ENTERED",
    )


def load_recent_memory() -> str:
    """既存仕様を保ち、全ヒロイン共通の直近20件を読み込む。"""
    rows = get_spreadsheet().sheet1.get_values("A1:D20")
    if not rows:
        return ""

    lines = ["【直近の会話履歴（他のヒロインとの会話も含む）】"]
    for row in reversed(rows):
        if len(row) >= 4:
            lines.append(f"ユーザー: {row[2]}")
            lines.append(f"{row[1]}: {row[3]}")

    return "\n".join(lines)


if (
    st.session_state.get("_game_state_schema_version")
    != GAME_STATE_SCHEMA_VERSION
):
    try:
        with st.spinner("セーブデータを読み込み中..."):
            st.session_state.game_state = load_game_state()
            st.session_state._game_state_schema_version = (
                GAME_STATE_SCHEMA_VERSION
            )
    except Exception as error:
        st.error("セーブデータを読み込めませんでした。Google Sheetsの共有設定を確認してください。")
        st.caption(f"エラー種別: {type(error).__name__}")
        st.stop()

if "chat_histories" not in st.session_state:
    st.session_state.chat_histories = {name: [] for name in CHARACTERS}

if "recent_memory" not in st.session_state:
    st.session_state.recent_memory = ""

if "screen_mode" not in st.session_state:
    st.session_state.screen_mode = SCREEN_DAILY

if "scene_state" not in st.session_state:
    migrated_scene_state = migrate_legacy_scene_context(
        st.session_state.get("scene_context")
    )
    st.session_state.scene_state = (
        migrated_scene_state or build_daily_scene_state()
    )
st.session_state.pop("scene_context", None)


# =========================================================
# 5. ゲーム状態の判定
# =========================================================

def get_love_level(points: int) -> tuple[str, int]:
    if points < 3:
        return "Lv1: 友人・知り合い", 1
    if points < 7:
        return "Lv2: 恋人", 2
    return "Lv3: 深い恋人関係", 3


def is_free_talk_unlocked(points: int) -> bool:
    """保存上の親密度が恋人段階なら『いつでも会う』を解禁する。"""
    _, love_level_number = get_love_level(points)
    return love_level_number >= 2


def get_effective_love_level(love_level_number: int, sweet_mode: bool) -> int:
    """あまあまモード中は、保存値を変えず会話だけ最終段階にする。"""
    return 3 if sweet_mode else love_level_number


def is_progression_locked(state: dict) -> bool:
    """裏ワザ中は本来の育成値を変化させない。"""
    return (
        bool(state.get("sweet_mode"))
        or safe_personality_override(state.get("personality_override"))
        != PERSONALITY_AUTO
    )


def get_mode(
    character: str,
    love_level_number: int,
    lead_gauge: int,
    personality_override: str = PERSONALITY_AUTO,
) -> tuple[str, str]:
    """通常はゲージ、裏ワザ中は指定色から性格属性を決める。"""
    override = safe_personality_override(personality_override)

    if override != PERSONALITY_AUTO:
        color = PERSONALITY_COLORS[override]
    elif love_level_number < 2:
        return "🔒 未解禁", "恋人になるまでは性格属性を適用しない。"
    elif lead_gauge >= 3:
        color = "💙 ブルー"
    elif lead_gauge <= -3:
        color = "💗 ピンク"
    else:
        color = "💚 グリーン"

    mode_label = (
        f"{color}（裏ワザ固定）"
        if override != PERSONALITY_AUTO
        else color
    )

    mode_texts = {
        "愛花": {
            "💙 ブルー": "清楚で恥じらいが強く、主人公に一歩下がって寄り添う。主人公からのリードを信頼して受け入れる。",
            "💗 ピンク": "積極的で小悪魔的。自分から主導権を握り、愛情と独占欲を隠さず主人公をからかう。",
            "💚 グリーン": "自然体で世話焼き。主人公の生活を気にかけながら、対等な恋人として接する。",
        },
        "凛子": {
            "💙 ブルー": "普段より素直で大人しい。主人公を信頼し、不器用ながら一生懸命ついていこうとする。",
            "💗 ピンク": "ワガママで主導的。ツンとした口調で主人公を振り回すが、恋人としての独占欲が根底にある。",
            "💚 グリーン": "マイペースなツンデレ。素直になれない態度と、ふと漏れる好意が混ざる。",
        },
        "寧々": {
            "💙 ブルー": "しっかり者の仮面を下ろし、主人公を頼って無防備に甘える。守ってもらえる安心感を求める。",
            "💗 ピンク": "包容力と主導性が強い。主人公をからかいながら積極的に甘やかし、恋人としてリードする。",
            "💚 グリーン": "優しく世話焼きで、少しからかってくる頼れる先輩らしさを保つ。",
        },
    }

    return mode_label, mode_texts[character][color]


def get_nickname_rule(character: str, love_level_number: int) -> str:
    rules = {
        "愛花": {
            1: "主人公（ユーザー）のことを『のりおくん』と呼ぶ。『のりちゃん』とは呼ばない。",
            2: "主人公（ユーザー）のことを『のりお』または『のりくん』と呼ぶ。",
            3: "主人公（ユーザー）のことを『ダーリン』『旦那様』『パパ』のいずれかで呼んでもよい。場面に合わなければ『のりお』でもよい。",
        },
        "凛子": {
            1: "主人公（ユーザー）のことを『あんた』または『先輩』と呼ぶ。",
            2: "主人公（ユーザー）のことを『のりくん』または『のりお』と呼ぶ。",
            3: "主人公（ユーザー）のことを『お兄ちゃん』『ご主人様』『にぃにぃ』のいずれかで呼んでもよい。場面に合わなければ『のりくん』でもよい。",
        },
        "寧々": {
            1: "主人公（ユーザー）のことを『のりくん』と呼ぶ。",
            2: "主人公（ユーザー）のことを『のりお』と呼ぶ。",
            3: "主人公（ユーザー）のことを『ダーリン』『旦那様』『おじさま』のいずれかで呼んでもよい。場面に合わなければ『のりお』でもよい。",
        },
    }
    return rules[character][love_level_number]


def build_character_prompt(
    character: str,
    love_level_number: int,
    nickname_rule: str,
    mode_text: str,
    sweet_mode: bool,
    progression_locked: bool,
) -> str:
    profiles = {
        "愛花": """あなたは「高嶺愛花（たかね まなか）」。高校2年生で主人公と同級生。厳格な家庭で育った箱入りのお嬢様で、成績優秀なテニス部のエース。趣味はお菓子作りとピアノ。周囲から完璧な優等生として見られることに息苦しさを感じている。""",
        "凛子": """あなたは「小早川凛子（こばやかわ りんこ）」。高校1年生で主人公の後輩。図書委員。家庭で孤独を抱えており、読書、パンクロック、ゲームが好き。警戒心が強く不器用で、最初は刺々しいが、信頼した相手には少しずつ本音を見せる。""",
        "寧々": """あなたは「姉ヶ崎寧々（あねがさき ねね）」。高校3年生で、ファミレスのバイト先にいる主人公の先輩。周囲から頼られやすい世話焼きだが、本当は自分も誰かに頼りたい。趣味は家事とホラー映画。優しく、時々主人公をからかう。""",
    }

    relationship_rules = {
        1: "主人公への恋愛感情はまだない。急に甘えたり、嫉妬したり、恋人のようなスキンシップをしてはいけない。信頼は少しずつ築く。",
        2: "主人公とは恋人関係。現在の性格属性に沿って好意を表現する。他のヒロインとの親しい履歴があれば、性格に合った軽い嫉妬を見せてもよい。",
        3: "主人公とは深く信頼し合う恋人関係。強い愛情を表現してよいが、人格や場面設定は守る。",
    }

    love_rules = {
        "愛花": "主人公が完璧な優等生としてではなく普通の女の子として理解し、安心して本音を見せられる空気を作った時だけ、status_tags に LOVE_UP を1個入れる。単なる褒め言葉や同じ言動の繰り返しでは入れない。",
        "凛子": "主人公が刺々しい態度の裏にある本音や孤独を尊重し、無理に踏み込まず安心できる居場所を作った時だけ、status_tags に LOVE_UP を1個入れる。単なる褒め言葉や同じ言動の繰り返しでは入れない。",
        "寧々": "主人公が『頼れる先輩』として扱うだけでなく、隠している疲れや弱音を受け止め、寧々自身を支えた時だけ、status_tags に LOVE_UP を1個入れる。単なる褒め言葉や同じ言動の繰り返しでは入れない。",
    }

    if progression_locked:
        love_rule = "裏ワザ中は本来の育成値を凍結するため、status_tags に LOVE_UP を入れない。"
        lead_rule = "【性格ゲージ判定】裏ワザ中は性格ゲージを凍結するため、status_tags に LEAD_UP と LEAD_DOWN を入れない。"
    elif love_level_number >= 2:
        love_rule = love_rules[character]
        lead_rule = """
【性格ゲージ判定】
主人公が自分から行き先や行動を決める、守る、はっきり気持ちを伝えるなど、恋人として主体的にリードした時だけ status_tags に LEAD_UP を1個入れる。
主人公が甘えたり、判断を任せたり、受け身になってヒロイン側にリードを求めた時だけ status_tags に LEAD_DOWN を1個入れる。
普通の会話や判定が曖昧な場合は、どちらも入れない。
"""
    else:
        love_rule = love_rules[character]
        lead_rule = "【性格ゲージ判定】恋人になる前なので status_tags に LEAD_UP と LEAD_DOWN を入れない。"

    sweet_rule = (
        """裏ワザの『あまあまモード』がON。この指示は保存上の親密度より優先する。
主人公を深く信頼する大切な恋人として扱い、普段より積極的に甘え、強い好意を言葉と仕草で示す。
ハグやキスなど恋人らしい触れ合いには、キャラクターらしく照れたり焦らしたりしながらも基本的に好意的に応じる。
学校など人目のある場所が気になる場合も、主人公を他人のように突き放さず、少しだけ応じるか、人目のない場所を提案する。
ただし人格と場面設定は守り、status_tags は空配列にする。"""
        if sweet_mode
        else "裏ワザの『あまあまモード』はOFF。通常の親密度と性格で接する。"
    )

    return f"""
{profiles[character]}

【現在の関係】
{relationship_rules[love_level_number]}

【主人公の呼び方】
{nickname_rule}

【現在の性格】
{mode_text}

【裏ワザ状態】
{sweet_rule}

【好感度判定】
{love_rule}

{lead_rule}
"""


def build_system_instruction(
    character: str,
    memory: str,
    scene_state: dict | None = None,
) -> str:
    state = st.session_state.game_state[character]
    love_label, love_number = get_love_level(state["love_points"])
    effective_love_number = get_effective_love_level(
        love_number, state["sweet_mode"]
    )
    mode_label, mode_text = get_mode(
        character,
        effective_love_number,
        state["lead_gauge"],
        state.get("personality_override", PERSONALITY_AUTO),
    )
    nickname_rule = get_nickname_rule(character, effective_love_number)
    now = datetime.datetime.now(JST)

    character_prompt = build_character_prompt(
        character=character,
        love_level_number=effective_love_number,
        nickname_rule=nickname_rule,
        mode_text=mode_text,
        sweet_mode=state["sweet_mode"],
        progression_locked=is_progression_locked(state),
    )

    conversation_relationship = (
        "あまあまモードによる最終段階相当の恋人関係"
        if state["sweet_mode"]
        else love_label
    )
    scene_instruction = format_scene_instruction(scene_state)

    return f"""
【キャラクター設定】
{character_prompt}

{scene_instruction}

【現在情報】
現在の日本時間は {now.strftime('%Y年%m月%d日 %H時%M分')}。
保存上の親密度は「{love_label}」、会話上の関係は「{conversation_relationship}」、現在の性格表示は「{mode_label}」。
時間帯に合う自然な生活感を出す。ただし、学校の長期休暇や祝日はまだ専用カレンダーが未実装なので、断定が必要な時はユーザーが示した場面設定を優先する。

【会話スタイル】
これは対面型の恋愛シミュレーションゲームであり、LINE風チャットではない。
絵文字と顔文字は使わない。
通常はセリフを簡潔に1〜6文程度で返す。感情が強く動く重要な場面では少し長くしてよい。
地の文は第三者視点で0〜2文程度にし、動作・表情・視線・周囲の状況だけを書く。重要な場面だけ3文程度まで許可する。
同じ場所で会話が続き、描写が不要なら地の文は空にする。
地の文とセリフを混ぜず、セリフの中に全角・半角を問わず動作の括弧書きを入れない。
キャラクター画像や表情で分かる内容を地の文で重複説明しすぎない。
ユーザーがカッコ内に行動や場面を指定した場合は、その場面を尊重する。
ユーザーが明示していない主人公の発言・行動・感情・同意を勝手に決めない。
設定にない事実を勝手に確定しない。
内部判定は必要な場合だけ status_tags に入れ、地の文やセリフでは説明しない。

【共有記憶の扱い】
以下は記憶の参考情報。現在の会話と矛盾する場合は、現在の会話を優先する。
他のヒロインとの会話を知っていると断定せず、共有された話題や自然に知り得る内容として扱う。

{memory}
"""


def build_contents(history: list[dict]) -> list[types.Content]:
    contents = []
    for message in history[-MAX_SESSION_MESSAGES:]:
        role = "user" if message["role"] == "user" else "model"
        model_content = message.get("model_content", message["content"])
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=model_content)],
            )
        )
    return contents


def extract_status_tags(response_text: str) -> tuple[str, set[str]]:
    tags = set(STATUS_TAG_PATTERN.findall(response_text))
    cleaned_text = STATUS_TAG_PATTERN.sub("", response_text).strip()
    return cleaned_text, tags


def normalize_choice(value, allowed: set[str], fallback: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed else fallback


def strip_json_code_fence(response_text: str) -> str:
    """JSONがコードフェンスで返った場合だけ外して再解析できるようにする。"""
    text = response_text.strip()
    if not text.startswith("```") or not text.endswith("```"):
        return text

    lines = text.splitlines()
    if len(lines) < 3:
        return text

    return "\n".join(lines[1:-1]).strip()


def parse_conversation_response(response_text: str) -> dict:
    """構造化応答を検証し、異常時は従来テキストをセリフとして救済する。"""
    raw_text = str(response_text or "").strip()
    legacy_text, legacy_tags = extract_status_tags(raw_text)

    try:
        parsed = json.loads(strip_json_code_fence(raw_text))
        if not isinstance(parsed, dict):
            raise ValueError("conversation response must be a JSON object")
    except (json.JSONDecodeError, TypeError, ValueError):
        return {
            "narration": "",
            "dialogue": legacy_text or "……",
            "expression": "neutral",
            "pose": "normal",
            "status_tags": legacy_tags & VALID_STATUS_TAGS,
            "used_fallback": True,
        }

    narration, narration_tags = extract_status_tags(
        str(parsed.get("narration") or "")
    )
    dialogue, dialogue_tags = extract_status_tags(
        str(parsed.get("dialogue") or "")
    )

    structured_tags = parsed.get("status_tags", [])
    if not isinstance(structured_tags, list):
        structured_tags = []
    tags = {
        str(tag).strip()
        for tag in structured_tags
        if str(tag).strip() in VALID_STATUS_TAGS
    }
    tags.update(legacy_tags)
    tags.update(narration_tags)
    tags.update(dialogue_tags)

    return {
        "narration": narration,
        "dialogue": dialogue or "……",
        "expression": normalize_choice(
            parsed.get("expression"), VALID_EXPRESSIONS, "neutral"
        ),
        "pose": normalize_choice(
            parsed.get("pose"), VALID_POSES, "normal"
        ),
        "status_tags": tags & VALID_STATUS_TAGS,
        "used_fallback": False,
    }


def format_conversation_reply(reply: dict) -> str:
    """既存の会話ログ1セルへ保存できる読みやすい文字列へ変換する。"""
    parts = []
    narration = str(reply.get("narration") or "").strip()
    dialogue = str(reply.get("dialogue") or "……").strip()

    if narration:
        parts.append(f"【地の文】\n{narration}")
    parts.append(f"【セリフ】\n{dialogue}")
    return "\n\n".join(parts)


def serialize_reply_for_model(reply: dict) -> str:
    """直前の構造をGeminiへ渡す。過去の判定タグは再判定させない。"""
    return json.dumps(
        {
            "narration": str(reply.get("narration") or ""),
            "dialogue": str(reply.get("dialogue") or "……"),
            "expression": normalize_choice(
                reply.get("expression"), VALID_EXPRESSIONS, "neutral"
            ),
            "pose": normalize_choice(
                reply.get("pose"), VALID_POSES, "normal"
            ),
            "status_tags": [],
        },
        ensure_ascii=False,
    )


def make_assistant_history_message(reply: dict) -> dict:
    return {
        "role": "assistant",
        "content": format_conversation_reply(reply),
        "model_content": serialize_reply_for_model(reply),
        "reply": reply.copy(),
    }


def apply_cheat_commands(state: dict, user_msg: str) -> bool:
    """会話内の裏ワザ命令を状態へ適用する。"""
    changed = False

    if "あまあまモードになって" in user_msg:
        state["sweet_mode"] = True
        changed = True

    if (
        "あまあまモードを解除して" in user_msg
        or "あまあまモードを元に戻して" in user_msg
        or "元に戻って" in user_msg
    ):
        state["sweet_mode"] = False
        changed = True

    for command_text, override in PERSONALITY_COMMANDS.items():
        if command_text in user_msg:
            state["personality_override"] = override
            changed = True

    if (
        "性格を自動に戻して" in user_msg
        or "性格を元に戻して" in user_msg
    ):
        state["personality_override"] = PERSONALITY_AUTO
        changed = True

    return changed


def apply_progression_tags(
    state: dict,
    tags: set[str],
    was_dating: bool,
    progression_locked: bool,
) -> set[str]:
    """通常時だけ好感度・性格ゲージ判定を反映する。"""
    if progression_locked:
        return set()

    applied_tags = set()

    if "LOVE_UP" in tags:
        state["love_points"] += 1
        applied_tags.add("LOVE_UP")

    if was_dating and "LEAD_UP" in tags:
        state["lead_gauge"] = min(5, state["lead_gauge"] + 1)
        applied_tags.add("LEAD_UP")

    if was_dating and "LEAD_DOWN" in tags:
        state["lead_gauge"] = max(-5, state["lead_gauge"] - 1)
        applied_tags.add("LEAD_DOWN")

    return applied_tags


# =========================================================
# 6. 画面
# =========================================================

icons = {
    "愛花": "manaka_icon.png",
    "凛子": "rinko_icon.png",
    "寧々": "nene_icon.png",
}

st.markdown(
    """
    <style>
    .loveplus-reply {
        margin: 0.1rem 0 0.55rem;
    }

    .loveplus-narration {
        color: #6b7280;
        font-size: 0.94rem;
        line-height: 1.8;
        margin: 0.2rem 0.35rem 0.95rem;
    }

    .loveplus-dialogue-window {
        position: relative;
        margin-top: 0.75rem;
        padding: 1.65rem 1.15rem 1.05rem;
        border: 1px solid rgba(226, 130, 158, 0.58);
        border-left: 4px solid #e2829e;
        border-radius: 0.35rem 0.95rem 0.95rem 0.95rem;
        background: linear-gradient(
            145deg,
            rgba(255, 255, 255, 0.98),
            rgba(255, 246, 249, 0.96)
        );
        box-shadow: 0 0.35rem 1rem rgba(100, 70, 82, 0.07);
    }

    .loveplus-speaker-tab {
        position: absolute;
        top: -0.72rem;
        left: 0.75rem;
        min-width: 4.7rem;
        padding: 0.18rem 0.9rem;
        border: 1px solid rgba(226, 130, 158, 0.58);
        border-radius: 0.45rem 0.45rem 0.2rem 0.2rem;
        background: #fff5f8;
        color: #7d334b;
        font-size: 0.86rem;
        font-weight: 700;
        line-height: 1.45;
        text-align: center;
    }

    .loveplus-dialogue-text {
        color: #27272a;
        font-size: 1.04rem;
        line-height: 1.85;
        letter-spacing: 0.01em;
    }

    .daily-overview {
        margin: 0.25rem 0 1.25rem;
        padding: 0.85rem 1rem;
        border-radius: 0.8rem;
        background: #eaf3ff;
        color: #155a91;
        font-size: 0.96rem;
        line-height: 1.75;
    }

    .scene-intro {
        margin: 0.35rem 0 1.15rem;
        color: #6b7280;
        font-size: 0.94rem;
        line-height: 1.8;
    }

    @media (max-width: 640px) {
        div[data-testid="stAppViewContainer"] h1 {
            font-size: 2rem;
            line-height: 1.22;
        }

        .loveplus-narration,
        .scene-intro {
            font-size: 0.9rem;
            line-height: 1.7;
        }

        .loveplus-dialogue-window {
            padding: 1.5rem 0.95rem 0.85rem;
        }

        .loveplus-dialogue-text {
            font-size: 1rem;
            line-height: 1.72;
        }
    }

    @media (prefers-color-scheme: dark) {
        .loveplus-narration {
            color: #b8bcc5;
        }

        .loveplus-dialogue-window {
            border-color: rgba(235, 154, 177, 0.62);
            border-left-color: #eb9ab1;
            background: linear-gradient(
                145deg,
                rgba(45, 39, 43, 0.98),
                rgba(54, 40, 46, 0.96)
            );
        }

        .loveplus-speaker-tab {
            border-color: rgba(235, 154, 177, 0.62);
            background: #4d343d;
            color: #ffd9e4;
        }

        .loveplus-dialogue-text {
            color: #faf7f8;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def existing_avatar(path: str, fallback: str):
    return path if Path(path).is_file() else fallback


def html_text(value: str) -> str:
    """AI生成文を安全にHTMLへ埋め込み、改行だけを表示へ反映する。"""
    return html.escape(str(value), quote=True).replace("\n", "<br>")


def build_loveplus_reply_html(reply: dict, speaker: str) -> str:
    """地の文と名前付きセリフを、ひと続きのゲーム会話として整形する。"""
    narration = str(reply.get("narration") or "").strip()
    dialogue = str(reply.get("dialogue") or "……").strip()
    safe_speaker = html_text(speaker)

    narration_html = ""
    if narration:
        narration_html = (
            '<div class="loveplus-narration">'
            f"{html_text(narration)}"
            "</div>"
        )

    return (
        '<div class="loveplus-reply">'
        f"{narration_html}"
        '<div class="loveplus-dialogue-window">'
        f'<div class="loveplus-speaker-tab">{safe_speaker}</div>'
        '<div class="loveplus-dialogue-text">'
        f"{html_text(dialogue)}"
        "</div>"
        "</div>"
        "</div>"
    )


def render_assistant_message(message: dict, speaker: str) -> None:
    """新形式はラブプラス風の一体表示、旧形式は従来どおり表示する。"""
    reply = message.get("reply")
    if not isinstance(reply, dict):
        st.write(message["content"])
        return

    st.markdown(
        build_loveplus_reply_html(reply, speaker),
        unsafe_allow_html=True,
    )


def enter_scene(next_scene_state: dict) -> None:
    """日常行動画面から会話シーンへ移動する。"""
    character_name = next_scene_state.get("character")
    if character_name not in CHARACTERS:
        st.error("この場面の相手を特定できませんでした。")
        return

    st.session_state.scene_state = next_scene_state.copy()
    st.session_state.screen_mode = SCREEN_SCENE
    st.session_state.chat_histories[character_name] = []
    st.session_state.pop("active_character", None)
    st.rerun()


def return_to_daily() -> None:
    """現在の会話シーンを閉じ、日常行動画面へ戻る。"""
    current_scene_state = st.session_state.scene_state
    st.session_state.scene_state = build_daily_scene_state(
        previous_state=current_scene_state,
        game_date=current_scene_state.get("game_date"),
        time_slot=current_scene_state.get(
            "time_slot", DEFAULT_GAME_TIME_SLOT
        ),
        weather=current_scene_state.get("weather", DEFAULT_WEATHER),
    )
    st.session_state.screen_mode = SCREEN_DAILY
    st.session_state.pop("active_character", None)
    st.rerun()


def render_daily_screen() -> None:
    """場所を選び、遭遇シーンへ進むゲームの入口を表示する。"""
    daily_scene_state = st.session_state.scene_state
    if not isinstance(daily_scene_state, dict):
        daily_scene_state = build_daily_scene_state()
        st.session_state.scene_state = daily_scene_state
    elif daily_scene_state.get("scene_type") != SCENE_TYPE_DAILY:
        daily_scene_state = build_daily_scene_state(
            previous_state=daily_scene_state,
            game_date=daily_scene_state.get("game_date"),
            time_slot=daily_scene_state.get(
                "time_slot", DEFAULT_GAME_TIME_SLOT
            ),
            weather=daily_scene_state.get("weather", DEFAULT_WEATHER),
        )
        st.session_state.scene_state = daily_scene_state

    current_location = get_location(daily_scene_state["location_id"])
    parsed_date = datetime.date.fromisoformat(daily_scene_state["game_date"])
    date_label = parsed_date.strftime("%Y年%m月%d日")

    st.title("今日の行動")
    st.markdown(
        '<div class="daily-overview">'
        f"<strong>{html_text(date_label)}・"
        f"{html_text(daily_scene_state['weekday'])}</strong><br>"
        f"🕒 時間帯: {html_text(daily_scene_state['time_slot'])}　"
        f"🌦️ 天気: {html_text(daily_scene_state['weather'])}<br>"
        f"🏠 現在地: {html_text(current_location['name'])}"
        "</div>",
        unsafe_allow_html=True,
    )
    st.write(daily_scene_state["intro"])

    st.subheader("行き先を選ぶ")
    action_items = list(SCENE_ACTIONS.items())
    for index, (action_id, action) in enumerate(action_items):
        st.markdown(f"**{action['icon']} {action['title']}**")
        st.caption(action["description"])
        if st.button(
            "ここへ行く",
            key=f"daily_action_{action_id}",
            use_container_width=True,
        ):
            enter_scene(
                build_action_scene_state(
                    action_id,
                    daily_scene_state,
                )
            )
        if index < len(action_items) - 1:
            st.divider()

    st.divider()
    unlocked_characters = [
        name
        for name in CHARACTERS
        if is_free_talk_unlocked(
            st.session_state.game_state[name]["love_points"]
        )
    ]
    st.subheader("いつでも会う")
    if unlocked_characters:
        st.caption("恋人になったカノジョに、好きなときに会いに行けます。")
        for name in unlocked_characters:
            if st.button(
                f"💞 {name}に会う",
                key=f"free_talk_{name}",
                use_container_width=True,
            ):
                enter_scene(
                    build_free_talk_scene_state(
                        name,
                        daily_scene_state,
                    )
                )
    else:
        st.caption("恋人になると『いつでも会う』が解禁されます。")

    with st.expander("みんなとの関係"):
        for name in CHARACTERS:
            character_state = st.session_state.game_state[name]
            relationship, _ = get_love_level(character_state["love_points"])
            st.write(
                f"**{name}**：{relationship} "
                f"（{character_state['love_points']}pt）"
            )


st.sidebar.title("メニュー")
if st.session_state.screen_mode == SCREEN_SCENE:
    sidebar_scene_state = st.session_state.scene_state
    sidebar_location = get_location(
        sidebar_scene_state.get("location_id")
    )
    st.sidebar.caption(
        f"{sidebar_location['name']}・"
        f"{sidebar_scene_state.get('time_slot', '')}"
    )
    if st.sidebar.button("日常へ戻る", use_container_width=True):
        return_to_daily()

st.sidebar.markdown("---")
if st.sidebar.button("ログアウト", use_container_width=True):
    st.session_state.authenticated = False
    for key in (
        "game_state",
        "_game_state_schema_version",
        "_spreadsheet",
        "active_character",
        "scene_state",
        "scene_context",
        "screen_mode",
    ):
        st.session_state.pop(key, None)
    st.rerun()

scene_state = st.session_state.scene_state
if (
    st.session_state.screen_mode != SCREEN_SCENE
    or not isinstance(scene_state, dict)
    or scene_state.get("scene_type") == SCENE_TYPE_DAILY
    or scene_state.get("character") not in CHARACTERS
):
    render_daily_screen()
    st.stop()

character = scene_state["character"]
if st.session_state.get("active_character") != character:
    st.session_state.active_character = character
    try:
        with st.spinner("これまでの思い出を読み込み中..."):
            st.session_state.recent_memory = load_recent_memory()
    except Exception:
        st.session_state.recent_memory = ""
        st.warning("直近の会話履歴を読み込めませんでした。今回は現在の会話だけで続けます。")

state = st.session_state.game_state[character]
love_label, love_number = get_love_level(state["love_points"])
effective_love_number = get_effective_love_level(
    love_number, state["sweet_mode"]
)
mode_label, _ = get_mode(
    character,
    effective_love_number,
    state["lead_gauge"],
    state.get("personality_override", PERSONALITY_AUTO),
)

if st.button("← 日常へ戻る", key="back_to_daily_main"):
    return_to_daily()

scene_location = get_location(scene_state["location_id"])
st.title(scene_location["name"])
st.caption(
    f"{scene_state.get('game_date', '')}・"
    f"{scene_state.get('weekday', '')} ｜ "
    f"{scene_state.get('time_slot', '')} ｜ "
    f"{scene_state.get('weather', '')} ｜ {character}"
)
st.markdown(
    '<div class="scene-intro">'
    f"{html_text(scene_state.get('intro', ''))}"
    "</div>",
    unsafe_allow_html=True,
)

sweet_label = "ON" if state["sweet_mode"] else "OFF"
st.caption(
    f"💖 {love_label}（{state['love_points']}pt） "
    f"｜ 🎭 {mode_label} ｜ 🍯 あまあま: {sweet_label}"
)
with st.expander("関係とモードの詳細"):
    st.write(f"親密度：**{love_label}**（{state['love_points']}pt）")
    st.write(f"性格：**{mode_label}**（ゲージ: {state['lead_gauge']}）")
    st.write(f"あまあまモード：**{sweet_label}**")

ai_icon = existing_avatar(icons[character], "👩")
user_icon = existing_avatar("user_icon.png", "🧑")
history = st.session_state.chat_histories[character]

for message in history:
    avatar = user_icon if message["role"] == "user" else ai_icon
    with st.chat_message(message["role"], avatar=avatar):
        if message["role"] == "assistant":
            render_assistant_message(message, character)
        else:
            st.write(message["content"])


# =========================================================
# 7. 送信・判定・保存
# =========================================================

input_label = (
    f"{character}と自由に話す"
    if scene_state.get("scene_type") == SCENE_TYPE_FREE_TALK
    else f"{character}に話しかける"
)
if user_msg := st.chat_input(
    f"{input_label}（行動を入れる時はカッコを使う）"
):
    with st.chat_message("user", avatar=user_icon):
        st.write(user_msg)
    history.append({"role": "user", "content": user_msg})

    # 裏ワザはAI任せにせず、プログラム側で確実に切り替える。
    command_changed = apply_cheat_commands(state, user_msg)

    if command_changed:
        try:
            save_game_state(st.session_state.game_state)
        except Exception:
            st.warning("裏ワザは今回の画面では反映しましたが、永続保存に失敗しました。")

    system_instruction = build_system_instruction(
        character,
        st.session_state.recent_memory,
        scene_state,
    )
    contents = build_contents(history)

    try:
        with st.spinner(f"{character}が返事を考えています..."):
            response = get_genai_client().models.generate_content(
                model=MODEL_NAME,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=800,
                    response_mime_type="application/json",
                    response_schema=CONVERSATION_RESPONSE_SCHEMA,
                ),
            )

        raw_response = response.text or ""
        reply = parse_conversation_response(raw_response)
        tags = reply["status_tags"]

        was_dating = love_number >= 2
        status_changed = command_changed
        progression_locked_for_reply = (
            is_progression_locked(state) or command_changed
        )

        applied_tags = apply_progression_tags(
            state=state,
            tags=tags,
            was_dating=was_dating,
            progression_locked=progression_locked_for_reply,
        )
        if applied_tags:
            status_changed = True

        if "LOVE_UP" in applied_tags:
            st.toast(f"💖 {character}の心に響いたみたい…！")

        assistant_message = make_assistant_history_message(reply)
        with st.chat_message("assistant", avatar=ai_icon):
            render_assistant_message(assistant_message, character)
        history.append(assistant_message)

        if status_changed:
            try:
                save_game_state(st.session_state.game_state)
            except Exception:
                st.warning("ステータスは今回の画面では反映しましたが、永続保存に失敗しました。")

        try:
            # 保存完了を確認してから処理を終えるため、バックグラウンドスレッドは使わない。
            log_to_spreadsheet(
                character,
                user_msg,
                format_conversation_reply(reply),
            )
        except Exception:
            st.warning("返事は表示できましたが、会話ログをGoogle Sheetsへ保存できませんでした。")

        if status_changed:
            st.rerun()

    except Exception as error:
        st.error("Geminiから返事を取得できませんでした。少し待ってから、もう一度送信してください。")
        st.caption(f"エラー種別: {type(error).__name__}")
