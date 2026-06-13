import logging
import random
import json
import os
import time
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

# ==================== تنظیمات ====================
BOT_TOKEN = "8109899106:AAEfYzpVUq6S6Fbs_7BRMgbIN0JN0rqeiic"
ADMIN_IDS = [7837042019]  # ← آیدی عددی تلگرامت رو اینجا بذار
DATA_FILE = "users_data.json"
START_COINS = 1000
MAX_MINER_LEVEL = 1000

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== ابزارها ====================
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(user_id: str, data: dict) -> dict:
    if user_id not in data:
        data[user_id] = {
            "coins": 0,
            "registered": False,
            "miner_level": 0,
            "miner_last_claim": 0,
            "max_coins": 0,
            "wheel_last_spin": 0,
            "username": ""
        }
    u = data[user_id]
    for key, default in [
        ("miner_level", 0), ("miner_last_claim", 0),
        ("max_coins", 0), ("wheel_last_spin", 0), ("username", "")
    ]:
        if key not in u:
            u[key] = default
    if u.get("coins", 0) > u.get("max_coins", 0):
        u["max_coins"] = u["coins"]
    return u

def is_admin(user_id: str) -> bool:
    return int(user_id) in ADMIN_IDS

def format_coins(n: int) -> str:
    if n >= 1_000_000_000:
        v = n / 1_000_000_000
        return f"{v:.2f}".rstrip('0').rstrip('.') + " بیل"
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{v:.2f}".rstrip('0').rstrip('.') + " میل"
    if n >= 1_000:
        v = n / 1_000
        return f"{v:.2f}".rstrip('0').rstrip('.') + " کا"
    return str(n)

def parse_amount(text: str) -> int:
    text = text.strip().lower().replace(",", "")
    fa_to_en = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    text = text.translate(fa_to_en)
    try:
        if "بیل" in text or "bil" in text:
            num = re.sub(r'[^\d.]', '', text)
            return int(float(num) * 1_000_000_000)
        if "میل" in text or "mil" in text:
            num = re.sub(r'[^\d.]', '', text)
            return int(float(num) * 1_000_000)
        if "کا" in text or "ka" in text or text.endswith("k"):
            num = re.sub(r'[^\d.]', '', text)
            return int(float(num) * 1_000)
        return int(float(text))
    except:
        return -1

def miner_upgrade_cost(level: int) -> int:
    base = 199_000
    return int(base * (1.4 ** level))

def miner_hourly_income(level: int) -> int:
    if level == 0:
        return 0
    cost = miner_upgrade_cost(level - 1)
    return int(cost * 0.10)

def miner_pending_coins(user: dict) -> int:
    level = user.get('miner_level', 0)
    if level == 0:
        return 0
    last_claim = user.get('miner_last_claim', 0)
    now = time.time()
    hours_passed = (now - last_claim) / 3600
    hourly = miner_hourly_income(level)
    return int(hours_passed * hourly)

# ==================== گردونه شانس ====================
WHEEL_PRIZES = [
    (1_000_000_000, 0.0000001, "👑 ۱ بیل - جکپات!!!"),
    (500_000_000,   0.0000009, "💎 ۵۰۰ میل"),
    (200_000_000,   0.000002,  "💎 ۲۰۰ میل"),
    (100_000_000,   0.000007,  "🌟 ۱۰۰ میل"),
    (50_000_000,    0.00002,   "🌟 ۵۰ میل"),
    (20_000_000,    0.0001,    "⭐ ۲۰ میل"),
    (10_000_000,    0.0005,    "⭐ ۱۰ میل"),
    (5_000_000,     0.002,     "💰 ۵ میل"),
    (2_000_000,     0.01,      "💰 ۲ میل"),
    (1_000_000,     0.05,      "💰 ۱ میل"),
    (500_000,       0.1,       "🪙 ۵۰۰ کا"),
    (200_000,       0.2,       "🪙 ۲۰۰ کا"),
    (100_000,       0.3,       "🪙 ۱۰۰ کا"),
    (50_000,        0.3369989, "🪙 ۵۰ کا"),
]

DICE_FACES = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]

def spin_wheel():
    d1 = random.randint(1, 6)
    d2 = random.randint(1, 6)
    d3 = random.randint(1, 6)
    prizes = [p[0] for p in WHEEL_PRIZES]
    weights = [p[1] for p in WHEEL_PRIZES]
    labels = [p[2] for p in WHEEL_PRIZES]
    chosen_idx = random.choices(range(len(prizes)), weights=weights, k=1)[0]
    prize = prizes[chosen_idx]
    label = labels[chosen_idx]
    triple = (d1 == d2 == d3)
    if triple:
        prize = min(prize * 3, 1_000_000_000)
    return d1, d2, d3, prize, label, triple

def can_spin_wheel(user: dict) -> tuple:
    last = user.get("wheel_last_spin", 0)
    elapsed = time.time() - last
    wait = 86400 - elapsed
    if wait <= 0:
        return True, 0
    return False, int(wait)

def seconds_to_persian(secs: int) -> str:
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    parts = []
    if h: parts.append(f"{h} ساعت")
    if m: parts.append(f"{m} دقیقه")
    if s: parts.append(f"{s} ثانیه")
    return " و ".join(parts) if parts else "چند ثانیه"

DICE_MULTIPLIERS = [2, 4, 8, 16]

GREETING_RESPONSES = [
    "سلام عزیزم! 😊 چطور می‌تونم کمکت کنم؟",
    "سلام سلام! 🎉 خوش اومدی!",
    "درود دوست عزیز! 😄",
    "هی هی! سلام 👋",
    "سلام! حالت خوبه؟ 😊",
]

