import datetime
import os
import google.generativeai as genai
import json
import gspread
from google.oauth2.service_account import Credentials
import streamlit as st

# --- 1. パスワード設定（ここで合言葉を決めます） ---
SECRET_PASSWORD = "nori"  # ← 好きなパスワードに変更可能です

if "authenticated" not in st.session_state:
  st.session_state.authenticated = False

# ログイン画面
if not st.session_state.authenticated:
  st.title("🔒 秘密の部屋")
  pwd = st.text_input("パスワードを入力してください", type="password")
  if st.button("ログイン"):
    if pwd == SECRET_PASSWORD:
      st.session_state.authenticated = True
      st.rerun()
    else:
      st.error("パスワードが違います！")
  st.stop()  # パスワードが合うまでここから下は実行されません

# --- 2. メインアプリの準備 ---
# Streamlit Secretsから安全にAPIキーを読み込むように修正
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])


def load_text(filename):
  if os.path.exists(filename):
    with open(filename, "r", encoding="utf-8") as f:
      return f.read()
  return ""


def append_history(filename, text):
  with open(filename, "a", encoding="utf-8") as f:
    f.write(text + "\n")


# --- ★ Googleスプレッドシートにログを保存する関数を追加 ---
def log_to_spreadsheet(character, user_msg, ai_msg):
  try:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = json.loads(st.secrets["GCP_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)

    # 「AI会話ログ」という名前のスプレッドシートの1枚目のシートを開く
    sheet = client.open("AI会話ログ").sheet1

    # 日時、キャラクター名、ユーザーの発言、AIの返答を追加
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([now, character, user_msg, ai_msg])
  except Exception as e:
    st.warning(f"スプレッドシート保存エラー: {e}")


shared_history_file = "shared_history.txt"

# --- 3. サイドバー（キャラ選択） ---
st.sidebar.title("ヒロイン選択")
character = st.sidebar.radio("誰と話す？", ["愛花", "凛子", "寧々"])

if character == "愛花":
  file_prefix = "manaka"
  ai_icon = "manaka_icon.png"  # 拡張子がjpgの場合は書き換えてください
elif character == "凛子":
  file_prefix = "rinko"
  ai_icon = "rinko_icon.png"
else:
  file_prefix = "nene"
  ai_icon = "nene_icon.png"

user_icon = "user_icon.png"

# 設定と共有記憶の読み込み
prompt_file = f"{file_prefix}_prompt.txt"
prompt = load_text(prompt_file)
history = load_text(shared_history_file)

# 時間の連動
now = datetime.datetime.now()
current_time_str = now.strftime("%Y年%m月%d日 %H時%M分")
system_instruction = f"【現在時刻】\n今は {current_time_str} です。\n\n【キャラクター設定】\n{prompt}\n\n【これまでの全会話履歴】\n{history}"

model = genai.GenerativeModel(
    model_name="gemini-3.6-flash", system_instruction=system_instruction
)

# --- 4. チャット画面の構築 ---
st.title(f"{character}とのチャットルーム")

# キャラクターを切り替えた時に画面をリセットする処理
if (
    "current_char" not in st.session_state
    or st.session_state.current_char != character
):
  st.session_state.current_char = character
  st.session_state.chat_history = []  # 画面の履歴をクリア
  st.session_state.chat_session = model.start_chat()

# 画面上にこれまでの会話ログ（アイコン付き）を表示
for msg in st.session_state.chat_history:
  if msg["role"] == "user":
    with st.chat_message("user", avatar=user_icon):
      st.write(msg["content"])
  else:
    with st.chat_message("ai", avatar=ai_icon):
      st.write(msg["content"])

# --- 5. メッセージ送信処理 ---
if user_msg := st.chat_input(f"{character}にメッセージを送る"):
  # のりちゃんの入力を画面に表示
  with st.chat_message("user", avatar=user_icon):
    st.write(user_msg)
  st.session_state.chat_history.append({"role": "user", "content": user_msg})

  # AIの返答を取得して画面に表示
  response = st.session_state.chat_session.send_message(user_msg)
  with st.chat_message("ai", avatar=ai_icon):
    st.write(response.text)
  st.session_state.chat_history.append({"role": "ai", "content": response.text})

  # 従来のローカルファイル保存
  log_text = f"[{character}との会話] のりちゃん: {user_msg}\n{character}: {response.text}"
  append_history(shared_history_file, log_text)

  # ★ Googleスプレッドシートへも自動保存！
  log_to_spreadsheet(character, user_msg, response.text)
