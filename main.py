import os
import random
import pyodbc
import telebot
import replicate  # ← هذا هو المطلوب
from urllib.parse import quote_plus
from telebot import types
from flask import Flask, request, render_template, redirect, url_for
from telebot.apihelper import ApiTelegramException
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

REPLICATE_API_TOKEN = "r8_NMNWJ2UrPYicF9l0ibrzt8rqpCaiiwf472QEd"

# ───────── إعداد الاتصال بقاعدة البيانات ─────────
DB_CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=sql5088.site4now.net;"
    "DATABASE=db_aa4cc6_bot;"
    "UID=db_aa4cc6_bot_admin;"
    "PWD=HSK@id1996"
)
TOKEN = "7898604286:AAG5YnX8OuB3EF4V13E81vXsNnx5pQbER9Y"

bot = telebot.TeleBot(TOKEN)

# ╭───────────────────────╮
# │  وظائف مساعدة للبيانات│
# ╰───────────────────────╯

def connect():
    """Open a fresh autocommit connection."""
    return pyodbc.connect(DB_CONN_STR, autocommit=True)


def fetchall(sql: str, *params):
    with connect() as c:
        cur = c.cursor()
        cur.execute(sql, *params)
        return cur.fetchall()


def execute(sql: str, *params):
    with connect() as c:
        cur = c.cursor()
        cur.execute(sql, *params)

# ========= المشرفون =========

def is_admin(cid: int) -> bool:
    return bool(fetchall("SELECT 1 FROM BotAdmins WHERE ChatId = ?", cid))

# ========= الاشتراك بالقنوات =========

def channels():
    return [r[0] for r in fetchall("SELECT ChannelUsername FROM RequiredChannels")]


def joined_all(cid: int) -> bool:
    for ch in channels():
        try:
            status = bot.get_chat_member(ch, cid).status
            if status not in ("member", "administrator", "creator"):
                return False
        except Exception:
            return False  # القناة خاصّة أو أن البوت ليس مشرفًا
    return True

# ========= المشاريع =========

def all_projects():
    return fetchall("SELECT Id, Name, LanguagesUsed, GitHubUrl FROM Projects")


def add_project(name: str, langs: str, url: str):
    execute("INSERT INTO Projects (Name, LanguagesUsed, GitHubUrl) VALUES (?,?,?)", name, langs, url)


def update_project(pid: int, col: str, val: str):
    execute(f"UPDATE Projects SET {col} = ? WHERE Id = ?", val, pid)


def delete_project(pid: int):
    execute("DELETE FROM Projects WHERE Id = ?", pid)

# ========= روابط التواصل =========

def all_links():
    return fetchall("SELECT Platform, Url FROM SocialLinks")


def add_link(platform: str, url: str):
    execute("INSERT INTO SocialLinks VALUES(?, ?)", platform, url)


def upd_link(platform: str, url: str):
    execute("UPDATE SocialLinks SET Url = ? WHERE Platform = ?", url, platform)


def del_link(platform: str):
    execute("DELETE FROM SocialLinks WHERE Platform = ?", platform)

# ========= قنوات الاشتراك =========

def add_channel(ch: str):
    execute("INSERT INTO RequiredChannels (ChannelUsername) VALUES (?)", ch)


def del_channel(ch: str):
    execute("DELETE FROM RequiredChannels WHERE ChannelUsername = ?", ch)

# ========= المستخدمون =========

def save_user(cid: int):
    execute(
        """
        IF NOT EXISTS (SELECT 1 FROM Users WHERE ChatId = ?)
            INSERT INTO Users (ChatId) VALUES (?)
        """,
        cid,
        cid,
    )


def all_users():
    return [r[0] for r in fetchall("SELECT ChatId FROM Users")]


def count_users() -> int:
    return fetchall("SELECT COUNT(*) FROM Users")[0][0]

# ╭───────────────────────╮
# │       قائمة رئيسية     │
# ╰───────────────────────╯

