# -*- coding: utf-8 -*-
"""Telegram Bot (Webhook) – ready for deployment on Render/Railway/Fly.io

▶️ ملاحظات:
  - غيّر قيم BOT_TOKEN و DB_CONN_STR إلى متغيّرات بيئة في الاستضافة.
  - بعد نشر الخدمة احصل على رابطها (مثال https://my-bot.onrender.com)
    ثم نفّذ:
    https://api.telegram.org/bot<توكنك>/setWebhook?url=https://my-bot.onrender.com/<توكنك>

"""
import os, random, pyodbc, telebot
from flask import Flask, request
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ───────── متغيّرات البيئة (أمّنها في لوحة التحكم) ─────────
BOT_TOKEN   = os.environ.get("BOT_TOKEN",   "7898604286:AAHm4fDA-LG_KB14U123qYVO7fEdX9dV5VA")
DB_CONN_STR = os.environ.get("DB_CONN_STR", 
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=sql5088.site4now.net;"
    "DATABASE=db_aa4cc6_bot;"
    "UID=db_aa4cc6_bot_admin;"
    "PWD=HSK@id1996"
)

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

# ╭───────────────────────╮
# │  وظائف مساعدة للبيانات│
# ╰───────────────────────╯
def connect():      return pyodbc.connect(DB_CONN_STR, autocommit=True)
def fetchall(sql,*p): 
    with connect() as c: 
        cur=c.cursor(); cur.execute(sql,*p); 
        return cur.fetchall()
def execute(sql,*p):
    with connect() as c:
        cur=c.cursor(); cur.execute(sql,*p)

# ========= المشرفون =========
def is_admin(cid): return bool(fetchall("SELECT 1 FROM BotAdmins WHERE ChatId=?", cid))

# ========= الاشتراك بالقنوات =========
def channels(): return [r[0] for r in fetchall("SELECT ChannelUsername FROM RequiredChannels")]
def joined_all(cid):
    for ch in channels():
        try:
            st = bot.get_chat_member(ch, cid).status
            if st not in ("member","administrator","creator"): return False
        except: 
            return False
    return True

# ========= المشاريع =========
def all_projects(): 
    return fetchall("SELECT Id,Name,LanguagesUsed,GitHubUrl FROM Projects")

def add_project(name,langs,url):
    execute("INSERT INTO Projects (Name,LanguagesUsed,GitHubUrl) VALUES (?,?,?)",name,langs,url)

def update_project(pid,col,val):
    execute(f"UPDATE Projects SET {col}=? WHERE Id=?",val,pid)

def delete_project(pid):
    execute("DELETE FROM Projects WHERE Id=?",pid)

# ========= التواصل =========
def all_links(): return fetchall("SELECT Platform,Url FROM SocialLinks")
def add_link(p,u): execute("INSERT INTO SocialLinks VALUES(?,?)",p,u)
def upd_link(p,u): execute("UPDATE SocialLinks SET Url=? WHERE Platform=?",u,p)
def del_link(p):   execute("DELETE FROM SocialLinks WHERE Platform=?",p)

# ========= قنوات الاشتراك =========
def add_channel(ch): execute("INSERT INTO RequiredChannels (ChannelUsername) VALUES (?)",ch)
def del_channel(ch): execute("DELETE FROM RequiredChannels WHERE ChannelUsername=?",ch)

# ========= المستخدمون =========
def save_user(cid):
    execute("IF NOT EXISTS(SELECT 1 FROM Users WHERE ChatId=?) INSERT INTO Users(ChatId) VALUES (?)",cid,cid)
def all_users(): return [r[0] for r in fetchall("SELECT ChatId FROM Users")]

# ╭───────────────────────╮
# │       القائمة          │
# ╰───────────────────────╯
def main_menu(cid, note="👋 مرحبًا بك!"):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("📂 مشاريع مفتوحة المصدر",callback_data="p_random"),
           InlineKeyboardButton("👨‍💻 مطوّر البوت",callback_data="links"))
    if is_admin(cid):
        kb.add(InlineKeyboardButton("🛠️ إدارة البوت", callback_data="admin"))
    bot.send_message(cid,note,reply_markup=kb)