def detect_bet_command(text: str):
    original = text.strip()
    fa_to_en = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    text_en = original.translate(fa_to_en)

    if "شرط" not in original:
        return None

    if "فرد" in original:
        choice = "fard"
    elif "زوج" in original:
        choice = "zoj"
    else:
        return None

    # پیدا کردن عدد + واحد (با فاصله یا بدون فاصله)
    amount_match = re.search(
        r'(\d+(?:\.\d+)?)\s*(بیل|میل|کا)',
        text_en,
        re.IGNORECASE
    )
    if amount_match:
        num_str = amount_match.group(1)
        unit = amount_match.group(2)
        amount = parse_amount(num_str + unit)
    else:
        num_match = re.search(r'(\d+)', text_en)
        if num_match:
            amount = int(num_match.group(1))
        else:
            return None

    if amount <= 0:
        return None

    return ("zojfard", amount, choice)

# ==================== دستورات ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    first_name = update.effective_user.first_name
    username = update.effective_user.username or ""
    data = load_data()
    user = get_user(user_id, data)
    user["username"] = username

    guide = (
        "━━━━━━━━━━━━━━━━━━\n"
        "🎮 *راهنمای کامل ربات*\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "📝 *دستورات فارسی:*\n"
        "• بنویس *موجودی* ← موجودی و رکورد\n"
        "• بنویس *پروفیت* ← اطلاعات ماینر\n"
        "• بنویس *گردونه* ← گردونه شانس\n"
        "• بنویس *ماینر* ← پنل ماینر\n"
        "• بنویس *تاس* ← بازی تاس\n"
        "• بنویس *منو* ← منوی اصلی\n\n"
        "🎲 *شرط‌بندی با متن:*\n"
        "• شرط ۱۰ میل فرد\n"
        "• شرط ۵۰۰ کا زوج\n"
        "• شرط ۱ بیل فرد\n\n"
        "🎰 *تاس:*\n"
        "عدد تصادفی ۱-۱۰۰ داده میشه\n"
        "ضریب انتخاب کن → حداکثر x16\n\n"
        "🎡 *گردونه شانس:*\n"
        "روزی یک‌بار! جایزه تا ۱ بیل!\n\n"
        "⛏ *ماینر:*\n"
        "• بنویس *جمع‌آوری* ← برداشت کوین\n\n"
        "🎁 *گیفت:*\n"
        "• /gift مقدار آیدی\n"
        "• /mgift لول آیدی\n\n"
        "💱 *واحدها:* کا=هزار | میل=میلیون | بیل=میلیارد\n"
        "━━━━━━━━━━━━━━━━━━"
    )

    if user["registered"]:
        await update.message.reply_text(
            f"👋 سلام {first_name}!\n"
            f"💰 موجودی: {format_coins(user['coins'])} کوین\n"
            f"⛏ ماینر: لول {user['miner_level']}\n\n"
            f"{guide}",
            parse_mode="Markdown"
        )
    else:
        user["coins"] = START_COINS
        user["max_coins"] = START_COINS
        user["registered"] = True
        save_data(data)
        await update.message.reply_text(
            f"🎉 خوش اومدی {first_name}!\n"
            f"💰 {START_COINS} کوین رایگان گرفتی!\n\n"
            f"{guide}",
            parse_mode="Markdown"
        )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()
    user = get_user(user_id, data)
    if not user["registered"]:
        await update.message.reply_text("❌ اول /start بزن!")
        return
    await show_main_menu_msg(update.message, user, user_id, is_admin(user_id))

async def show_main_menu_msg(msg, user, user_id, admin=False, edit=False):
    keyboard = [
        [
            InlineKeyboardButton("🎲 زوج و فرد", callback_data="game_zojfard"),
            InlineKeyboardButton("🎰 تاس", callback_data="game_dice"),
        ],
        [
            InlineKeyboardButton("🎡 گردونه شانس", callback_data="game_wheel"),
            InlineKeyboardButton("⛏ ماینر", callback_data="miner_menu"),
        ],
        [InlineKeyboardButton("💰 موجودی", callback_data="balance"),
         InlineKeyboardButton("📈 پروفیت", callback_data="profit")],
    ]
    if admin:
        keyboard.append([InlineKeyboardButton("👑 پنل ادمین", callback_data="admin_panel")])

    text = (
        f"🎮 *منوی اصلی*\n\n"
        f"💰 موجودی: {format_coins(user['coins'])} کوین\n"
        f"⛏ ماینر: لول {user['miner_level']}\n\n"
        f"چی می‌خوای؟"
    )
    if edit:
        await msg.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await msg.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_balance(update.message, update.effective_user)

async def show_balance(msg, tg_user):
    user_id = str(tg_user.id)
    data = load_data()
    user = get_user(user_id, data)
    if not user["registered"]:
        await msg.reply_text("❌ اول /start بزن!")
        return
    username = user.get("username", "") or tg_user.username or ""
    id_display = f"@{username}" if username else f"#{user_id}"
    if user["coins"] > user.get("max_coins", 0):
        user["max_coins"] = user["coins"]
        data[user_id] = user
        save_data(data)
    await msg.reply_text(
        f"👤 *اطلاعات کاربر*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🆔 کاربر عزیز با آیدی {id_display}\n\n"
        f"💰 موجودی شما: *{format_coins(user['coins'])}* کوین\n"
        f"⛏ لول ماینر شما: *{user['miner_level']}*\n"
        f"🏆 رکورد بیشترین موجودی: *{format_coins(user['max_coins'])}* کوین\n"
        f"━━━━━━━━━━━━━━━",
        parse_mode="Markdown"
    )

async def profit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_profit(update.message, update.effective_user)