def build_main_menu(cid: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📂 مشاريع مفتوحة المصدر", callback_data="p_random"),
        InlineKeyboardButton("🧠 صورة من نص (AI)", callback_data="ai_img"),
        InlineKeyboardButton("👨‍💻 مطوّر البوت", callback_data="links")
    )
    if is_admin(cid):
        kb.add(InlineKeyboardButton("🛠️ إدارة البوت", callback_data="admin"))
    return kb


def main_menu_send(cid: int, note="👋 مرحبًا بك!"):
    bot.send_message(cid, note, reply_markup=build_main_menu(cid))


def main_menu_edit(call, note="👋 مرحبًا بك!"):
    bot.edit_message_text(
        note,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=build_main_menu(call.message.chat.id),
    )

# ╭───────────────────────╮
# │        /start         │
# ╰───────────────────────╯

@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    cid = message.chat.id
    if not joined_all(cid):
        kb = InlineKeyboardMarkup()
        for ch in channels():
            kb.add(InlineKeyboardButton(f"📢 اشترك في {ch}", url=f"https://t.me/{ch.lstrip('@')}") )
        kb.add(InlineKeyboardButton("✅ تم الاشتراك", callback_data="chk_sub"))
        bot.send_message(cid, "🚫 اشترك بجميع القنوات ثم اضغط ✅", reply_markup=kb)
        return
    save_user(cid)
    main_menu_send(cid)


@bot.callback_query_handler(func=lambda c: c.data == "chk_sub")
def callback_check_sub(call: types.CallbackQuery):
    if joined_all(call.message.chat.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        main_menu_send(call.message.chat.id, "✅ تم التفعيل!")
    else:
        bot.answer_callback_query(call.id, "❗ اشترك في كل القنوات")

# ╭───────────────────────╮
# │   استعراض المشاريع     │
# ╰───────────────────────╯

session_view: dict[int, set[int]] = {}

@bot.callback_query_handler(func=lambda c: c.data == "p_random")
def callback_random_projects(call: types.CallbackQuery):
    cid = call.message.chat.id
    shown = session_view.get(cid, set())
    pool = [p for p in all_projects() if p[0] not in shown]
    if len(pool) < 2:
        shown = set()
        pool = all_projects()
    pick = random.sample(pool, min(2, len(pool)))
    session_view[cid] = shown.union({p[0] for p in pick})

    text = "".join(
        f"🔹 <b>{name}</b>\n🛠️ <i>{lang}</i>\n🔗 {url}\n\n"
        for _, name, lang, url in pick
    )
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("➡️ التالي", callback_data="p_random"),
        InlineKeyboardButton("🔙 رجوع", callback_data="back"),
    )
    try:
        bot.edit_message_text(
            text,
            chat_id=cid,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=kb,
        )
    except ApiTelegramException as exc:
        if "message is not modified" in str(exc):
            bot.answer_callback_query(call.id, "↻ لا يوجد مشاريع جديدة الآن")
        else:
            raise

# ╭───────────────────────╮
# │     روابط المطوّر      │
# ╰───────────────────────╯

def generate_url(value: str, platform: str) -> str | None:
    value, platform = value.strip(), platform.lower()
    if platform in ("تيليجرام", "telegram") and value.startswith("@"):  # Username
        return f"https://t.me/{value.lstrip('@')}"
    if platform in ("هاتف", "phone") and value.replace("+", "").isdigit():
        return f"tel:{value}"
    if platform in ("انستغرام", "instagram"):
        return f"https://instagram.com/{value}"
    if platform in ("تويتر", "twitter"):
        return f"https://twitter.com/{value}"
    if platform in ("يوتيوب", "youtube"):
        return f"https://youtube.com/{value}"
    if platform in ("تيك توك", "tiktok"):
        return f"https://tiktok.com/@{value}"
    if value.startswith(("http://", "https://", "tg://")):
        return value
    return None


