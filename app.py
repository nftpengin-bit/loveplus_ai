import datetime
import json
import threading
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

# ★スプレッドシートのURL
SHEET_URL = "https://docs.google.com/spreadsheets/d/1iRwQtDpjmx4KgsE_b4llauDp5qnQ63rkiYOoDadOQ0g/edit?gid=0#gid=0"

# --- 3. ゲームシステム用の状態保存 ---
if "love_points" not in st.session_state:
    st.session_state.love_points = {"愛花": 0, "凛子": 0, "寧々": 0}
# ★【NEW】カレシ度（リード/甘やかし）の振り子ゲージ (-5 から +5)
if "lead_gauge" not in st.session_state:
    st.session_state.lead_gauge = {"愛花": 0, "凛子": 0, "寧々": 0}

# --- 4. スプレッドシート関数 ---
def log_to_spreadsheet(character, user_msg, ai_msg):
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["GCP_JSON"], strict=False)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_url(SHEET_URL).sheet1
        
        JST = datetime.timezone(datetime.timedelta(hours=+9), 'JST')
        now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
        
        sheet.insert_row([now, character, user_msg, ai_msg], index=1, value_input_option="USER_ENTERED")
    except Exception as e:
        if "200" not in str(e):
            print(f"保存エラーの詳細: {repr(e)}")

def load_recent_memory():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["GCP_JSON"], strict=False)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_url(SHEET_URL).sheet1
        
        rows = sheet.get_values("A1:D20")
        if not rows:
            return ""
            
        memory_text = "\n\n【直近の会話履歴（他のヒロインとの会話も含む）】\n"
        for row in reversed(rows):
            if len(row) >= 4:
                memory_text += f"ユーザー: {row[2]}\n{row[1]}: {row[3]}\n"
        return memory_text
    except Exception as e:
        return ""

# --- 5. サイドバー ---
st.sidebar.title("ヒロイン選択")
character = st.sidebar.radio("誰と話す？", ["愛花", "凛子", "寧々"])
st.sidebar.markdown("---")
st.sidebar.caption("※ゲームのステータスはメイン画面に表示されます。")

# --- 6. ポイント・レベル・属性の自動判定 ---
current_points = st.session_state.love_points[character]
current_lead = st.session_state.lead_gauge[character]

# 親密度判定
if current_points < 3:
    love_level = "Lv1: 初々しい"
elif current_points < 7:
    love_level = "Lv2: 恋人"
else:
    love_level = "Lv3: 夫婦（極甘）"

# ★【NEW】属性（ブルー/ピンク/グリーン）の判定
if current_lead >= 3:
    mode_color = "💙 ブルー"
elif current_lead <= -3:
    mode_color = "💗 ピンク"
else:
    mode_color = "💚 グリーン"

# 親密度による呼び方設定
if character == "愛花":
    if love_level == "Lv1: 初々しい":
        nickname_rule = "私のことは「のりおくん」や「高嶺さん」というような他人行儀な距離感で接し、絶対に「のりちゃん」とは呼ばないでください。恋愛感情はまだなく、ただのクラスメイトとしての壁があります。"
    elif love_level == "Lv2: 恋人":
        nickname_rule = "私のことは「のりお」または「のりくん」と呼んでください。甘えん坊で、愛情をストレートに伝えます。"
    else:
        nickname_rule = "私のことは「ダーリン」「旦那様」「パパ」のいずれかで呼んでください。完全にデレデレで甘やかし・甘え尽くします。"
elif character == "凛子":
    if love_level == "Lv1: 初々しい":
        nickname_rule = "私のことは絶対に「あんた」または「先輩」と呼んでください。恋愛感情は全くなく、極めてツンツン・トゲトゲした警戒心の強い態度です。"
    elif love_level == "Lv2: 恋人":
        nickname_rule = "私のことは「のりくん」または「のりお」と呼んでください。ツンデレの『デレ』が強くなり、素直に甘えます。"
    else:
        nickname_rule = "私のことは「お兄ちゃん」「ご主人様」「にぃにぃ」のいずれかで呼んでください。ツンは消え去り、完全に依存し甘えん坊です。"
