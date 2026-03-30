import requests
import time
import threading
import json
import os
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN", "TOKEN_CUA_BAN")
CHAT_ID   = os.environ.get("CHAT_ID",   "CHAT_ID_CUA_BAN")

ALERTS_FILE = "alerts.json"

REPORT_HOUR   = 9
REPORT_MINUTE = 0

# ── CoinGecko ID map ───────────────────────────────────────────
COINGECKO_IDS = {
    "BTCUSDT":  "bitcoin",
    "ETHUSDT":  "ethereum",
    "BNBUSDT":  "binancecoin",
    "SOLUSDT":  "solana",
    "XRPUSDT":  "ripple",
    "DOGEUSDT": "dogecoin",
    "HYPEUSDT": "hyperliquid",
    "ADAUSDT":  "cardano",
    "AVAXUSDT": "avalanche-2",
    "DOTUSDT":  "polkadot",
    "MATICUSDT":"matic-network",
    "LINKUSDT": "chainlink",
    "LTCUSDT":  "litecoin",
    "UNIUSDT":  "uniswap",
    "ATOMUSDT": "cosmos",
    "TRXUSDT":  "tron",
    "SHIBUSDT": "shiba-inu",
    "PEPEUSDT": "pepe",
    "SUIUSDT":  "sui",
    "APTUSDT":  "aptos",
    "ARBUSDT":  "arbitrum",
    "OPUSDT":   "optimism",
    "INJUSDT":  "injective-protocol",
    "NEARUSDT": "near",
    "WIFUSDT":  "dogwifcoin",
    "BONKUSDT": "bonk",
    "ETCUSDT":  "ethereum-classic",
    "XLMUSDT":  "stellar",
    "FILUSDT":  "filecoin",
    "AAVEUSDT": "aave",
    "SANDUSDT": "the-sandbox",
    "MANAUSDT": "decentraland",
    "ALGOUSDT": "algorand",
    "VETUSDT":  "vechain",
}

# Coins không có trên CoinGecko free → dùng Binance/Hyperliquid API
BINANCE_ONLY = {"HYPEUSDT"}

# USDT.D alerts lưu riêng (không phải coin price)
USDTD_ALERTS_FILE = "usdtd_alerts.json"

def load_usdtd_alerts():
    if os.path.exists(USDTD_ALERTS_FILE):
        with open(USDTD_ALERTS_FILE, "r") as f:
            return json.load(f)
    return []

def save_usdtd_alerts(data):
    with open(USDTD_ALERTS_FILE, "w") as f:
        json.dump(data, f, indent=2)

usdtd_alerts    = load_usdtd_alerts()
usdtd_triggered = set()

REPORT_COINS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT",
    "XRPUSDT", "DOGEUSDT", "HYPEUSDT"
]

SYMBOLS = list(COINGECKO_IDS.keys())

SHORT_NAME = {
    "btc": "BTCUSDT", "eth": "ETHUSDT", "bnb": "BNBUSDT",
    "sol": "SOLUSDT", "xrp": "XRPUSDT", "doge": "DOGEUSDT",
    "ada": "ADAUSDT", "avax": "AVAXUSDT", "dot": "DOTUSDT",
    "matic": "MATICUSDT", "link": "LINKUSDT", "ltc": "LTCUSDT",
    "uni": "UNIUSDT", "atom": "ATOMUSDT", "trx": "TRXUSDT",
    "shib": "SHIBUSDT", "pepe": "PEPEUSDT", "sui": "SUIUSDT",
    "apt": "APTUSDT", "arb": "ARBUSDT", "op": "OPUSDT",
    "inj": "INJUSDT", "near": "NEARUSDT", "hype": "HYPEUSDT",
    "wif": "WIFUSDT", "bonk": "BONKUSDT", "etc": "ETCUSDT",
    "xlm": "XLMUSDT", "fil": "FILUSDT", "aave": "AAVEUSDT",
    "sand": "SANDUSDT", "mana": "MANAUSDT", "algo": "ALGOUSDT",
    "vet": "VETUSDT",
}

# ── Lưu/tải alerts ─────────────────────────────────────────────
def load_alerts():
    if os.path.exists(ALERTS_FILE):
        with open(ALERTS_FILE, "r") as f:
            return json.load(f)
    return []