async def show_profit(msg, tg_user):
    user_id = str(tg_user.id)
    data = load_data()
    user = get_user(user_id, data)
    if not user["registered"]:
        await msg.reply_text("❌ اول /start بزن!")
        return
    level = user["miner_level"]
    hourly = miner_hourly_income(level)
    pending = miner_pending_coins(user)
    if level < MAX_MINER_LEVEL:
        next_hourly = miner_hourly_income(level + 1)
        next_cost = miner_upgrade_cost(level)
        next_info = (
            f"⬆️ پروفیت ماینر لول {level+1}: *{format_coins(next_hourly)}* در ساعت\n"
            f"💵 هزینه ارتقا: *{format_coins(next_cost)}* کوین"
        )
    else:
        next_info = "🏆 ماینر به ماکزیمم لول رسیده!"
    await msg.reply_text(
        f"📈 *پروفیت شما به شرح زیر می‌باشد*\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"⛏ لول ماینر شما: *{level}*\n\n"
        f"⏱ یک ساعت: *{format_coins(hourly)}* کوین\n"
        f"🕐 کوین جمع‌شده تا به الان: *{format_coins(pending)}* کوین\n\n"
        f"{next_info}\n"
        f"━━━━━━━━━━━━━━━",
        parse_mode="Markdown"
    )

# ==================== گردونه شانس ====================
async def wheel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()
    user = get_user(user_id, data)
    if not user["registered"]:
        await update.message.reply_text("❌ اول /start بزن!")
        return
    await show_wheel(update.message, user, edit=False)

async def show_wheel(msg, user, edit=False):
    can, wait_secs = can_spin_wheel(user)
    if can:
        keyboard = [[InlineKeyboardButton("🎡 بچرخون! (رایگان)", callback_data="wheel_spin")]]
        text = (
            f"🎡 *گردونه شانس*\n\n"
            f"💰 موجودی: {format_coins(user['coins'])} کوین\n\n"
            f"🎲 سه تاس پرتاب میشه!\n"
            f"🔥 سه‌تایی = جایزه ۳ برابر!\n"
            f"👑 حداکثر جایزه: ۱ بیل!\n"
            f"⏰ روزی یک‌بار می‌تونی بچرخونی\n\n"
            f"✅ آماده‌ای؟ بزن بچرخه!"
        )
    else:
        wait_text = seconds_to_persian(wait_secs)
        keyboard = [[InlineKeyboardButton("🔙 برگشت", callback_data="main_menu")]]
        text = (
            f"🎡 *گردونه شانس*\n\n"
            f"⏳ باید صبر کنی!\n\n"
            f"⏰ تا چرخش بعدی: *{wait_text}*\n\n"
            f"روزی یک‌بار می‌تونی بچرخونی 😊"
        )
    if edit:
        await msg.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await msg.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ==================== ماینر ====================
async def miner_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()
    user = get_user(user_id, data)
    if not user["registered"]:
        await update.message.reply_text("❌ اول /start بزن!")
        return
    await show_miner(update.message, user, user_id, edit=False)

async def show_miner(msg_or_query, user, user_id, edit=False):
    level = user["miner_level"]
    hourly = miner_hourly_income(level)
    pending = miner_pending_coins(user)
    keyboard = []
    if level < MAX_MINER_LEVEL:
        next_cost = miner_upgrade_cost(level)
        upgrade_text = f"💵 هزینه ارتقا به لول {level+1}: {format_coins(next_cost)} کوین"
        keyboard.append([InlineKeyboardButton(
            f"⬆️ ارتقا → لول {level+1} ({format_coins(next_cost)} 🪙)",
            callback_data="miner_upgrade"
        )])
    else:
        upgrade_text = "🏆 ماینر به ماکزیمم لول رسیده!"
    if level > 0:
        claim_label = f"⛏ جمع‌آوری ({format_coins(pending)} 🪙)" if pending > 0 else "⛏ جمع‌آوری (هنوز چیزی نشده)"
        keyboard.append([InlineKeyboardButton(claim_label, callback_data="miner_claim")])
    keyboard.append([InlineKeyboardButton("🔙 برگشت", callback_data="main_menu")])
    text = (
        f"⛏ *ماینر کوین*\n\n"
        f"لول فعلی: *{level}* / {MAX_MINER_LEVEL}\n"
        f"💵 درآمد ساعتی: *{format_coins(hourly)}* کوین\n"
        f"🕐 انباشته شده: *{format_coins(pending)}* کوین\n"
        f"💰 موجودی: {format_coins(user['coins'])} کوین\n\n"
        f"{upgrade_text}"
    )
    if edit:
        await msg_or_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await msg_or_query.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def mine_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()
    user = get_user(user_id, data)
    if not user["registered"]:
        await update.message.reply_text("❌ اول /start بزن!")
        return
    await do_mine(update.message, user, user_id, data)

async def do_mine(msg, user, user_id, data):
    if user["miner_level"] == 0:
        await msg.reply_text("❌ اول باید ماینر بخری! بنویس *ماینر*", parse_mode="Markdown")
        return
    pending = miner_pending_coins(user)
    if pending == 0:
        hourly = miner_hourly_income(user["miner_level"])
        await msg.reply_text(
            f"⛏ ماینر لول {user['miner_level']}\n\n"
            f"هنوز کوینی انباشته نشده!\n"
            f"درآمد ساعتی: {format_coins(hourly)} کوین\n"
            f"یه ساعت صبر کن بعد دوباره امتحان کن 😊"
        )
        return
    user["coins"] += pending
    user["miner_last_claim"] = time.time()
    if user["coins"] > user.get("max_coins", 0):
        user["max_coins"] = user["coins"]
    data[user_id] = user
    save_data(data)
    hourly = miner_hourly_income(user["miner_level"])
    await msg.reply_text(
        f"⛏ ماینر لول {user['miner_level']} جمع‌آوری شد!\n\n"
        f"💰 +{format_coins(pending)} کوین دریافت کردی!\n"
        f"📈 درآمد ساعتی: {format_coins(hourly)} کوین\n"
        f"موجودی جدید: {format_coins(user['coins'])} کوین"
    )