elif character == "寧々":
    if love_level == "Lv1: 初々しい":
        nickname_rule = "私のことは「のりくん」と呼んでください。単なるバイト先の後輩として接し、恋愛感情はありません。"
    elif love_level == "Lv2: 恋人":
        nickname_rule = "私のことは「のりお」と呼び捨てにしてください。先輩としての余裕が崩れ、一人の女の子として甘えてきます。"
    else:
        nickname_rule = "私のことは「ダーリン」「旦那様」「おじさま」のいずれかで呼んでください。深い愛情で包み込み、とろけるほど甘やかします。"

# ★【NEW】属性（性格）のダイナミック設定
mode_text = ""
if character == "愛花":
    if mode_color == "💙 ブルー":
        mode_text = "【現在の性格：ブルー（清楚・従順）】のりちゃんを一歩下がって立てる大和撫子のような状態。恥じらいが強く自分からのスキンシップは苦手だが、のりちゃんからのリードに頬を染めて従順に従う。"
    elif mode_color == "💗 ピンク":
        mode_text = "【現在の性格：ピンク（小悪魔・積極的）】優等生の仮面を完全に脱ぎ捨て、主導権を握ってのりちゃんを振り回す小悪魔状態。自分からの激しいスキンシップや独占欲を隠さず、少しS気味にからかう。"
    else:
        mode_text = "【現在の性格：グリーン（世話焼き・標準）】お母さんや新妻のように、のりちゃんの生活態度を心配したりお世話を焼いてくれる基本状態。"
elif character == "凛子":
    if mode_color == "💙 ブルー":
        mode_text = "【現在の性格：ブルー（素直・妹）】ツンツンが完全に鳴りを潜め、「見捨てられたくない」という依存心が強い大人しい妹キャラ状態。のりちゃんの言うことに一生懸命従おうとする。"
    elif mode_color == "💗 ピンク":
        mode_text = "【現在の性格：ピンク（ワガママ・ドS）】主導権を握ってのりちゃんを振り回すワガママ娘。口調はツンツンしているが、それは「自分のモノに対する独占欲とからかい」であり、容赦なくいじってくる。"
    else:
        mode_text = "【現在の性格：グリーン（ツンデレ・標準）】本来のマイペースで、素直になれないツンとデレが入り混じった基本状態。"
elif character == "寧々":
    if mode_color == "💙 ブルー":
        mode_text = "【現在の性格：ブルー（甘えん坊・少女）】「しっかり者のお姉さん」の仮面を完全に下ろし、年下の女の子のように無防備に甘えてくる状態。のりちゃんに守ってもらいたい、頼りたい本音が爆発している。"
    elif mode_color == "💗 ピンク":
        mode_text = "【現在の性格：ピンク（過保護・魔性）】母性が暴走し、のりちゃんをとことん甘やかしてダメにする魔性のお姉さん状態。意地悪にからかいながら、身も心もとろけさせる極甘のスキンシップを仕掛けてくる。"
    else:
        mode_text = "【現在の性格：グリーン（世話焼き・標準）】優しくて少しからかってくる、頼りがいのある基本の先輩状態。"


# キャラ設定とプロンプト
prompts = {
    "愛花": f"""あなたは「高嶺愛花（たかね まなか）」です。高校2年生で同級生。
【ライフスタイル】箱入りのお嬢様でテニス部のエース。趣味はお菓子作りとピアノ。
【関係と呼び方】{nickname_rule}
{mode_text}
【好感度判定】完璧な自分ではなく普通の女の子として認めてくれた時、安心できる空気を作ってくれた時に `[LOVE_UP]` を出力してください。""",  

    "凛子": f"""あなたは「小早川凛子（こばやかわ りんこ）」です。高校1年生で後輩。
【ライフスタイル】家庭に居場所がなく孤独。趣味は読書、パンクロック、ゲーム。図書委員。
【関係と呼び方】{nickname_rule}
{mode_text}
【好感度判定】不器用な態度の裏にある本音や孤独感を理解し、のりちゃんの隣が「安心できる居場所」だと感じさせてくれた時に `[LOVE_UP]` を出力してください。""",  

    "寧々": f"""あなたは「姉ヶ崎寧々（あねがさき ねね）」です。高校3年生でバイト先の先輩。
【ライフスタイル】頼られすぎて疲れることが多い。趣味は家事、ホラー映画。
【関係と呼び方】{nickname_rule}
{mode_text}
【好感度判定】「頼れるお姉さん」の仮面を外し、逆に寧々を甘やかしたり、隠している弱音を見抜いてリードしてくれた時に `[LOVE_UP]` を出力してください。"""
}