def save_alerts(alerts):
    with open(ALERTS_FILE, "w") as f:
        json.dump(alerts, f, indent=2)

alerts     = load_alerts()
triggered  = set()
user_state = {}

# ── CoinGecko API ───────────────────────────────────────────────
def safe_json(res):
    """Parse JSON an toàn, trả về None nếu lỗi hoặc response rỗng."""
    try:
        if res.status_code == 429:
            print(f"⚠️ CoinGecko rate-limit (429), chờ 10s...")
            time.sleep(10)
            return None
        if res.status_code != 200:
            print(f"⚠️ CoinGecko HTTP {res.status_code}")
            return None
        text = res.text.strip()
        if not text:
            print("⚠️ CoinGecko response rỗng")
            return None
        return res.json()
    except Exception as e:
        print(f"⚠️ JSON parse error: {e} | body: {res.text[:100]}")
        return None

def get_price_binance(symbol):
    """Lấy giá HYPE từ Hyperliquid API (chính chủ, luôn có giá).
    Fallback: Binance Futures → Binance Spot."""
    sym = symbol.upper()

    # 1. Hyperliquid API (nguồn chính xác nhất cho HYPE)
    try:
        res  = requests.post(
            "https://api.hyperliquid.xyz/info",
            json={"type": "metaAndAssetCtxs"},
            timeout=8
        )
        data = safe_json(res)
        if data and isinstance(data, list) and len(data) >= 2:
            universe = data[0].get("universe", [])
            ctxs     = data[1]
            for i, asset in enumerate(universe):
                if asset.get("name", "").upper() == "HYPE":
                    price = float(ctxs[i].get("markPx", 0))
                    if price > 0:
                        print(f"✅ HYPE price from Hyperliquid: {price}")
                        return price, None   # Hyperliquid không có 24h change dễ lấy
    except Exception as e:
        print(f"⚠️ Hyperliquid API error: {e}")

    # 2. Binance Futures fallback
    try:
        res  = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr",
                            params={"symbol": sym}, timeout=8)
        data = safe_json(res)
        if data and "lastPrice" in data:
            return float(data["lastPrice"]), float(data.get("priceChangePercent", 0))
    except Exception as e:
        print(f"⚠️ Binance Futures fallback error: {e}")

    # 3. Binance Spot fallback
    try:
        res  = requests.get("https://api.binance.com/api/v3/ticker/24hr",
                            params={"symbol": sym}, timeout=8)
        data = safe_json(res)
        if data and "lastPrice" in data:
            return float(data["lastPrice"]), float(data.get("priceChangePercent", 0))
    except Exception as e:
        print(f"⚠️ Binance Spot fallback error: {e}")

    return None, None

def get_coin_data(symbol):
    cg_id = COINGECKO_IDS.get(symbol.upper())
    if not cg_id:
        return None
    url = f"https://api.coingecko.com/api/v3/coins/{cg_id}"
    params = {"localization": "false", "tickers": "false", "community_data": "false", "developer_data": "false"}
    res  = requests.get(url, params=params, timeout=10)
    return safe_json(res)

def get_price(symbol):
    if symbol.upper() in BINANCE_ONLY:
        price, _ = get_price_binance(symbol)
        return price
    cg_id = COINGECKO_IDS.get(symbol.upper())
    if not cg_id:
        return None
    url    = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": cg_id, "vs_currencies": "usd"}
    res    = requests.get(url, params=params, timeout=8)
    data   = safe_json(res)
    if not data:
        return None
    return float(data[cg_id]["usd"]) if cg_id in data else None

def get_prices_batch(symbols):
    result = {}

    # Lấy coins Binance-only trước
    for sym in symbols:
        if sym in BINANCE_ONLY:
            price, change = get_price_binance(sym)
            if price is not None:
                result[sym] = {"price": price, "change": change}

    # Lấy phần còn lại từ CoinGecko
    cg_symbols = [s for s in symbols if s not in BINANCE_ONLY]
    ids = [COINGECKO_IDS[s] for s in cg_symbols if s in COINGECKO_IDS]
    if not ids:
        return result
    url    = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": ",".join(ids),
        "vs_currencies": "usd",
        "include_24hr_change": "true",
        "include_24hr_vol": "true",
        "include_market_cap": "false"
    }
    res  = requests.get(url, params=params, timeout=10)
    data = safe_json(res)
    if not data:
        return result
    for sym in cg_symbols:
        cg_id = COINGECKO_IDS.get(sym)
        if cg_id and cg_id in data:
            result[sym] = {
                "price":  float(data[cg_id]["usd"]),
                "change": float(data[cg_id].get("usd_24h_change", 0)),
            }
    return result

