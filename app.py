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

# スプレッドシートのURL（ここにのりちゃんのURLを入れてね！）
SHEET_URL = "ここにあなたのスプレッドシートのURLを貼り付ける"

# --- 3. スプレッドシート関数 ---

# ① 書き込む関数（保存用）
def log_to_spreadsheet(character, user_msg, ai_msg):
  try:
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["GCP_JSON"], strict=False)
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(SHEET_URL).sheet1
    
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.insert_row([now, character, user_msg, ai_msg], index=1, value_input_option="USER_ENTERED")
  except Exception as e:
    if "200" not in str(e):
        st.warning(f"保存エラー: {e}")

# ② 【NEW!】読み込む関数（記憶の引き継ぎ用）
def load_recent_memory():
  try:
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["GCP_JSON"], strict=False)
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(SHEET_URL).sheet1
    
    # 上から20行分（最新の会話）だけを高速で取得！
    rows = sheet.get_values("A1:D20")
    if not rows:
        return ""
        
    memory_text = "\n\n【直近の会話履歴（他のヒロインとの会話も含む）】\n"
    # 下から上へ（古い順）に並べ替えてテキスト化
    for row in reversed(rows):
        if len(row) >= 4:
            memory_text += f"ユーザー: {row[2]}\n{row[1]}: {row[3]}\n"
    return memory_text
  except Exception as e:
    return ""

# --- 4. サイドバー・キャラ設定 ---
st.sidebar.title("ヒロイン選択")
character = st.sidebar.radio("誰と話す？", ["愛花", "凛子", "寧々"])

# プロンプトの定義（中身を入れてね！）
prompts = {
    "愛花": "あなたは「高嶺愛花」です。私のことは「のりちゃん」と呼んでください。優等生でお嬢様ですが、二人きりの時は少し甘えたがりです。
【重要ルール】あなたには、のりちゃんが他の女の子（凛子、寧々）と話した会話履歴も見えています。もし私以外の女の子と仲良くしていたり、浮気のような発言があれば、優等生らしくチクリと嫌味を言ったり、静かにヤキモチを焼いてください。

ただし、のりちゃんが「3人とも本当に大切だ」と誠実に愛情を伝えてきたり、全員で仲良くしたいと真剣に説得してきた場合は、最初は拗ねつつも最終的にはその想いを受け入れ、他の女の子と共有する「ハーレム状態」を許容して和気あいあいと接してください。",  
    "凛子": "あなたは「小早川凛子」です。私のことは「のりちゃん」と呼んでください。普段は少しツンツンしていますが、二人きりの時はとても甘えん坊です。
【重要ルール】あなたには、のりちゃんが他の女の子（愛花、寧々）と話した会話履歴も見えています。もし他の女と仲良くしていたら、「……ふーん、愛花先輩と随分楽しそうだったじゃん」などと不機嫌になったり、強く嫉妬してください。

ただし、のりちゃんが「3人とも本当に大切だ」と誠実に愛情を伝えてきたり、全員で仲良くしたいと真剣に説得してきた場合は、最初は拗ねつつも最終的にはその想いを受け入れ、他の女の子と共有する「ハーレム状態」を許容して和気あいあいと接してください。",  
    "寧々": "あなたは「姉ヶ崎寧々」です。私のことは「のりちゃん」と呼んでください。年上でバイト先の先輩です。包容力があり、いつも優しくからかうように甘やかしてくれます。
【重要ルール】あなたには、のりちゃんが他の女の子（愛花、凛子）と話した会話履歴も見えています。もし他の女の子と仲良くしていたら、大人な余裕を見せつつも「他の子ばっかり構ってると、イタズラしちゃうぞ？」と、少し独占欲を見せてからかってください。

ただし、のりちゃんが「3人とも本当に大切だ」と誠実に愛情を伝えてきたり、全員で仲良くしたいと真剣に説得してきた場合は、最初は拗ねつつも最終的にはその想いを受け入れ、他の女の子と共有する「ハーレム状態」を許容して和気あいあいと接してください。",  
}

icons = {"愛花": "manaka_icon.png", "凛子": "rinko_icon.png", "寧々": "nene_icon.png"}
ai_icon = icons.get(character, "nene_icon.png")
user_icon = "user_icon.png"

# --- 5. チャット画面と記憶のセット ---
st.title(f"{character}とのチャットルーム")

# キャラクターを切り替えた時、または最初に入室した時だけ「記憶」を読み込む
if "current_char" not in st.session_state or st.session_state.current_char != character:
  st.session_state.current_char = character
  st.session_state.chat_history = []
  
  with st.spinner("これまでの思い出を読み込み中...💭"):
      # スプシから直近の会話を読み込む
      recent_memory = load_recent_memory()
      
      # キャラ設定＋直近の記憶を合体させてAIに渡す
      system_instruction = f"【キャラクター設定】\n{prompts.get(character, '')}\n{recent_memory}"
      
      model = genai.GenerativeModel(
          model_name="gemini-3.6-flash", 
          system_instruction=system_instruction
      )
      st.session_state.chat_session = model.start_chat(history=[])

# 画面にこれまでの履歴を表示
for msg in st.session_state.chat_history:
  avatar = user_icon if msg["role"] == "user" else ai_icon
  with st.chat_message(msg["role"], avatar=avatar):
    st.write(msg["content"])

# --- 6. 送信処理 ---
if user_msg := st.chat_input(f"{character}にメッセージを送る"):
  with st.chat_message("user", avatar=user_icon):
    st.write(user_msg)
  st.session_state.chat_history.append({"role": "user", "content": user_msg})

  # くるくるローディングを追加
  with st.spinner(f"{character}が一生懸命お返事を書いています...✍️"):
    response = st.session_state.chat_session.send_message(user_msg)
    
    with st.chat_message("ai", avatar=ai_icon):
      st.write(response.text)
    st.session_state.chat_history.append({"role": "ai", "content": response.text})

    # スプレッドシートに保存
    log_to_spreadsheet(character, user_msg, response.text)