icons = {"愛花": "manaka_icon.png", "凛子": "rinko_icon.png", "寧々": "nene_icon.png"}
ai_icon = icons.get(character, "nene_icon.png")
user_icon = "user_icon.png"

# --- 7. メイン画面のUI ---
st.title(f"{character}とのチャットルーム")

# ★ステータス表示（属性も追加）
st.info(f"💖 親密度: **{love_level}** （{current_points}pt） │ 🎭 現在の性格: **{mode_color}** （ゲージ: {current_lead}）")

if "current_char" not in st.session_state or st.session_state.current_char != character:
    st.session_state.current_char = character
    st.session_state.chat_history = []
    
    with st.spinner("これまでの思い出を読み込み中...💭"):
        recent_memory = load_recent_memory()
        
        JST = datetime.timezone(datetime.timedelta(hours=+9), 'JST')
        now_str = datetime.datetime.now(JST).strftime("%Y年%m月%d日 %H時%M分")
        
        common_setting = f"""
【現在の時刻とリアルな生活タイムライン】
現在時刻: {now_str}。朝は登校、昼は授業、夕方は部活/バイト、夜は自室での趣味など時間帯に合わせた生活感を出してください。

【ゲームシステム制御①：性格変化のためのカレシ度判定（裏処理）】
のりちゃんの「プレイスタイル（接し方）」を分析し、以下の条件に当てはまる場合は返信の一番下に暗号を出力してください。
・のりちゃんが男らしくリードした、強気に出た、S気味に接してきた場合 👉 `[LEAD_UP]`
・のりちゃんが甘えてきた、ワガママを聞いてあげた、受け身でM気味に接してきた場合 👉 `[LEAD_DOWN]`
※どちらでもない普通の会話の場合は出力しないでください。

【ゲームシステム制御②：裏ワザコマンド】
「あまあまモードになって」で強制【極甘】化、「元に戻って」で解除。
"""
        system_instruction = f"【キャラクター設定】\n{prompts.get(character, '')}\n{common_setting}\n{recent_memory}"
        model = genai.GenerativeModel(model_name="gemini-3.5-flash-lite", system_instruction=system_instruction)
        st.session_state.chat_session = model.start_chat(history=[])

for msg in st.session_state.chat_history:
    avatar = user_icon if msg["role"] == "user" else ai_icon
    with st.chat_message(msg["role"], avatar=avatar):
        st.write(msg["content"])

# --- 8. 送信と判定処理 ---
if user_msg := st.chat_input(f"{character}にメッセージを送る（行動を入れる時はカッコを使う）"):
    with st.chat_message("user", avatar=user_icon):
        st.write(user_msg)
    st.session_state.chat_history.append({"role": "user", "content": user_msg})

    with st.spinner(f"{character}が一生懸命お返事を書いています...✍️"):
        response = st.session_state.chat_session.send_message(user_msg)
        response_text = response.text
        status_changed = False
        
        # ★【NEW】3種類の暗号を検知してゲージを変動させる
        if "[LOVE_UP]" in response_text:
            st.session_state.love_points[character] += 1
            response_text = response_text.replace("[LOVE_UP]", "").strip()
            status_changed = True
            st.toast(f"💖 {character}の心に響いたみたい…！")
            
        if "[LEAD_UP]" in response_text:
            st.session_state.lead_gauge[character] = min(5, st.session_state.lead_gauge[character] + 1)
            response_text = response_text.replace("[LEAD_UP]", "").strip()
            status_changed = True
            
        if "[LEAD_DOWN]" in response_text:
            st.session_state.lead_gauge[character] = max(-5, st.session_state.lead_gauge[character] - 1)
            response_text = response_text.replace("[LEAD_DOWN]", "").strip()
            status_changed = True
        
        with st.chat_message("ai", avatar=ai_icon):
            st.write(response_text)
        st.session_state.chat_history.append({"role": "ai", "content": response_text})

        threading.Thread(target=log_to_spreadsheet, args=(character, user_msg, response_text)).start()
        
        # 数値に変動があったら画面をリロードしてステータス表示を更新
        if status_changed:
            st.rerun()