def get_usdt_dominance():
    try:
        url  = "https://api.coingecko.com/api/v3/global"
        res  = requests.get(url, timeout=10)
        data = safe_json(res)
        if not data:
            return None, None
        dom        = data["data"]["market_cap_percentage"].get("usdt", 0)
        total_mcap = data["data"]["total_market_cap"].get("usd", 0)
        return round(dom, 2), total_mcap
    except Exception as e:
        print(f"⚠️ Lỗi get_usdt_dominance: {e}")
        return None, None

# ── TradingView link ────────────────────────────────────────────
def chart_link(symbol):
    base = symbol.replace("USDT", "")
    return f"https://www.tradingview.com/chart/?symbol=BINANCE:{base}USDT"

# ── Resolve symbol ──────────────────────────────────────────────
def resolve_symbol(text):
    t = text.strip().lower().replace("/", "").replace("-", "")
    if t in SHORT_NAME:
        return SHORT_NAME[t]
    full = t.upper()
    if not full.endswith("USDT"):
        full += "USDT"
    return full

# ── Gửi giá 1 coin ─────────────────────────────────────────────
def send_price_info(chat_id, symbol):
    try:
        name = symbol.replace("USDT", "")
        link = chart_link(symbol)

        if symbol.upper() in BINANCE_ONLY:
            price, change = get_price_binance(symbol)
            if price is None:
                send(chat_id, f"❌ Lỗi lấy dữ liệu <b>{symbol}</b> từ Binance, thử lại sau!")
                return
        else:
            cg_id = COINGECKO_IDS.get(symbol.upper())
            if not cg_id:
                send(chat_id, f"❌ Không hỗ trợ symbol <b>{symbol}</b>")
                return
            url    = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                "ids": cg_id,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_24hr_high": "true",
                "include_24hr_low": "true",
            }
            res    = requests.get(url, params=params, timeout=8)
            raw    = safe_json(res)
            if not raw or cg_id not in raw:
                send(chat_id, f"❌ Lỗi lấy dữ liệu <b>{symbol}</b>: API không phản hồi (có thể bị rate-limit, thử lại sau 30s)")
                return
            data   = raw[cg_id]
            price  = float(data["usd"])
            change = float(data.get("usd_24h_change", 0))

        emoji = "📈" if change >= 0 else "📉"
        sign  = "+" if change >= 0 else ""
        send(chat_id,
             f"{emoji} <b>{name}/USDT</b>\n"
             f"Giá: <b>${price:,.4f}</b>\n"
             f"24h: {sign}{change:.2f}%\n"
             f"📊 <a href='{link}'>Xem chart TradingView</a>")
    except Exception as e:
        send(chat_id, f"❌ Lỗi lấy dữ liệu <b>{symbol}</b>: {e}")

# ── Gửi USDT.D ─────────────────────────────────────────────────
def send_usdt_dominance(chat_id):
    send(chat_id, "⏳ Đang lấy dữ liệu USDT Dominance...")
    dom, total_mcap = get_usdt_dominance()
    if dom is None:
        send(chat_id, "❌ Lỗi lấy dữ liệu USDT Dominance!")
        return
    total_str = f"${total_mcap/1e12:.2f}T" if total_mcap else "N/A"
    send(chat_id,
         f"💵 <b>USDT Dominance</b>\n"
         f"Dominance: <b>{dom}%</b>\n"
         f"Tổng Market Cap: {total_str}\n\n"
         f"📊 <a href='https://www.tradingview.com/chart/?symbol=CRYPTOCAP:USDT.D'>Xem chart USDT.D</a>")

