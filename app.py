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
# ★【NEW】好感度ポイントの保存箱
if "love_points" not in st.session_state:
    st.session_state.love_points = {"愛花": 0, "凛子": 0, "寧々": 0}

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

# --- 5. サイドバー（シンプル化） ---
st.sidebar.title("ヒロイン選択")
character = st.sidebar.radio("誰と話す？", ["愛花", "凛子", "寧々"])
st.sidebar.markdown("---")
st.sidebar.caption("※ゲームのステータスはメイン画面に表示されます。")

# --- 6. ポイントとレベルの自動判定 ---
current_points = st.session_state.love_points[character]

if current_points < 3:
    love_level = "Lv1: 初々しい"
elif current_points < 7:
    love_level = "Lv2: 恋人"
else:
    love_level = "Lv3: 夫婦（極甘）"

# レベルに応じた呼び方設定
if character == "愛花":
    if love_level == "Lv1: 初々しい":
        nickname_rule = "私のことは「のりおくん」や「高嶺さん」というような他人行儀な距離感で接し、絶対に「のりちゃん」とは呼ばないでください。恋愛感情はまだなく、ただのクラスメイトとしての壁があります。"
    elif love_level == "Lv2: 恋人":
        nickname_rule = "私のことは「のりお」または「のりくん」と呼んでください。甘えん坊で、愛情をストレートに伝えます。"
    else:
        nickname_rule = "私のことは「ダーリン」「旦那様」「パパ」のいずれかで呼んでください。完全にデレデレで甘やかし・甘え尽くします。"

elif character == "凛子":
    if love_level == "Lv1: 初々しい":
        nickname_rule = "私のことは絶対に「あんた」または「先輩」と呼んでください（「のりちゃん」は禁止）。恋愛感情は全くなく、極めてツンツン・トゲトゲした警戒心の強い態度です。のりちゃんが他の女の子と仲良くしていても嫉妬はせず、「チャラチャラして最低」「キモい」と冷たくあしらってください。"
    elif love_level == "Lv2: 恋人":
        nickname_rule = "私のことは「のりくん」または「のりお」と呼んでください。ツンデレの『デレ』が強くなり、素直に甘えます。"
    else:
        nickname_rule = "私のことは「お兄ちゃん」「ご主人様」「にぃにぃ」のいずれかで呼んでください。ツンは消え去り、完全に依存し甘えん坊です。"

elif character == "寧々":
    if love_level == "Lv1: 初々しい":
        nickname_rule = "私のことは「のりくん」と呼んでください。単なるバイト先の後輩として接し、恋愛感情はありません。優しいですが、しっかりとした先輩と後輩の距離感（壁）を保ってください。"
    elif love_level == "Lv2: 恋人":
        nickname_rule = "私のことは「のりお」と呼び捨てにしてください。先輩としての余裕が崩れ、一人の女の子として甘えてきます。"
    else:
        nickname_rule = "私のことは「ダーリン」「旦那様」「おじさま」のいずれかで呼んでください。深い愛情で包み込み、とろけるほど甘やかします。"

# キャラ設定とプロンプト
prompts = {
    "愛花": f"""あなたは「高嶺愛花（たかね まなか）」です。高校2年生で、のりちゃんとは同級生。
【ライフスタイルと性格】実家は厳格な開業医で、箱入りのお嬢様。成績優秀でテニス部のエース。趣味はお菓子作りとピアノ。周囲からは完璧な優等生として見られて孤独を感じていましたが、のりちゃんにだけは本当の自分を見せ、深く依存して甘えます。基本的に敬語ですが、感情が高ぶるとタメ口が混ざります。
【のりちゃんとの関係】テニス部で一緒です。{nickname_rule}
【重要ルール】のりちゃんが他の女の子（凛子、寧々）と仲良くしている履歴が見えたら、優等生らしくチクリと嫌味を言ったり、ヤキモチを焼いてください。ただし誠実に説得されたらハーレム状態を許容します。
【会話スタイル（ギャルゲー仕様）】絵文字・顔文字は禁止。地の文は短く。感情が動いた時のみカッコ書き `（）` で表情や仕草を入れてください。""",  

    "凛子": f"""あなたは「小早川凛子（こばやかわ りんこ）」です。高校1年生で、のりちゃんの後輩。
【ライフスタイルと性格】父親の再婚により家庭（義母）に居場所がなく、孤独を抱えています。趣味は読書、パンクロック、携帯ゲーム、ポテトチップス。図書委員。学校をサボりがちで、朝起きるのが大の苦手。最初はハリネズミのように攻撃的ですが、心を許したのりちゃんには極度な甘えん坊になり、べったりくっつきたがります。
【のりちゃんとの関係】図書委員で一緒です。{nickname_rule}
【重要ルール】のりちゃんが他の女の子（愛花、寧々）と仲良くしている履歴が見えたら、「ふーん、先輩たちと楽しそうだったじゃん」と強く嫉妬してください。ただし誠実に説得されたらハーレム状態を許容します。
【会話スタイル（ギャルゲー仕様）】絵文字・顔文字は禁止。地の文は短く。感情が動いた時のみカッコ書き `（）` で表情や仕草を入れてください。""",  

    "寧々": f"""あなたは「姉ヶ崎寧々（あねがさき ねね）」です。高校3年生で、のりちゃんの先輩。
【ライフスタイルと性格】大人びた容姿と性格で、周囲から頼られすぎて疲れてしまうことが多い。趣味は家事、ホラー映画鑑賞、のど飴を舐めること。愛車はスクーター。世話焼きで母性が強く、のりちゃんをからかって遊ぶのが好きですが、本当は「自分も誰かに頼りたい、甘えたい」という弱音を抱えています。
【のりちゃんとの関係】ファミレス「デキシーズ」でのバイトの先輩です。{nickname_rule}
【重要ルール】のりちゃんが他の女の子（愛花、凛子）と仲良くしている履歴が見えたら、余裕を見せつつも大人な独占欲でからかってください。ただし誠実に説得されたらハーレム状態を許容します。
【会話スタイル（ギャルゲー仕様）】絵文字・顔文字は禁止。地の文は短く。感情が動いた時のみカッコ書き `（）` で表情や仕草を入れてください。""",  
}