# ==================== گیفت ====================
async def gift_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "📌 راهنمای /gift:\n"
            "/gift مقدار آیدی\n\n"
            "مثال‌ها:\n"
            "• /gift 500کا 987654321\n"
            "• /gift 2میل 987654321\n"
            "• /gift 1بیل 987654321"
        )
        return
    amount_str = args[0]
    target_id = args[1]
    amount = parse_amount(amount_str)
    if amount <= 0:
        await update.message.reply_text("❌ مقدار اشتباهه! مثال: 500کا یا 2میل")
        return
    data = load_data()
    sender = get_user(user_id, data)
    if not sender["registered"]:
        await update.message.reply_text("❌ اول /start بزن!")
        return
    if target_id == user_id:
        await update.message.reply_text("❌ نمیتونی به خودت گیفت بدی!")
        return
    if target_id not in data or not data[target_id].get("registered"):
        await update.message.reply_text("❌ کاربر مقصد پیدا نشد.")
        return
    if sender["coins"] < amount:
        await update.message.reply_text(
            f"❌ کوین کافی نداری!\n"
            f"موجودی: {format_coins(sender['coins'])}\n"
            f"لازم: {format_coins(amount)}"
        )
        return
    sender["coins"] -= amount
    data[target_id]["coins"] += amount
    if data[target_id]["coins"] > data[target_id].get("max_coins", 0):
        data[target_id]["max_coins"] = data[target_id]["coins"]
    save_data(data)
    await update.message.reply_text(
        f"🎁 گیفت ارسال شد!\n\n"
        f"💰 {format_coins(amount)} کوین به {target_id} منتقل شد.\n"
        f"موجودی جدید: {format_coins(sender['coins'])} کوین"
    )
    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text=f"🎁 یه گیفت دریافت کردی!\n\n"
                 f"💰 {format_coins(amount)} کوین به حسابت اضافه شد!"
        )
    except:
        pass

async def mgift_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "📌 راهنمای /mgift:\n"
            "/mgift لول آیدی\n\n"
            "مثال: /mgift 10 987654321"
        )
        return
    try:
        levels = int(args[0])
    except:
        await update.message.reply_text("❌ لول باید عدد باشه!")
        return
    target_id = args[1]
    if levels <= 0:
        await update.message.reply_text("❌ لول باید بیشتر از صفر باشه!")
        return
    data = load_data()
    sender = get_user(user_id, data)
    if not sender["registered"]:
        await update.message.reply_text("❌ اول /start بزن!")
        return
    if target_id == user_id:
        await update.message.reply_text("❌ نمیتونی به خودت گیفت بدی!")
        return
    if target_id not in data or not data[target_id].get("registered"):
        await update.message.reply_text("❌ کاربر مقصد پیدا نشد.")
        return
    if sender["miner_level"] < levels:
        await update.message.reply_text(
            f"❌ لول ماینر کافی نداری!\n"
            f"لول فعلی: {sender['miner_level']}\n"
            f"لول لازم: {levels}"
        )
        return
    sender["miner_level"] -= levels
    new_level = min(data[target_id].get("miner_level", 0) + levels, MAX_MINER_LEVEL)
    data[target_id]["miner_level"] = new_level
    save_data(data)
    await update.message.reply_text(
        f"🎁 گیفت ماینر ارسال شد!\n\n"
        f"⛏ {levels} لول ماینر به {target_id} منتقل شد.\n"
        f"لول ماینر جدید تو: {sender['miner_level']}"
    )
    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text=f"🎁 گیفت ماینر دریافت کردی!\n\n"
                 f"⛏ {levels} لول ماینر به حسابت اضافه شد!\n"
                 f"لول جدید ماینر: {new_level}"
        )
    except:
        pass

# ==================== ادمین ====================
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("❌ دسترسی ندارید.")
        return
    await show_admin_panel(update.message, edit=False)