# ── Gửi báo cáo sáng ───────────────────────────────────────────
def send_morning_report():
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    msg = f"🌅 <b>Báo cáo thị trường sáng {now}</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n\n"

    # USDT.D
    dom, total_mcap = get_usdt_dominance()
    if dom:
        total_str = f"${total_mcap/1e12:.2f}T" if total_mcap else ""
        msg += (f"💵 <b><a href='https://www.tradingview.com/chart/?symbol=CRYPTOCAP:USDT.D'>USDT.D</a></b>: {dom}%"
                f"   | Total MCap: {total_str}\n\n")

    # Lấy giá batch
    prices = get_prices_batch(REPORT_COINS)
    for symbol in REPORT_COINS:
        try:
            d      = prices.get(symbol)
            if not d:
                msg += f"⚠️ {symbol}: Lỗi lấy dữ liệu\n\n"
                continue
            price  = d["price"]
            change = d["change"]
            emoji  = "📈" if change >= 0 else "📉"
            sign   = "+" if change >= 0 else ""
            name   = symbol.replace("USDT", "")
            link   = chart_link(symbol)
            msg += (f"{emoji} <b><a href='{link}'>{name}</a></b>: ${price:,.4f}\n"
                    f"   {sign}{change:.2f}%\n\n")
        except:
            msg += f"⚠️ {symbol}: Lỗi lấy dữ liệu\n\n"

    msg += "━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📋 Alerts đang bật: <b>{len(alerts)}</b>\n"
    msg += "Chúc bạn trading vui! 🚀"

    send(CHAT_ID, msg)
    print(f"📊 Đã gửi báo cáo sáng lúc {now}")

def morning_report_checker():
    sent_today = None
    while True:
        now   = datetime.now()
        today = now.date()
        if (now.hour == REPORT_HOUR and
                now.minute == REPORT_MINUTE and
                sent_today != today):
            send_morning_report()
            sent_today = today
        time.sleep(30)

# ── Telegram ────────────────────────────────────────────────────
MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "💰 Xem giá"}, {"text": "🔔 Đặt Alert"}],
        [{"text": "📋 Danh sách Alert"}, {"text": "🗑 Xoá Alert"}],
        [{"text": "📊 Báo cáo thị trường"}, {"text": "💵 USDT.D"}],
        [{"text": "🎯 Alert USDT.D"}, {"text": "📋 Alert USDT.D List"}],
    ],
    "resize_keyboard": True,
    "persistent": True
}

def send(chat_id, msg, reply_markup=None):
    url     = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":                  chat_id,
        "text":                     msg,
        "parse_mode":               "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(url, json=payload)

def get_updates(offset=None):
    url    = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 10}
    if offset:
        params["offset"] = offset
    res = requests.get(url, params=params, timeout=15)
    return res.json().get("result", [])

