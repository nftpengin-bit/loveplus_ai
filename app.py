import datetime
import json
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
import streamlit as st

# --- 1. パスワード設定 ---
SECRET_PASSWORD = "nori"

if "authenticated" not in st.session_state:
  st.session_state.authenticated = False

if not st.session_state.authenticated:
  st.title("🔒 秘密の部屋")
  pwd = st.text_input("パスワードを入力してください", type="password")
  if st.button("ログイン"):
    if pwd == SECRET_PASSWORD:
      st.session_state.authenticated = True
      st.rerun()
    else:
      st.error("パスワードが違います！")
  st.stop()

# --- 2. メインアプリの準備 ---
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])


# --- スプレッドシート保存関数（ここが修正ポイント！） ---
def log_to_spreadsheet(character, user_msg, ai_msg):
  try:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    # Secretsの「GCP_JSON」からテキストを読み込んで正しくJSONに変換する
    creds_dict = json.loads(st.secrets["GCP_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open("AI会話ログ").sheet1
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([now, character, user_msg, ai_msg])
  except Exception as e:
    st.warning(f"スプレッドシート保存エラー: {e}")


# --- 3. サイドバー・キャラ設定 ---
st.sidebar.title("ヒロイン選択")
character = st.sidebar.radio("誰と話す？", ["愛花", "凛子", "寧々"])

# プロンプトの定義
prompts = {
    "愛花": "あなたは愛花です...",  # ここに元々の愛花のプロンプトを入れる
    "凛子": "あなたは凛子です...",  # ここに元々の凛子のプロンプトを入れる
    "寧々": "あなたは寧々です...",  # ここに元々の寧々のプロンプトを入れる
}

# アイコン設定
icons = {
    "愛花": "manaka_icon.png",
    "凛子": "rinko_icon.png",
    "寧々": "nene_icon.png",
}
ai_icon = icons.get(character, "nene_icon.png")
user_icon = "user_icon.png"

# システムプロンプト
system_instruction = f"【キャラクター設定】\n{prompts.get(character, '')}"

model = genai.GenerativeModel(
    model_name="gemini-3.6-flash", system_instruction=system_instruction
)

# --- 4. チャット画面 ---
st.title(f"{character}とのチャットルーム")

if (
    "current_char" not in st.session_state
    or st.session_state.current_char != character
):
  st.session_state.current_char = character
  st.session_state.chat_history = []
  st.session_state.chat_session = model.start_chat(history=[])

for msg in st.session_state.chat_history:
  avatar = user_icon if msg["role"] == "user" else ai_icon
  with st.chat_message(msg["role"], avatar=avatar):
    st.write(msg["content"])

# --- 5. 送信処理 ---
if user_msg := st.chat_input(f"{character}にメッセージを送る"):
  with st.chat_message("user", avatar=user_icon):
    st.write(user_msg)
  st.session_state.chat_history.append({"role": "user", "content": user_msg})

  response = st.session_state.chat_session.send_message(user_msg)

  with st.chat_message("ai", avatar=ai_icon):
    st.write(response.text)
  st.session_state.chat_history.append({"role": "ai", "content": response.text})

  # スプレッドシートに保存！
  log_to_spreadsheet(character, user_msg, response.text)