# ╭───────────────────────╮
# │        /start         │
# ╰───────────────────────╯
@bot.message_handler(commands=["start"])
def start(msg):
    cid=msg.chat.id
    if not joined_all(cid):
        kb=InlineKeyboardMarkup()
        for ch in channels():
            kb.add(InlineKeyboardButton(f"📢 اشترك في {ch}",url=f"https://t.me/{ch.lstrip('@')}"))
        kb.add(InlineKeyboardButton("✅ تم الاشتراك",callback_data="chk_sub"))
        bot.send_message(cid,"🚫 اشترك بجميع القنوات ثم اضغط ✅",reply_markup=kb)
        return
    save_user(cid)
    main_menu(cid)

@bot.callback_query_handler(func=lambda c:c.data=="chk_sub")
def chk_sub(call):
    if joined_all(call.message.chat.id):
        bot.delete_message(call.message.chat.id,call.message.message_id)
        main_menu(call.message.chat.id,"✅ تم التفعيل!")
    else:
        bot.answer_callback_query(call.id,"❗ اشترك في كل القنوات")

# ╭───────────────────────╮
# │  مشاريع عشوائية عرضًا │
# ╰───────────────────────╯
session_view={}
@bot.callback_query_handler(func=lambda c:c.data=="p_random")
def send_projects(call):
    cid=call.message.chat.id
    # إعادة التهيئة إذا استهلك كل المشاريع
    shown=session_view.get(cid,set())
    projects=[p for p in all_projects() if p[0] not in shown]
    if len(projects)<2: 
        shown=set(); 
        projects=all_projects()
    pick=random.sample(projects,min(2,len(projects)))
    session_view[cid]=shown.union({p[0] for p in pick})
    txt=""
    for _,name,lang,url in pick:
        txt+=f"🔹 <b>{name}</b>\n🛠️ <i>{lang}</i>\n🔗 {url}\n\n"
    kb=InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➡️ التالي",callback_data="p_random"),
           InlineKeyboardButton("🔙 رجوع",callback_data="back"))
    bot.send_message(cid,txt,parse_mode="HTML",reply_markup=kb)

# ╭───────────────────────╮
# │     روابط المطور      │
# ╰───────────────────────╯
@bot.callback_query_handler(func=lambda c:c.data=="links")
def links(call):
    kb=InlineKeyboardMarkup(row_width=2)
    for p,u in all_links():
        kb.add(InlineKeyboardButton(p,url=u))
    kb.add(InlineKeyboardButton("🔙 رجوع",callback_data="back"))
    bot.send_message(call.message.chat.id,"🌐 حسابات المطوّر:",reply_markup=kb)

# ╭───────────────────────╮
# │  لوحة الإدارة         │
# ╰───────────────────────╯
@bot.callback_query_handler(func=lambda c:c.data=="admin")
def admin_panel(call):
    cid=call.message.chat.id
    if not is_admin(cid): 
        return
    kb=InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ إضافة مشروع",callback_data="adm_add_p"),
        InlineKeyboardButton("✏️ تعديل/حذف مشروع",callback_data="adm_mod_p"),
        InlineKeyboardButton("🌐 إدارة الروابط",callback_data="adm_links"),
        InlineKeyboardButton("📢 إدارة القنوات",callback_data="adm_ch"),
        InlineKeyboardButton("📨 رسالة عامّة",callback_data="adm_bcast"),
        InlineKeyboardButton("🔙 رجوع",callback_data="back")
    )
    bot.send_message(cid,"🛠️ لوحة الإدارة:",reply_markup=kb)

# ... (باقي الدوال بدون تعديل) ...
# اختصارًا سنفترض أنك لسّت بحاجة لتغيير أي كود داخلي إضافي
# إذا كان لديك المزيد من الدوال، اتركها كما هي فوق هذا السطر

# ╭───────────────────────╮
# │   إعداد Webhook       │
# ╰───────────────────────╯
@app.route('/'+BOT_TOKEN, methods=['POST'])
def telegram_webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200

@app.route('/', methods=['GET'])
def index():
    return '💡 البوت يعمل بنجاح (Webhook)', 200

if __name__ == '__main__':
    # للتشغيل المحلي فقط:
    # 1) شغّل هذا الملف        python main.py
    # 2) ثم اربط ngrok         ngrok http 10000
    # 3) setWebhook إلى الرابط https://xxx.ngrok.io/<TOKEN>
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