# ── Xử lý tin nhắn ─────────────────────────────────────────────
def handle_message(chat_id, text):
    text  = text.strip()
    state = user_state.get(chat_id, {})

    # ── /start ──
    if text == "/start":
        send(chat_id,
             "👋 <b>Chào mừng đến Alert Bot!</b>\n\n"
             "Dùng các nút bên dưới hoặc gõ lệnh:\n"
             "/alert — Đặt alert giá mới\n"
             "/list — Xem danh sách alert\n"
             "/delete — Xoá alert\n"
             "/usdtd — Xem USDT Dominance\n"
             "/report — Báo cáo thị trường ngay\n\n"
             "💡 Gõ nhanh: <b>btc</b>, <b>eth</b>, <b>sol</b>... để xem giá!",
             reply_markup=MAIN_KEYBOARD)
        user_state[chat_id] = {}
        return

    # ── Nút Menu ──
    if text == "💰 Xem giá":
        send(chat_id, "💡 Gõ tên coin để xem giá:\nVí dụ: <b>btc</b>, <b>eth</b>, <b>sol</b>, <b>hype</b>...")
        return

    if text == "🔔 Đặt Alert":
        text = "/alert"

    if text == "📋 Danh sách Alert":
        text = "/list"

    if text == "🗑 Xoá Alert":
        text = "/delete"

    if text == "📊 Báo cáo thị trường":
        send(chat_id, "⏳ Đang lấy dữ liệu thị trường...")
        send_morning_report()
        return

    if text == "💵 USDT.D":
        send_usdt_dominance(chat_id)
        return

    # ── USDT.D Alert ──
    if text in ["🎯 Alert USDT.D", "/alertusdtd"]:
        dom, _ = get_usdt_dominance()
        dom_str = f" (hiện tại: {dom}%)" if dom else ""
        send(chat_id,
             f"🎯 <b>Đặt Alert USDT.D</b>{dom_str}\n\n"
             f"Nhập ngưỡng % muốn cảnh báo\n"
             f"Ví dụ: <b>5.5</b> (above) hoặc <b>4.8</b> (below)")
        user_state[chat_id] = {"step": "usdtd_wait_value"}
        return

    if text in ["📋 Alert USDT.D List", "/listusdtd"]:
        if not usdtd_alerts:
            send(chat_id, "📭 Chưa có USDT.D alert nào!", reply_markup=MAIN_KEYBOARD)
            return
        msg = "📋 <b>USDT.D Alerts:</b>\n\n"
        for i, a in enumerate(usdtd_alerts):
            emoji = "📈" if a["condition"] == "above" else "📉"
            msg += f"{i+1}. {emoji} USDT.D {a['condition'].upper()} {a['value']}%\n"
        msg += f"\nGõ /delusdtd [số] để xoá"
        send(chat_id, msg, reply_markup=MAIN_KEYBOARD)
        return

    if text.lower().startswith("/delusdtd"):
        parts = text.split()
        if len(parts) < 2:
            send(chat_id, "💡 Dùng: /delusdtd 1")
            return
        try:
            idx = int(parts[1]) - 1
            if 0 <= idx < len(usdtd_alerts):
                removed = usdtd_alerts.pop(idx)
                save_usdtd_alerts(usdtd_alerts)
                send(chat_id, f"✅ Đã xoá: USDT.D {removed['condition'].upper()} {removed['value']}%",
                     reply_markup=MAIN_KEYBOARD)
            else:
                send(chat_id, "❌ Số không hợp lệ!")
        except:
            send(chat_id, "❌ Vui lòng nhập số!")
        return

    # ── /report ──
    if text == "/report":
        send(chat_id, "⏳ Đang lấy dữ liệu thị trường...")
        send_morning_report()
        return

    # ── /usdtd ──
    if text.lower() in ["/usdtd", "usdt.d", "usdtd"]:
        send_usdt_dominance(chat_id)
        return

    # ── /price ──
    if text.lower().startswith("/price"):
        parts = text.split()
        if len(parts) < 2:
            send(chat_id, "💡 Dùng: /price BTC hoặc gõ thẳng <b>btc</b>")
            return
        symbol = resolve_symbol(parts[1])
        send_price_info(chat_id, symbol)
        return

    # ── /list ──
    if text == "/list":
        if not alerts:
            send(chat_id, "📭 Chưa có alert nào!", reply_markup=MAIN_KEYBOARD)
            return
        msg = "📋 <b>Danh sách alert:</b>\n\n"
        for i, a in enumerate(alerts):
            emoji = "📈" if a["condition"] == "above" else "📉"
            msg  += f"{i+1}. {emoji} {a['symbol']} {a['condition'].upper()} ${a['price']:,.2f}\n"
        send(chat_id, msg, reply_markup=MAIN_KEYBOARD)
        return

    # ── /delete ──
    if text == "/delete":
        if not alerts:
            send(chat_id, "📭 Chưa có alert nào để xoá!", reply_markup=MAIN_KEYBOARD)
            return
        msg = "🗑 <b>Nhập số thứ tự alert muốn xoá:</b>\n\n"
        for i, a in enumerate(alerts):
            emoji = "📈" if a["condition"] == "above" else "📉"
            msg  += f"{i+1}. {emoji} {a['symbol']} {a['condition'].upper()} ${a['price']:,.2f}\n"
        send(chat_id, msg)
        user_state[chat_id] = {"step": "delete"}
        return

    # ── /alert ──
    if text == "/alert":
        keyboard = []
        row = []
        for i, sym in enumerate(SYMBOLS):
            row.append({"text": sym, "callback_data": f"sym_{sym}"})
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        send(chat_id, "📌 <b>Chọn coin muốn đặt alert:</b>",
             reply_markup={"inline_keyboard": keyboard})
        user_state[chat_id] = {"step": "wait_symbol"}
        return

    # ── Gõ tên coin ngắn ──
    lower = text.lower().replace("/", "").replace("-", "")
    if lower in SHORT_NAME:
        send_price_info(chat_id, SHORT_NAME[lower])
        return

    # ── Các bước hội thoại ──
    if state.get("step") == "delete":
        try:
            idx = int(text) - 1
            if 0 <= idx < len(alerts):
                removed = alerts.pop(idx)
                save_alerts(alerts)
                send(chat_id,
                     f"✅ Đã xoá: <b>{removed['symbol']} {removed['condition'].upper()} ${removed['price']:,.2f}</b>",
                     reply_markup=MAIN_KEYBOARD)
            else:
                send(chat_id, "❌ Số không hợp lệ!")
        except:
            send(chat_id, "❌ Vui lòng nhập số thứ tự!")
        user_state[chat_id] = {}
        return

    if state.get("step") == "usdtd_wait_value":
        try:
            value = float(text.replace(",", "."))
            user_state[chat_id]["usdtd_value"] = value
            user_state[chat_id]["step"] = "usdtd_wait_condition"
            send(chat_id,
                 f"📊 Ngưỡng <b>{value}%</b>\n\nBáo khi USDT.D:",
                 reply_markup={"inline_keyboard": [[
                     {"text": "📈 Above (vượt lên)", "callback_data": f"usdtd_above_{value}"},
                     {"text": "📉 Below (rớt xuống)", "callback_data": f"usdtd_below_{value}"}
                 ]]})
        except:
            send(chat_id, "❌ Vui lòng nhập số hợp lệ! Ví dụ: 5.5")
        return

    if state.get("step") == "wait_price":
        try:
            price = float(text.replace(",", ""))
            user_state[chat_id]["price"] = price
            user_state[chat_id]["step"]  = "wait_condition"
            send(chat_id, f"📊 Giá <b>${price:,.2f}</b>\n\nBáo khi giá:",
                 reply_markup={"inline_keyboard": [[
                     {"text": "📈 Above (vượt lên)", "callback_data": "cond_above"},
                     {"text": "📉 Below (rớt xuống)", "callback_data": "cond_below"}
                 ]]})
        except:
            send(chat_id, "❌ Vui lòng nhập số hợp lệ! Ví dụ: 90000")
        return

    send(chat_id, "💡 Gõ /start để xem hướng dẫn hoặc dùng nút bên dưới!",
         reply_markup=MAIN_KEYBOARD)