@bot.callback_query_handler(func=lambda c: c.data == "links")
def callback_links(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(row_width=2)
    for platform, raw in all_links():
        url = generate_url(raw, platform)
        if url:
            kb.add(InlineKeyboardButton(platform, url=url))
    kb.add(InlineKeyboardButton("🔙 رجوع", callback_data="back"))
    bot.edit_message_text(
        "🌐 حسابات المطوّر:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=kb,
    )

# ╭───────────────────────╮
# │      لوحة الإدارة      │
# ╰───────────────────────╯

def build_admin_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ إضافة مشروع", callback_data="adm_add_p"),
        InlineKeyboardButton("✏️ تعديل/حذف مشروع", callback_data="adm_mod_p"),
        InlineKeyboardButton("🌐 إدارة الروابط", callback_data="adm_links"),
        InlineKeyboardButton("📢 إدارة القنوات", callback_data="adm_ch"),
        InlineKeyboardButton("📨 رسالة عامّة", callback_data="adm_bcast"),
        InlineKeyboardButton("👥 عدد الأعضاء", callback_data="adm_users_count"),
        InlineKeyboardButton("🔙 رجوع", callback_data="back"),
    )
    return kb


@bot.callback_query_handler(func=lambda c: c.data == "admin")
def callback_admin_panel(call: types.CallbackQuery):
    if not is_admin(call.message.chat.id):
        return
    bot.edit_message_text(
        "🛠️ لوحة الإدارة:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=build_admin_kb(),
    )


@bot.callback_query_handler(func=lambda c: c.data == "adm_users_count")
def callback_users_count(call: types.CallbackQuery):
    bot.answer_callback_query(call.id, f"عدد المستخدمين: {count_users()}", show_alert=True)

# ╭───────────────────────╮
# │ 1️⃣ إضافة مشروع        │
# ╰───────────────────────╯

@bot.callback_query_handler(func=lambda c: c.data == "adm_add_p")
def callback_ask_new_project(call: types.CallbackQuery):
    bot.edit_message_text(
        "أرسل البيانات بهذا الشكل:\n<الاسم> | <اللغات> | <الرابط>",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
    )
    bot.register_next_step_handler(call.message, save_new_project)


def save_new_project(msg: types.Message):
    try:
        name, langs, url = [x.strip() for x in msg.text.split("|", 2)]
        add_project(name, langs, url)
        bot.reply_to(msg, "✅ تمت إضافة المشروع.")
    except Exception:
        bot.reply_to(msg, "⚠️ صيغة غير صحيحة، حاول مجددًا.")
    # رجوع للوحة الإدارة
    callback_admin_panel(
        types.CallbackQuery(id="0", from_user=msg.from_user, message=msg)
    )

# ╭───────────────────────╮
# │ 2️⃣ تعديل/حذف مشروع    │
# ╰───────────────────────╯

def render_projects_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for pid, name, _, _ in all_projects():
        kb.add(
            InlineKeyboardButton(f"✏️ {name}", callback_data=f"edit_p_{pid}"),
            InlineKeyboardButton("🗑️", callback_data=f"del_p_{pid}"),
        )
    kb.add(InlineKeyboardButton("🔙 رجوع", callback_data="admin"))
    return kb


