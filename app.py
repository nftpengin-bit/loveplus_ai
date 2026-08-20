import datetime
import hmac
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
MODEL_NAME = st.secrets.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
SHEET_URL = st.secrets.get("SHEET_URL", "")
STATE_SHEET_NAME = "game_state"
GAME_STATE_SCHEMA_VERSION = 1
MAX_SESSION_MESSAGES = 16

DEFAULT_GAME_STATE = {
    name: {"love_points": 0, "lead_gauge": 0, "sweet_mode": False}
    for name in CHARACTERS
}
STATE_HEADERS = [
    "character",
    "love_points",
    "lead_gauge",
    "sweet_mode",
    "updated_at",
]

STATUS_TAG_PATTERN = re.compile(r"\[(LOVE_UP|LEAD_UP|LEAD_DOWN)\]")


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
        return spreadsheet.worksheet(STATE_SHEET_NAME)
    except WorksheetNotFound:
        return spreadsheet.add_worksheet(
            title=STATE_SHEET_NAME, rows=10, cols=5
        )


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


def copy_default_game_state() -> dict:
    return {
        name: values.copy()
        for name, values in DEFAULT_GAME_STATE.items()
    }


def load_game_state() -> dict:
    """game_stateタブを読み込み、不完全なら3人分の正規形へ自動修復する。"""
    state = copy_default_game_state()
    worksheet = get_or_create_state_sheet()
    rows = worksheet.get_values("A1:E4")
    header = rows[0][:5] if rows else []
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
        }

        if (
            row_index >= len(CHARACTERS)
            or character_name != CHARACTERS[row_index]
            or len(row) < 5
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
            ]
        )

    worksheet = get_or_create_state_sheet()
    worksheet.update(
        range_name="A1:E4",
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


# =========================================================
# 5. ゲーム状態の判定
# =========================================================

def get_love_level(points: int) -> tuple[str, int]:
    if points < 3:
        return "Lv1: 友人・知り合い", 1
    if points < 7:
        return "Lv2: 恋人", 2
    return "Lv3: 深い恋人関係", 3


def get_mode(character: str, love_level_number: int, lead_gauge: int) -> tuple[str, str]:
    """性格属性は恋人になった後だけ有効にする。"""
    if love_level_number < 2:
        return "🔒 未解禁", "恋人になるまでは性格属性を適用しない。"

    if lead_gauge >= 3:
        color = "💙 ブルー"
    elif lead_gauge <= -3:
        color = "💗 ピンク"
    else:
        color = "💚 グリーン"

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

    return color, mode_texts[character][color]


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
        "愛花": "主人公が完璧な優等生としてではなく普通の女の子として理解し、安心して本音を見せられる空気を作った時だけ、返信末尾に [LOVE_UP] を1個付ける。単なる褒め言葉や同じ言動の繰り返しでは付けない。",
        "凛子": "主人公が刺々しい態度の裏にある本音や孤独を尊重し、無理に踏み込まず安心できる居場所を作った時だけ、返信末尾に [LOVE_UP] を1個付ける。単なる褒め言葉や同じ言動の繰り返しでは付けない。",
        "寧々": "主人公が『頼れる先輩』として扱うだけでなく、隠している疲れや弱音を受け止め、寧々自身を支えた時だけ、返信末尾に [LOVE_UP] を1個付ける。単なる褒め言葉や同じ言動の繰り返しでは付けない。",
    }

    if love_level_number >= 2:
        lead_rule = """
【性格ゲージ判定】
主人公が自分から行き先や行動を決める、守る、はっきり気持ちを伝えるなど、恋人として主体的にリードした時だけ [LEAD_UP] を返信末尾に1個付ける。
主人公が甘えたり、判断を任せたり、受け身になってヒロイン側にリードを求めた時だけ [LEAD_DOWN] を返信末尾に1個付ける。
普通の会話や判定が曖昧な場合は、どちらも付けない。
"""
    else:
        lead_rule = "【性格ゲージ判定】恋人になる前なので [LEAD_UP] と [LEAD_DOWN] は出力しない。"

    sweet_rule = (
        "裏ワザの『あまあまモード』がON。親密度による関係そのものは変えず、その範囲内で普段より優しく好意的に接する。"
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
{love_rules[character]}

{lead_rule}
"""


def build_system_instruction(character: str, memory: str) -> str:
    state = st.session_state.game_state[character]
    love_label, love_number = get_love_level(state["love_points"])
    mode_label, mode_text = get_mode(character, love_number, state["lead_gauge"])
    nickname_rule = get_nickname_rule(character, love_number)
    now = datetime.datetime.now(JST)

    character_prompt = build_character_prompt(
        character=character,
        love_level_number=love_number,
        nickname_rule=nickname_rule,
        mode_text=mode_text,
        sweet_mode=state["sweet_mode"],
    )

    return f"""
【キャラクター設定】
{character_prompt}

【現在情報】
現在の日本時間は {now.strftime('%Y年%m月%d日 %H時%M分')}。
現在の親密度は「{love_label}」、現在の性格表示は「{mode_label}」。
時間帯に合う自然な生活感を出す。ただし、学校の長期休暇や祝日はまだ専用カレンダーが未実装なので、断定が必要な時はユーザーが示した場面設定を優先する。

【会話スタイル】
これは対面型の恋愛シミュレーションゲームであり、LINE風チャットではない。
絵文字と顔文字は使わない。
通常は簡潔に2〜6文程度で返す。感情が強く動く重要な場面では少し長くしてよい。
表情や仕草は、必要な時だけ短い全角カッコ（ ）で表現する。
ユーザーがカッコ内に行動や場面を指定した場合は、その場面を尊重する。
設定にない事実を勝手に確定しない。
内部判定タグは必要な場合だけ返信の最後に置き、本文中では説明しない。

【共有記憶の扱い】
以下は記憶の参考情報。現在の会話と矛盾する場合は、現在の会話を優先する。
他のヒロインとの会話を知っていると断定せず、共有された話題や自然に知り得る内容として扱う。

{memory}
"""


def build_contents(history: list[dict]) -> list[types.Content]:
    contents = []
    for message in history[-MAX_SESSION_MESSAGES:]:
        role = "user" if message["role"] == "user" else "model"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=message["content"])],
            )
        )
    return contents


def extract_status_tags(response_text: str) -> tuple[str, set[str]]:
    tags = set(STATUS_TAG_PATTERN.findall(response_text))
    cleaned_text = STATUS_TAG_PATTERN.sub("", response_text).strip()
    return cleaned_text, tags


# =========================================================
# 6. 画面
# =========================================================

st.sidebar.title("ヒロイン選択")
character = st.sidebar.radio("誰と話す？", CHARACTERS)
st.sidebar.markdown("---")

if st.sidebar.button("ログアウト"):
    st.session_state.authenticated = False
    st.session_state.pop("game_state", None)
    st.session_state.pop("_game_state_schema_version", None)
    st.session_state.pop("_spreadsheet", None)
    st.rerun()

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
mode_label, _ = get_mode(character, love_number, state["lead_gauge"])

st.title(f"{character}とのチャットルーム")

sweet_label = "ON" if state["sweet_mode"] else "OFF"
st.info(
    f"💖 親密度: **{love_label}**（{state['love_points']}pt） "
    f"│ 🎭 性格: **{mode_label}**（ゲージ: {state['lead_gauge']}） "
    f"│ 🍯 あまあま: **{sweet_label}**"
)

icons = {
    "愛花": "manaka_icon.png",
    "凛子": "rinko_icon.png",
    "寧々": "nene_icon.png",
}


def existing_avatar(path: str, fallback: str):
    return path if Path(path).is_file() else fallback


ai_icon = existing_avatar(icons[character], "👩")
user_icon = existing_avatar("user_icon.png", "🧑")
history = st.session_state.chat_histories[character]

for message in history:
    avatar = user_icon if message["role"] == "user" else ai_icon
    with st.chat_message(message["role"], avatar=avatar):
        st.write(message["content"])


# =========================================================
# 7. 送信・判定・保存
# =========================================================

if user_msg := st.chat_input(
    f"{character}にメッセージを送る（行動を入れる時はカッコを使う）"
):
    with st.chat_message("user", avatar=user_icon):
        st.write(user_msg)
    history.append({"role": "user", "content": user_msg})

    # 裏ワザはAI任せにせず、プログラム側で確実にON/OFFする。
    command_changed = False
    if "あまあまモードになって" in user_msg:
        state["sweet_mode"] = True
        command_changed = True
    elif "元に戻って" in user_msg:
        state["sweet_mode"] = False
        command_changed = True

    if command_changed:
        try:
            save_game_state(st.session_state.game_state)
        except Exception:
            st.warning("あまあまモードは今回の画面では反映しましたが、永続保存に失敗しました。")

    system_instruction = build_system_instruction(
        character, st.session_state.recent_memory
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
                ),
            )

        raw_response = response.text or ""
        response_text, tags = extract_status_tags(raw_response)

        if not response_text:
            response_text = "（少し考え込んでいる）"

        was_dating = love_number >= 2
        status_changed = command_changed

        if "LOVE_UP" in tags:
            state["love_points"] += 1
            status_changed = True
            st.toast(f"💖 {character}の心に響いたみたい…！")

        # 性格ゲージは、この返信を作った時点ですでに恋人の場合だけ動かす。
        if was_dating and "LEAD_UP" in tags:
            state["lead_gauge"] = min(5, state["lead_gauge"] + 1)
            status_changed = True

        if was_dating and "LEAD_DOWN" in tags:
            state["lead_gauge"] = max(-5, state["lead_gauge"] - 1)
            status_changed = True

        with st.chat_message("assistant", avatar=ai_icon):
            st.write(response_text)
        history.append({"role": "assistant", "content": response_text})

        if status_changed:
            try:
                save_game_state(st.session_state.game_state)
            except Exception:
                st.warning("ステータスは今回の画面では反映しましたが、永続保存に失敗しました。")

        try:
            # 保存完了を確認してから処理を終えるため、バックグラウンドスレッドは使わない。
            log_to_spreadsheet(character, user_msg, response_text)
        except Exception:
            st.warning("返事は表示できましたが、会話ログをGoogle Sheetsへ保存できませんでした。")

        if status_changed:
            st.rerun()

    except Exception as error:
        st.error("Geminiから返事を取得できませんでした。少し待ってから、もう一度送信してください。")
        st.caption(f"エラー種別: {type(error).__name__}")