# ── Xử lý callback ──────────────────────────────────────────────
def handle_callback(chat_id, callback_id, data):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
                  json={"callback_query_id": callback_id})

    state = user_state.get(chat_id, {})

    if data.startswith("usdtd_"):
        parts     = data.split("_")   # ["usdtd", "above"/"below", "value"]
        condition = parts[1]
        value     = float(parts[2])
        usdtd_alerts.append({"condition": condition, "value": value})
        save_usdtd_alerts(usdtd_alerts)
        emoji = "📈" if condition == "above" else "📉"
        send(chat_id,
             f"{emoji} <b>USDT.D Alert đã đặt!</b>\n\n"
             f"Báo khi USDT.D <b>{condition.upper()} {value}%</b>\n\n"
             f"📊 <a href='https://www.tradingview.com/chart/?symbol=CRYPTOCAP:USDT.D'>Xem chart USDT.D</a>",
             reply_markup=MAIN_KEYBOARD)
        user_state[chat_id] = {}
        return

    if data.startswith("sym_"):
        symbol = data.replace("sym_", "")
        try:
            price     = get_price(symbol)
            price_str = f"(hiện tại: ${price:,.4f})" if price else ""
        except:
            price_str = ""
        user_state[chat_id] = {"step": "wait_price", "symbol": symbol}
        send(chat_id, f"✅ Đã chọn <b>{symbol}</b> {price_str}\n\n💰 Nhập mức giá muốn đặt alert:")
        return

    if data.startswith("cond_"):
        condition = data.replace("cond_", "")
        symbol    = state.get("symbol")
        price     = state.get("price")
        if symbol and price:
            alerts.append({"symbol": symbol, "condition": condition, "price": price})
            save_alerts(alerts)
            emoji = "📈" if condition == "above" else "📉"
            link  = chart_link(symbol)
            send(chat_id,
                 f"{emoji} <b>Alert đã đặt!</b>\n\n"
                 f"Coin: <b>{symbol}</b>\n"
                 f"Điều kiện: <b>{condition.upper()}</b>\n"
                 f"Giá: <b>${price:,.2f}</b>\n\n"
                 f"📊 <a href='{link}'>Xem chart TradingView</a>",
                 reply_markup=MAIN_KEYBOARD)
        user_state[chat_id] = {}
        return