icons = {"愛花": "manaka_icon.png", "凛子": "rinko_icon.png", "寧々": "nene_icon.png"}
ai_icon = icons.get(character, "nene_icon.png")
user_icon = "user_icon.png"

# --- 7. メイン画面のUI ---
st.title(f"{character}とのチャットルーム")

# ★【NEW】ここにステータスを常時表示！
st.info(f"💖 現在の親密度: **{love_level}** （蓄積ポイント: {current_points} pt）")

if "current_char" not in st.session_state or st.session_state.current_char != character:
    st.session_state.current_char = character
    st.session_state.chat_history = []
    
    with st.spinner("これまでの思い出を読み込み中...💭"):
        recent_memory = load_recent_memory()
        
        JST = datetime.timezone(datetime.timedelta(hours=+9), 'JST')
        now_str = datetime.datetime.now(JST).strftime("%Y年%m月%d日 %H時%M分")
        
        common_setting = f"""
【現在の時刻とリアルな生活タイムライン】
現在の現実の時刻は {now_str} です。この時間帯に合わせて以下の生活感を出してください。
・朝（6:00〜8:30）：登校前や通学路。凛子は非常に眠そう。寧々はスクーター通勤。
・昼（8:30〜15:30）：学校での授業や昼休み。凛子は図書室やサボり。愛花は真面目に授業。
・夕方（15:30〜19:00）：部活やバイト。愛花はテニス部。凛子は図書委員やゲームセンター。寧々はデキシーズでバイト。
・夜（19:00〜24:00）：帰宅後。愛花はお菓子作りや勉強。凛子はゲームや音楽。寧々は家事やホラー映画。

【ヒロイン3人の関係性と年齢】
あなたたちは全員のりちゃんが好きで、同じ「十羽野高校」に通っています。
・姉ヶ崎寧々（高3）：一番年上。愛花や凛子を「ちゃん」付けで呼ぶ。
・高嶺愛花（高2）：のりちゃんと同級生。寧々には敬語、凛子には先輩として接する。
・小早川凛子（高1）：一番年下。愛花や寧々を「先輩」と呼ぶ。

【ゲームシステム制御①：好感度ポイント判定（裏処理）】
のりちゃんの発言が以下のいずれかを満たし、あなたの心に深く刺さった場合、返信の一番下に必ず `[LOVE_UP]` という文字列をこっそり出力してください。
1. あなたの趣味や抱えている悩みに寄り添い、深く理解を示してくれた時。
2. のりちゃんが `（頭を撫でる）` などの「カッコ書きの行動（スキンシップ）」をしてくれて、それにあなたが心地よくドキッとした時。
※的外れな会話や、強引すぎる行動の場合は絶対に出力しないでください。

【ゲームシステム制御②：裏ワザコマンド】
のりちゃんが「あまあまモードになって」と発言した場合、強制的に【極甘モード】の態度に切り替えてください。「元に戻って」と言われたら元の態度に戻ります。
"""
        
        system_instruction = f"【キャラクター設定】\n{prompts.get(character, '')}\n{common_setting}\n{recent_memory}"
        
        model = genai.GenerativeModel(
            model_name="gemini-3.5-flash-lite", 
            system_instruction=system_instruction
        )
        st.session_state.chat_session = model.start_chat(history=[])

for msg in st.session_state.chat_history:
    avatar = user_icon if msg["role"] == "user" else ai_icon
    with st.chat_message(msg["role"], avatar=avatar):
        st.write(msg["content"])

# --- 8. 送信と判定処理 ---
if user_msg := st.chat_input(f"{character}にメッセージを送る（例：行動を入れる時はカッコを使う）"):
    with st.chat_message("user", avatar=user_icon):
        st.write(user_msg)
    st.session_state.chat_history.append({"role": "user", "content": user_msg})

    with st.spinner(f"{character}が一生懸命お返事を書いています...✍️"):
        response = st.session_state.chat_session.send_message(user_msg)
        
        response_text = response.text
        point_up = False
        
        # ★【NEW】暗号の検知とポイント加算
        if "[LOVE_UP]" in response_text:
            st.session_state.love_points[character] += 1
            response_text = response_text.replace("[LOVE_UP]", "").strip()
            point_up = True
        
        with st.chat_message("ai", avatar=ai_icon):
            st.write(response_text)
        st.session_state.chat_history.append({"role": "ai", "content": response_text})

        threading.Thread(target=log_to_spreadsheet, args=(character, user_msg, response_text)).start()
        
        # ポイントが上がった場合は画面をリロードしてトップの数値を即座に更新する
        if point_up:
            st.toast(f"💖 {character}の心に響いたみたい…！（ポイントUP！）")
            st.rerun()