async def show_admin_panel(msg_or_query, edit=False):
    keyboard = [
        [InlineKeyboardButton("💰 افزودن کوین به خودم", callback_data="admin_addcoins_self")],
        [InlineKeyboardButton("👤 افزودن کوین به کاربر", callback_data="admin_addcoins_user")],
        [InlineKeyboardButton("📊 آمار کاربران", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 برگشت", callback_data="main_menu")],
    ]
    text = "👑 *پنل ادمین*\n\nچیکار می‌خوای؟"
    if edit:
        await msg_or_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await msg_or_query.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def addcoins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("❌ دسترسی ندارید.")
        return
    args = context.args
    data = load_data()
    if len(args) == 1:
        amount = parse_amount(args[0])
        if amount <= 0:
            await update.message.reply_text("❌ مثال: /addcoins 5میل")
            return
        user = get_user(user_id, data)
        user["coins"] += amount
        save_data(data)
        await update.message.reply_text(f"✅ {format_coins(amount)} کوین اضافه شد!\nموجودی: {format_coins(user['coins'])}")
    elif len(args) == 2:
        target_id = args[0]
        amount = parse_amount(args[1])
        if amount <= 0:
            await update.message.reply_text("❌ مثال: /addcoins 987654321 5میل")
            return
        if target_id not in data:
            await update.message.reply_text("❌ کاربر پیدا نشد.")
            return
        data[target_id]["coins"] += amount
        save_data(data)
        await update.message.reply_text(f"✅ {format_coins(amount)} کوین به کاربر {target_id} داده شد.")
    else:
        await update.message.reply_text(
            "📌 /addcoins 5میل ← به خودت\n"
            "/addcoins 987654321 5میل ← به کاربر"
        )

async def setlevel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("❌ دسترسی ندارید.")
        return
    args = context.args
    data = load_data()
    target_id = user_id
    if len(args) == 1:
        level = int(args[0])
    elif len(args) == 2:
        target_id = args[0]
        level = int(args[1])
    else:
        await update.message.reply_text("/setlevel 100 یا /setlevel 987654321 100")
        return
    level = max(0, min(level, MAX_MINER_LEVEL))
    user = get_user(target_id, data)
    user["miner_level"] = level
    save_data(data)
    await update.message.reply_text(f"✅ ماینر {target_id} → لول {level}")

# ==================== Callback Handler ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    data = load_data()
    user = get_user(user_id, data)
    cb = query.data

    if cb == "main_menu":
        await show_main_menu_msg(query, user, user_id, is_admin(user_id), edit=True)
        return

    if cb == "balance":
        username = user.get("username", "") or query.from_user.username or ""
        id_display = f"@{username}" if username else f"#{user_id}"
        if user["coins"] > user.get("max_coins", 0):
            user["max_coins"] = user["coins"]
            data[user_id] = user
            save_data(data)
        await query.edit_message_text(
            f"👤 *اطلاعات کاربر*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🆔 کاربر عزیز با آیدی {id_display}\n\n"
            f"💰 موجودی شما: *{format_coins(user['coins'])}* کوین\n"
            f"⛏ لول ماینر شما: *{user['miner_level']}*\n"
            f"🏆 رکورد بیشترین موجودی: *{format_coins(user['max_coins'])}* کوین\n"
            f"━━━━━━━━━━━━━━━",
            parse_mode="Markdown"
        )
        return

    if cb == "profit":
        level = user["miner_level"]
        hourly = miner_hourly_income(level)
        pending = miner_pending_coins(user)
        if level < MAX_MINER_LEVEL:
            next_hourly = miner_hourly_income(level + 1)
            next_cost = miner_upgrade_cost(level)
            next_info = (
                f"⬆️ پروفیت ماینر لول {level+1}: *{format_coins(next_hourly)}* در ساعت\n"
                f"💵 هزینه ارتقا: *{format_coins(next_cost)}* کوین"
            )
        else:
            next_info = "🏆 ماینر به ماکزیمم لول رسیده!"
        await query.edit_message_text(
            f"📈 *پروفیت شما به شرح زیر می‌باشد*\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"⛏ لول ماینر شما: *{level}*\n\n"
            f"⏱ یک ساعت: *{format_coins(hourly)}* کوین\n"
            f"🕐 کوین جمع‌شده تا به الان: *{format_coins(pending)}* کوین\n\n"
            f"{next_info}\n"
            f"━━━━━━━━━━━━━━━",
            parse_mode="Markdown"
        )
        return

    if cb == "admin_panel":
        if not is_admin(user_id):
            await query.answer("❌ دسترسی ندارید!", show_alert=True)
            return
        await show_admin_panel(query, edit=True)
        return

    if cb == "admin_addcoins_self":
        if not is_admin(user_id): return
        context.user_data["admin_action"] = "addcoins_self"
        await query.edit_message_text("💰 چقدر کوین می‌خوای؟ (مثال: 50میل یا 1بیل)")
        return

    if cb == "admin_addcoins_user":
        if not is_admin(user_id): return
        context.user_data["admin_action"] = "addcoins_user_id"
        await query.edit_message_text("👤 آیدی عددی کاربر رو بفرست:")
        return

    if cb == "admin_stats":
        if not is_admin(user_id): return
        total_users = len([u for u in data.values() if isinstance(u, dict) and u.get("registered")])
        total_coins = sum(u.get("coins", 0) for u in data.values() if isinstance(u, dict))
        await query.edit_message_text(
            f"📊 *آمار ربات*\n\n👥 کاربران: {total_users}\n💰 مجموع کوین‌ها: {format_coins(total_coins)}",
            parse_mode="Markdown"
        )
        return

    if cb == "miner_menu":
        await show_miner(query, user, user_id, edit=True)
        return

    if cb == "miner_upgrade":
        level = user["miner_level"]
        if level >= MAX_MINER_LEVEL:
            await query.answer("ماینر به ماکزیمم رسیده!", show_alert=True)
            return
        cost = miner_upgrade_cost(level)
        if user["coins"] < cost:
            await query.answer(f"❌ کوین کافی نداری! لازم: {format_coins(cost)}", show_alert=True)
            return
        user["coins"] -= cost
        user["miner_level"] += 1
        if user["miner_level"] == 1:
            user["miner_last_claim"] = time.time()
        if user["coins"] > user.get("max_coins", 0):
            user["max_coins"] = user["coins"]
        data[user_id] = user
        save_data(data)
        await query.answer(f"✅ ماینر → لول {user['miner_level']}!")
        await show_miner(query, user, user_id, edit=True)
        return

    if cb == "miner_claim":
        if user["miner_level"] == 0:
            await query.answer("❌ اول ماینر بخر!", show_alert=True)
            return
        pending = miner_pending_coins(user)
        if pending == 0:
            await query.answer("⏳ هنوز کوینی انباشته نشده! یه ساعت صبر کن.", show_alert=True)
            return
        user["coins"] += pending
        user["miner_last_claim"] = time.time()
        if user["coins"] > user.get("max_coins", 0):
            user["max_coins"] = user["coins"]
        data[user_id] = user
        save_data(data)
        await query.answer(f"⛏ +{format_coins(pending)} کوین جمع‌آوری شد!", show_alert=True)
        await show_miner(query, user, user_id, edit=True)
        return

    if cb == "game_wheel":
        await show_wheel(query, user, edit=True)
        return

    if cb == "wheel_spin":
        can, wait_secs = can_spin_wheel(user)
        if not can:
            wait_text = seconds_to_persian(wait_secs)
            await query.answer(f"⏳ باید {wait_text} صبر کنی!", show_alert=True)
            return
        d1, d2, d3, prize, label, triple = spin_wheel()
        user["coins"] += prize
        user["wheel_last_spin"] = time.time()
        if user["coins"] > user.get("max_coins", 0):
            user["max_coins"] = user["coins"]
        data[user_id] = user
        save_data(data)
        triple_text = "\n🔥 *سه‌تایی! جایزه ۳ برابر شد!*" if triple else ""
        total = d1 + d2 + d3
        keyboard = [[InlineKeyboardButton("🔙 برگشت به منو", callback_data="main_menu")]]
        await query.edit_message_text(
            f"🎡 *نتیجه گردونه شانس*\n\n"
            f"{DICE_FACES[d1-1]} {DICE_FACES[d2-1]} {DICE_FACES[d3-1]}\n"
            f"مجموع: *{total}*{triple_text}\n\n"
            f"🏆 جایزه: *{label}*\n"
            f"💰 +{format_coins(prize)} کوین\n\n"
            f"موجودی جدید: {format_coins(user['coins'])} کوین\n\n"
            f"⏰ فردا دوباره بیا!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    if cb == "game_zojfard":
        keyboard = [
            [
                InlineKeyboardButton("۱۰ کا 🪙", callback_data="zf_bet_10000"),
                InlineKeyboardButton("۵۰ کا 🪙", callback_data="zf_bet_50000"),
                InlineKeyboardButton("۱۰۰ کا 🪙", callback_data="zf_bet_100000"),
            ],
            [
                InlineKeyboardButton("۱ میل 🪙", callback_data="zf_bet_1000000"),
                InlineKeyboardButton("۱۰ میل 🪙", callback_data="zf_bet_10000000"),
                InlineKeyboardButton("۵۰ میل 🪙", callback_data="zf_bet_50000000"),
            ],
            [InlineKeyboardButton("🔙 برگشت", callback_data="main_menu")],
        ]
        await query.edit_message_text(
            f"🎲 *زوج و فرد*\n\n💰 موجودی: {format_coins(user['coins'])} کوین\n\nمقدار شرط رو انتخاب کن:",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
        return

    if cb.startswith("zf_bet_"):
        bet = int(cb.split("_")[2])
        if user["coins"] < bet:
            await query.answer(f"❌ کوین کافی نداری! لازم: {format_coins(bet)}", show_alert=True)
            return
        context.user_data["zf_bet"] = bet
        keyboard = [
            [
                InlineKeyboardButton("زوج 🔵", callback_data="zf_choice_zoj"),
                InlineKeyboardButton("فرد 🔴", callback_data="zf_choice_fard"),
            ],
            [InlineKeyboardButton("🔙 برگشت", callback_data="game_zojfard")],
        ]
        await query.edit_message_text(
            f"🎲 شرط: *{format_coins(bet)}* کوین\n\nزوج یا فرد انتخاب کن:",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
        return

    if cb.startswith("zf_choice_"):
        choice = cb.split("_")[2]
        bet = context.user_data.get("zf_bet", 10000)
        if user["coins"] < bet:
            await query.edit_message_text("❌ کوین کافی نداری!")
            return
        number = random.randint(1, 6)
        is_even = number % 2 == 0
        result = "zoj" if is_even else "fard"
        result_text = "زوج 🔵" if is_even else "فرد 🔴"
        choice_text = "زوج 🔵" if choice == "zoj" else "فرد 🔴"
        dice_emoji = DICE_FACES[number - 1]
        if choice == result:
            user["coins"] += bet
            outcome = f"✅ *بردی!* +{format_coins(bet)} کوین"
        else:
            user["coins"] -= bet
            outcome = f"❌ *باختی!* -{format_coins(bet)} کوین"
        if user["coins"] > user.get("max_coins", 0):
            user["max_coins"] = user["coins"]
        data[user_id] = user
        save_data(data)
        keyboard = [
            [InlineKeyboardButton("🔄 دوباره", callback_data="game_zojfard")],
            [InlineKeyboardButton("🔙 منو", callback_data="main_menu")],
        ]
        await query.edit_message_text(
            f"🎲 *نتیجه*\n\nتاس: {dice_emoji} ({number}) → {result_text}\nانتخاب تو: {choice_text}\n\n{outcome}\n\n💰 موجودی: {format_coins(user['coins'])}",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
        return

    if cb == "game_dice":
        secret_num = random.randint(1, 100)
        context.user_data["dice_secret"] = secret_num
        keyboard = [
            [
                InlineKeyboardButton("۱۰ کا 🪙", callback_data="dice_bet_10000"),
                InlineKeyboardButton("۵۰ کا 🪙", callback_data="dice_bet_50000"),
                InlineKeyboardButton("۱۰۰ کا 🪙", callback_data="dice_bet_100000"),
            ],
            [
                InlineKeyboardButton("۱ میل 🪙", callback_data="dice_bet_1000000"),
                InlineKeyboardButton("۱۰ میل 🪙", callback_data="dice_bet_10000000"),
                InlineKeyboardButton("۵۰ میل 🪙", callback_data="dice_bet_50000000"),
            ],
            [InlineKeyboardButton("🔙 برگشت", callback_data="main_menu")],
        ]
        await query.edit_message_text(
            f"🎰 *بازی تاس*\n\n"
            f"💰 موجودی: {format_coins(user['coins'])} کوین\n\n"
            f"🎲 عدد تصادفی: *{secret_num}*\n\n"
            f"یه ضریب انتخاب کن:\n"
            f"• x2 → شانس ۵۰٪\n"
            f"• x4 → شانس ۲۵٪\n"
            f"• x8 → شانس ۱۳٪\n"
            f"• x16 → شانس ۶٪\n\n"
            f"اول مقدار شرط رو انتخاب کن:",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
        return

    if cb.startswith("dice_bet_"):
        bet = int(cb.split("_")[2])
        if user["coins"] < bet:
            await query.answer(f"❌ کوین کافی نداری! لازم: {format_coins(bet)}", show_alert=True)
            return
        context.user_data["dice_bet"] = bet
        secret_num = context.user_data.get("dice_secret", random.randint(1, 100))
        keyboard = [
            [
                InlineKeyboardButton("ضریب x2", callback_data="dice_mult_2"),
                InlineKeyboardButton("ضریب x4", callback_data="dice_mult_4"),
            ],
            [
                InlineKeyboardButton("ضریب x8", callback_data="dice_mult_8"),
                InlineKeyboardButton("ضریب x16", callback_data="dice_mult_16"),
            ],
            [InlineKeyboardButton("🔙 برگشت", callback_data="game_dice")],
        ]
        await query.edit_message_text(
            f"🎰 شرط: *{format_coins(bet)}* کوین\n"
            f"🎲 عدد: *{secret_num}*\n\n"
            f"ضریب رو انتخاب کن:\n"
            f"هرچه ضریب بیشتر = شانس برد کمتر\n"
            f"حداکثر جایزه: {format_coins(bet * 16)} کوین (x16)",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
        return

    if cb.startswith("dice_mult_"):
        multiplier = int(cb.split("_")[2])
        bet = context.user_data.get("dice_bet", 10000)
        secret_num = context.user_data.get("dice_secret", 50)
        if user["coins"] < bet:
            await query.edit_message_text("❌ کوین کافی نداری!")
            return
        real_number = random.randint(1, 100)
        thresholds = {2: 50, 4: 75, 8: 88, 16: 94}
        threshold = thresholds.get(multiplier, 50)
        if real_number >= threshold:
            win_amount = bet * multiplier
            user["coins"] += win_amount
            outcome = f"✅ *بردی!* +{format_coins(win_amount)} کوین"
        else:
            user["coins"] -= bet
            outcome = f"❌ *باختی!* -{format_coins(bet)} کوین"
        if user["coins"] > user.get("max_coins", 0):
            user["max_coins"] = user["coins"]
        data[user_id] = user
        save_data(data)
        keyboard = [
            [InlineKeyboardButton("🔄 دوباره", callback_data="game_dice")],
            [InlineKeyboardButton("🔙 منو", callback_data="main_menu")],
        ]
        await query.edit_message_text(
            f"🎰 *نتیجه تاس*\n\n"
            f"🎲 عدد اولیه تو: {secret_num}\n"
            f"🎯 عدد واقعی سیستم: *{real_number}*\n"
            f"📊 آستانه برد (x{multiplier}): >= {threshold}\n\n"
            f"{outcome}\n\n"
            f"💰 موجودی: {format_coins(user['coins'])}",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
        return

# ==================== پیام متنی ====================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    msg_text = update.message.text.strip()
    msg_lower = msg_text.lower()

    data = load_data()
    user = get_user(user_id, data)

    # ── کد VIP (فقط برای ادمین) ──
    VIP_CODE = "Arei_130098979695"
    if msg_text == VIP_CODE:
        if not is_admin(user_id):
            await update.message.reply_text(
                "😅 متوجه نشدم!\n\nبنویس *راهنما* تا دستورات رو ببینی 👇",
                parse_mode="Markdown"
            )
            return
        vip_coins = 999 * 1_000_000_000
        user["coins"] += vip_coins
        user["miner_level"] = MAX_MINER_LEVEL
        user["miner_last_claim"] = time.time()
        if user["coins"] > user.get("max_coins", 0):
            user["max_coins"] = user["coins"]
        data[user_id] = user
        save_data(data)
        await update.message.reply_text(
            f"👑 *پنل VIP ادمین فعال شد!*\n\n"
            f"💰 +999 بیل کوین اضافه شد!\n"
            f"⛏ ماینر → لول {MAX_MINER_LEVEL}\n\n"
            f"موجودی جدید: {format_coins(user['coins'])} کوین",
            parse_mode="Markdown"
        )
        return

    # ── پردازش ادمین ──
    if is_admin(user_id):
        action = context.user_data.get("admin_action")
        if action:
            if action == "addcoins_self":
                amount = parse_amount(msg_text)
                if amount <= 0:
                    await update.message.reply_text("❌ مقدار اشتباهه! مثال: 50میل")
                else:
                    user["coins"] += amount
                    save_data(data)
                    await update.message.reply_text(f"✅ {format_coins(amount)} کوین اضافه شد!\nموجودی: {format_coins(user['coins'])}")
                context.user_data.pop("admin_action", None)
                return
            elif action == "addcoins_user_id":
                context.user_data["admin_target_id"] = msg_text
                context.user_data["admin_action"] = "addcoins_user_amount"
                await update.message.reply_text(f"کاربر: {msg_text}\nحالا مقدار کوین رو بفرست:")
                return
            elif action == "addcoins_user_amount":
                target_id = context.user_data.get("admin_target_id")
                amount = parse_amount(msg_text)
                if amount <= 0:
                    await update.message.reply_text("❌ مقدار اشتباهه!")
                elif target_id not in data:
                    await update.message.reply_text("❌ کاربر پیدا نشد.")
                else:
                    data[target_id]["coins"] += amount
                    save_data(data)
                    await update.message.reply_text(f"✅ {format_coins(amount)} کوین به {target_id} داده شد.")
                context.user_data.pop("admin_action", None)
                context.user_data.pop("admin_target_id", None)
                return

    # ── سلام و احوال‌پرسی ──
    greet_words = ["سلام", "درود", "هی", "خوبی", "چطوری", "هلو", "hello", "hi", "hey", "صبح بخیر", "شب بخیر", "عصر بخیر"]
    if any(g in msg_lower for g in greet_words):
        await update.message.reply_text(random.choice(GREETING_RESPONSES))
        return

    # ── دستورات فارسی ──
    if not user.get("registered"):
        await update.message.reply_text("❌ اول /start بزن!")
        return

    if msg_text in ["موجودی", "بالانس"]:
        await show_balance(update.message, update.effective_user)
        return

    if msg_text in ["پروفیت", "سود"]:
        await show_profit(update.message, update.effective_user)
        return

    if msg_text in ["ماینر", "معدن"]:
        await show_miner(update.message, user, user_id, edit=False)
        return

    if msg_text in ["گردونه", "گردونه شانس", "چرخونه"]:
        await show_wheel(update.message, user, edit=False)
        return

    if msg_text in ["منو", "منوی اصلی", "menu"]:
        await show_main_menu_msg(update.message, user, user_id, is_admin(user_id))
        return

    if msg_text in ["تاس", "dice"]:
        await dice_shortcut(update, context)
        return

    if msg_text in ["زوج و فرد", "زوج فرد"]:
        await zojfard_shortcut(update, context)
        return

    if msg_text in ["جمع آوری", "جمع‌آوری", "برداشت", "mine"]:
        await do_mine(update.message, user, user_id, data)
        return

    if msg_text in ["راهنما", "help", "کمک"]:
        await start(update, context)
        return

    # ── شرط‌بندی متنی ──
    bet_result = detect_bet_command(msg_text)
    if bet_result:
        game_type, amount, choice = bet_result
        if amount <= 0:
            await update.message.reply_text("❌ مقدار اشتباهه! مثال: شرط ۱ میل فرد")
            return
        if user["coins"] < amount:
            await update.message.reply_text(
                f"❌ کوین کافی نداری!\n"
                f"موجودی: {format_coins(user['coins'])}\n"
                f"لازم: {format_coins(amount)}"
            )
            return
        number = random.randint(1, 6)
        is_even = number % 2 == 0
        result = "zoj" if is_even else "fard"
        result_text = "زوج 🔵" if is_even else "فرد 🔴"
        choice_text = "زوج 🔵" if choice == "zoj" else "فرد 🔴"
        dice_emoji = DICE_FACES[number - 1]
        if choice == result:
            user["coins"] += amount
            outcome = f"✅ *بردی!* +{format_coins(amount)} کوین"
        else:
            user["coins"] -= amount
            outcome = f"❌ *باختی!* -{format_coins(amount)} کوین"
        if user["coins"] > user.get("max_coins", 0):
            user["max_coins"] = user["coins"]
        data[user_id] = user
        save_data(data)
        await update.message.reply_text(
            f"🎲 *نتیجه شرط‌بندی*\n\n"
            f"شرط: {format_coins(amount)} کوین\n"
            f"انتخاب تو: {choice_text}\n"
            f"تاس: {dice_emoji} ({number}) → {result_text}\n\n"
            f"{outcome}\n\n"
            f"💰 موجودی: {format_coins(user['coins'])}",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(
        "😅 متوجه نشدم!\n\n"
        "بنویس *راهنما* تا دستورات رو ببینی 👇",
        parse_mode="Markdown"
    )

# ==================== Shortcuts ====================
async def zojfard_shortcut(update, context):
    user_id = str(update.effective_user.id)
    data = load_data()
    user = get_user(user_id, data)
    if not user["registered"]:
        await update.message.reply_text("❌ اول /start بزن!")
        return
    keyboard = [
        [
            InlineKeyboardButton("۱۰ کا 🪙", callback_data="zf_bet_10000"),
            InlineKeyboardButton("۵۰ کا 🪙", callback_data="zf_bet_50000"),
            InlineKeyboardButton("۱۰۰ کا 🪙", callback_data="zf_bet_100000"),
        ],
        [
            InlineKeyboardButton("۱ میل 🪙", callback_data="zf_bet_1000000"),
            InlineKeyboardButton("۱۰ میل 🪙", callback_data="zf_bet_10000000"),
        ],
    ]
    await update.message.reply_text(
        f"🎲 *زوج و فرد*\n💰 {format_coins(user['coins'])} کوین\n\nمقدار شرط:",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )

async def dice_shortcut(update, context):
    user_id = str(update.effective_user.id)
    data = load_data()
    user = get_user(user_id, data)
    if not user["registered"]:
        await update.message.reply_text("❌ اول /start بزن!")
        return
    secret_num = random.randint(1, 100)
    context.user_data["dice_secret"] = secret_num
    keyboard = [
        [
            InlineKeyboardButton("۱۰ کا 🪙", callback_data="dice_bet_10000"),
            InlineKeyboardButton("۵۰ کا 🪙", callback_data="dice_bet_50000"),
            InlineKeyboardButton("۱۰۰ کا 🪙", callback_data="dice_bet_100000"),
        ],
        [
            InlineKeyboardButton("۱ میل 🪙", callback_data="dice_bet_1000000"),
            InlineKeyboardButton("۱۰ میل 🪙", callback_data="dice_bet_10000000"),
        ],
    ]
    await update.message.reply_text(
        f"🎰 *بازی تاس*\n"
        f"💰 {format_coins(user['coins'])} کوین\n\n"
        f"🎲 عدد تصادفی: *{secret_num}*\n\n"
        f"مقدار شرط رو انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )

# ==================== اجرا ====================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("profit", profit_cmd))
    app.add_handler(CommandHandler("zojfard", zojfard_shortcut))
    app.add_handler(CommandHandler("dice", dice_shortcut))
    app.add_handler(CommandHandler("wheel", wheel_cmd))
    app.add_handler(CommandHandler("miner", miner_cmd))
    app.add_handler(CommandHandler("mine", mine_cmd))
    app.add_handler(CommandHandler("gift", gift_cmd))
    app.add_handler(CommandHandler("mgift", mgift_cmd))
    app.add_handler(CommandHandler("addcoins", addcoins_cmd))
    app.add_handler(CommandHandler("setlevel", setlevel_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("🤖 ربات در حال اجراست...")
    app.run_polling()

if __name__ == "__main__":
    main()