# ── Price checker ───────────────────────────────────────────────
def price_checker():
    while True:
        # Check coin alerts
        for alert in alerts[:]:
            key = f"{alert['symbol']}_{alert['condition']}_{alert['price']}"
            try:
                price = get_price(alert["symbol"])
                if price is None:
                    continue
                hit = (alert["condition"] == "above" and price >= alert["price"]) or \
                      (alert["condition"] == "below" and price <= alert["price"])

                if hit and key not in triggered:
                    emoji = "📈" if alert["condition"] == "above" else "📉"
                    link  = chart_link(alert["symbol"])
                    name  = alert["symbol"].replace("USDT", "")
                    msg   = (f"🚨 <b>ALERT TRIGGERED!</b>\n\n"
                             f"{emoji} <b>{name}/USDT</b>\n"
                             f"Giá hiện tại: <b>${price:,.4f}</b>\n"
                             f"Điều kiện: {alert['condition'].upper()} ${alert['price']:,.2f}\n\n"
                             f"📊 <a href='{link}'>Xem chart TradingView</a>")
                    send(CHAT_ID, msg)
                    triggered.add(key)
                    print(f"📨 Đã gửi alert: {key}")
                elif not hit and key in triggered:
                    triggered.discard(key)
            except Exception as e:
                print(f"⚠️ Lỗi check giá: {e}")

        # Check USDT.D alerts
        if usdtd_alerts:
            try:
                dom, _ = get_usdt_dominance()
                if dom is not None:
                    for a in usdtd_alerts:
                        key = f"usdtd_{a['condition']}_{a['value']}"
                        hit = (a["condition"] == "above" and dom >= a["value"]) or \
                              (a["condition"] == "below" and dom <= a["value"])
                        if hit and key not in usdtd_triggered:
                            emoji = "📈" if a["condition"] == "above" else "📉"
                            send(CHAT_ID,
                                 f"🚨 <b>USDT.D ALERT!</b>\n\n"
                                 f"{emoji} USDT Dominance hiện tại: <b>{dom}%</b>\n"
                                 f"Điều kiện: {a['condition'].upper()} {a['value']}%\n\n"
                                 f"💡 Xem xét lại vị thế BTC/altcoin!\n"
                                 f"📊 <a href='https://www.tradingview.com/chart/?symbol=CRYPTOCAP:USDT.D'>Xem chart USDT.D</a>")
                            usdtd_triggered.add(key)
                            print(f"📨 USDT.D alert: {key} (dom={dom}%)")
                        elif not hit and key in usdtd_triggered:
                            usdtd_triggered.discard(key)
            except Exception as e:
                print(f"⚠️ Lỗi check USDT.D: {e}")

        time.sleep(60)

# ── Main ────────────────────────────────────────────────────────
def main():
    print(f"✅ Bot đang chạy... Báo cáo sáng lúc {REPORT_HOUR:02d}:{REPORT_MINUTE:02d}")
    send(CHAT_ID,
         f"🤖 <b>Bot đã khởi động!</b>\n"
         f"🌅 Báo cáo sáng tự động lúc <b>{REPORT_HOUR:02d}:{REPORT_MINUTE:02d}</b>\n"
         f"Gõ /start để xem hướng dẫn",
         reply_markup=MAIN_KEYBOARD)

    threading.Thread(target=price_checker,          daemon=True).start()
    threading.Thread(target=morning_report_checker, daemon=True).start()

    offset = None
    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                if "message" in update:
                    msg     = update["message"]
                    chat_id = str(msg["chat"]["id"])
                    text    = msg.get("text", "")
                    if text:
                        handle_message(chat_id, text)
                elif "callback_query" in update:
                    cb      = update["callback_query"]
                    chat_id = str(cb["message"]["chat"]["id"])
                    handle_callback(chat_id, cb["id"], cb["data"])
        except Exception as e:
            print(f"⚠️ Lỗi: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