@bot.callback_query_handler(func=lambda c: c.data == "adm_mod_p")
def callback_list_projects(call: types.CallbackQuery):
    bot.edit_message_text(
        "اختر مشروعًا:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=render_projects_kb(),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("del_p_"))
def callback_delete_project(call: types.CallbackQuery):
    delete_project(int(call.data.split("_", 2)[2]))
    bot.answer_callback_query(call.id, "🗑️ تم الحذف")
    callback_list_projects(call)


@bot.callback_query_handler(func=lambda c: c.data.startswith("edit_p_"))
def callback_edit_project_field(call: types.CallbackQuery):
    pid = int(call.data.split("_", 2)[2])
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("اسم", callback_data=f"editp_name_{pid}"),
        InlineKeyboardButton("لغات", callback_data=f"editp_lang_{pid}"),
        InlineKeyboardButton("رابط", callback_data=f"editp_url_{pid}"),
        InlineKeyboardButton("🔙", callback_data="adm_mod_p"),
    )
    bot.edit_message_text(
        "اختر العنصر للتعديل:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("editp_") and len(c.data.split("_")) == 3)
def callback_edit_project_value(call: types.CallbackQuery):
    _, field, pid_str = call.data.split("_")
    pid, fieldmap = int(pid_str), {"name": "Name", "lang": "LanguagesUsed", "url": "GitHubUrl"}
    column = fieldmap[field]
    bot.edit_message_text(
        f"أدخل القيمة الجديدة لـ {column}:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
    )
    bot.register_next_step_handler(call.message, lambda m: update_and_return(m, pid, column))


def update_and_return(msg: types.Message, pid: int, column: str):
    update_project(pid, column, msg.text.strip())
    bot.reply_to(msg, "✅ تم التحديث.")
    callback_list_projects(
        types.CallbackQuery(id="0", from_user=msg.from_user, message=msg)
    )

# ╭───────────────────────╮
# │ 3️⃣ إدارة الروابط      │
# ╰───────────────────────╯

def render_links_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    for platform, _ in all_links():
        kb.add(
            InlineKeyboardButton(f"✏️ {platform}", callback_data=f"edit_l_{platform}"),
            InlineKeyboardButton("🗑️", callback_data=f"del_l_{platform}"),
        )
    kb.add(
        InlineKeyboardButton("➕ إضافة", callback_data="add_l"),
        InlineKeyboardButton("🔙 رجوع", callback_data="admin"),
    )
    return kb


@bot.callback_query_handler(func=lambda c: c.data == "adm_links")
def callback_links_admin(call: types.CallbackQuery):
    bot.edit_message_text(
        "إدارة الروابط:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=render_links_kb(),
    )


@bot.callback_query_handler(func=lambda c: c.data == "add_l")
def callback_ask_new_link(call: types.CallbackQuery):
    bot.edit_message_text(
        "أرسل: <المنصة> | <الرابط>",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
    )
    bot.register_next_step_handler(call.message, save_new_link)


def save_new_link(msg: types.Message):
    try:
        platform, url = [x.strip() for x in msg.text.split("|", 1)]
        add_link(platform, url)
        bot.reply_to(msg, "✅ تمت الإضافة.")
    except Exception:
        bot.reply_to(msg, "⚠️ صيغة غير صحيحة.")
    callback_links_admin(
        types.CallbackQuery(id="0", from_user=msg.from_user, message=msg)
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("edit_l_"))
def callback_ask_edit_link(call: types.CallbackQuery):
    platform = call.data.split("_", 2)[2]
    bot.edit_message_text(
        f"أدخل الرابط الجديد لـ {platform}:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
    )
    bot.register_next_step_handler(call.message, lambda m: update_link(m, platform))


def update_link(msg: types.Message, platform: str):
    upd_link(platform, msg.text.strip())
    bot.reply_to(msg, "✅ تم التحديث.")
    callback_links_admin(
        types.CallbackQuery(id="0", from_user=msg.from_user, message=msg)
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("del_l_"))
def callback_delete_link(call: types.CallbackQuery):
    platform = call.data.split("_", 2)[2]
    del_link(platform)
    bot.answer_callback_query(call.id, "🗑️ تم الحذف")
    callback_links_admin(call)

# ╭───────────────────────╮
# │ 4️⃣ إدارة القنوات      │
# ╰───────────────────────╯

def render_channels_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for ch in channels():
        kb.add(InlineKeyboardButton(f"🗑️ {ch}", callback_data=f"del_ch_{ch}"))
    kb.add(
        InlineKeyboardButton("➕ إضافة قناة", callback_data="add_ch"),
        InlineKeyboardButton("🔙 رجوع", callback_data="admin"),
    )
    return kb


@bot.callback_query_handler(func=lambda c: c.data == "adm_ch")
def callback_channels_admin(call: types.CallbackQuery):
    bot.edit_message_text(
        "إدارة القنوات:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=render_channels_kb(),
    )


@bot.callback_query_handler(func=lambda c: c.data == "add_ch")
def callback_ask_add_channel(call: types.CallbackQuery):
    bot.edit_message_text(
        "أرسل اسم القناة هكذا: @my_channel",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
    )
    bot.register_next_step_handler(call.message, save_ch)


def save_ch(msg: types.Message):
    add_channel(msg.text.strip())
    bot.reply_to(msg, "✅ تم إضافة القناة.")
    callback_channels_admin(types.CallbackQuery(id="0", from_user=msg.from_user, message=msg))


@bot.callback_query_handler(func=lambda c: c.data.startswith("del_ch_"))
def callback_del_ch(call: types.CallbackQuery):
    ch = call.data.split("_", 2)[2]
    del_channel(ch)
    bot.answer_callback_query(call.id, "🗑️ حُذفت القناة")
    callback_channels_admin(call)

# ╭───────────────────────╮
# │ 5️⃣ إذاعة رسالة عامة   │
# ╰───────────────────────╯

@bot.callback_query_handler(func=lambda c: c.data == "adm_bcast")
def callback_ask_bcast(call: types.CallbackQuery):
    bot.edit_message_text(
        "📝 أرسل الرسالة ليتم بثّها للجميع:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
    )
    bot.register_next_step_handler(call.message, do_bcast)


def do_bcast(msg: types.Message):
    text, n = msg.text, 0
    for uid in all_users():
        try:
            bot.send_message(uid, text)
            n += 1
        except Exception:
            pass
    bot.reply_to(msg, f"✅ أُرسلت الرسالة إلى {n} مستخدم.")
    callback_admin_panel(types.CallbackQuery(id="0", from_user=msg.from_user, message=msg))

# ╭───────────────────────╮
# │         رجوع          │
# ╰───────────────────────╯

@bot.callback_query_handler(func=lambda c: c.data == "back")
def callback_back(call: types.CallbackQuery):
    main_menu_edit(call, "🔙 رجوع للقائمة الرئيسية.")

# ─────────────────────── تشغيل البوت ───────────────────────

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "Bot is alive!", 200

@app.route("/", methods=["POST"])
def webhook():
    update = request.get_json()
    if update:
        bot.process_new_updates([telebot.types.Update.de_json(update)])
    return "OK", 200

@bot.callback_query_handler(func=lambda c: c.data == "ai_img")
def ask_prompt(call):
    bot.edit_message_text(
        "📝 أرسل وصفًا دقيقًا للصورة التي تريد إنشاؤها بالذكاء الاصطناعي:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    bot.register_next_step_handler(call.message, generate_ai_image)


def generate_ai_image(msg):
    prompt = msg.text.strip()
    cid = msg.chat.id
    bot.send_chat_action(cid, "upload_photo")  # يُظهر جاري التحميل

    try:
        output = replicate.run(
            "stability-ai/sdxl:9fa26e1f129b4c3d4b2c1f543b7c3b204631cdd29935d5194031e6e7c61c6a3d",
            input={"prompt": prompt}
        )
        image_url = output[0] if isinstance(output, list) else output
        bot.send_photo(cid, image_url, caption="🧠 تم إنشاء الصورة باستخدام الذكاء الاصطناعي")
    except Exception as e:
        bot.reply_to(msg, f"❌ حدث خطأ أثناء توليد الصورة:\n{e}")


if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url="https://telegram-bot-gs90.onrender.com/")  # عدله إلى رابط Fly الخاص بك
    app.run(host="0.0.0.0", port=8080)
