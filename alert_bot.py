import requests
import time
import threading
import json
import os
from datetime import datetime

BOT_TOKEN = "TOKEN_CỦA_BẠN"
CHAT_ID   = "CHAT_ID_CỦA_BẠN"

ALERTS_FILE = "alerts.json"

REPORT_HOUR   = 9
REPORT_MINUTE = 0

REPORT_COINS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "HYPEUSDT"
]

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT",
    "LINKUSDT", "LTCUSDT", "UNIUSDT", "ATOMUSDT", "ETCUSDT",
    "XLMUSDT", "NEARUSDT", "FILUSDT", "AAVEUSDT", "SANDUSDT",
    "MANAUSDT", "AXSUSDT", "FTMUSDT", "ALGOUSDT", "VETUSDT",
    "ICPUSDT", "THETAUSDT", "EGLDUSDT", "FLOWUSDT", "XTZUSDT",
    "TRXUSDT", "SHIBUSDT", "PEPEUSDT", "WIFUSDT", "BONKUSDT",
    "SUIUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "INJUSDT", "HYPEUSDT",
]

SHORT_NAME = {
    "btc": "BTCUSDT", "eth": "ETHUSDT", "bnb": "BNBUSDT",
    "sol": "SOLUSDT", "xrp": "XRPUSDT", "doge": "DOGEUSDT",
    "ada": "ADAUSDT", "avax": "AVAXUSDT", "dot": "DOTUSDT",
    "matic": "MATICUSDT", "link": "LINKUSDT", "ltc": "LTCUSDT",
    "uni": "UNIUSDT", "atom": "ATOMUSDT", "trx": "TRXUSDT",
    "shib": "SHIBUSDT", "pepe": "PEPEUSDT", "sui": "SUIUSDT",
    "apt": "APTUSDT", "arb": "ARBUSDT", "op": "OPUSDT",
    "inj": "INJUSDT", "near": "NEARUSDT", "hype": "HYPEUSDT",
    "wif": "WIFUSDT", "bonk": "BONKUSDT",
}

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

def get_price(symbol):
    url  = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol.upper()}"
    res  = requests.get(url, timeout=5)
    data = res.json()
    return float(data["price"]) if "price" in data else None

def get_ticker_24h(symbol):
    url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol.upper()}"
    res = requests.get(url, timeout=5)
    return res.json()

def get_usdt_dominance():
    try:
        url = "https://api.coingecko.com/api/v3/global"
        res = requests.get(url, timeout=8)
        data = res.json()
        dom        = data["data"]["market_cap_percentage"].get("usdt", 0)
        total_mcap = data["data"]["total_market_cap"].get("usd", 0)
        return round(dom, 2), total_mcap
    except:
        return None, None

def chart_link(symbol):
    base = symbol.replace("USDT", "")
    return f"https://www.tradingview.com/chart/?symbol=BINANCE:{base}USDT"

def resolve_symbol(text):
    t = text.strip().lower().replace("/", "").replace("-", "")
    if t in SHORT_NAME:
        return SHORT_NAME[t]
    full = t.upper()
    if not full.endswith("USDT"):
        full += "USDT"
    return full

def send_price_info(chat_id, symbol):
    try:
        data   = get_ticker_24h(symbol)
        price  = float(data["lastPrice"])
        change = float(data["priceChangePercent"])
        high   = float(data["highPrice"])
        low    = float(data["lowPrice"])
        emoji  = "📈" if change >= 0 else "📉"
        sign   = "+" if change >= 0 else ""
        name   = symbol.replace("USDT", "")
        link   = chart_link(symbol)
        send(chat_id,
             f"{emoji} <b>{name}/USDT</b>\n"
             f"Giá: <b>${price:,.4f}</b>\n"
             f"24h: {sign}{change:.2f}%\n"
             f"High: ${high:,.4f} | Low: ${low:,.4f}\n"
             f"📊 <a href='{link}'>Xem chart TradingView</a>")
    except:
        send(chat_id, f"❌ Không tìm thấy symbol <b>{symbol}</b>")

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

def send_morning_report():
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    msg = f"🌅 <b>Báo cáo thị trường sáng {now}</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n\n"

    dom, total_mcap = get_usdt_dominance()
    if dom:
        total_str = f"${total_mcap/1e12:.2f}T" if total_mcap else ""
        msg += (f"💵 <b><a href='https://www.tradingview.com/chart/?symbol=CRYPTOCAP:USDT.D'>USDT.D</a></b>: {dom}%"
                f"   | Total MCap: {total_str}\n\n")

    for symbol in REPORT_COINS:
        try:
            data   = get_ticker_24h(symbol)
            price  = float(data["lastPrice"])
            change = float(data["priceChangePercent"])
            high   = float(data["highPrice"])
            low    = float(data["lowPrice"])
            emoji  = "📈" if change >= 0 else "📉"
            sign   = "+" if change >= 0 else ""
            name   = symbol.replace("USDT", "")
            link   = chart_link(symbol)
            msg += (f"{emoji} <b><a href='{link}'>{name}</a></b>: ${price:,.4f}\n"
                    f"   {sign}{change:.2f}% | H: ${high:,.2f} | L: ${low:,.2f}\n\n")
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

def send(chat_id, msg, reply_markup=None):
    url     = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "HTML",
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

def handle_message(chat_id, text):
    text  = text.strip()
    state = user_state.get(chat_id, {})

    if text == "/start":
        send(chat_id,
             "👋 <b>Chào mừng đến Alert Bot!</b>\n\n"
             "Các lệnh:\n"
             "/alert — Đặt alert giá mới\n"
             "/list — Xem danh sách alert\n"
             "/delete — Xoá alert\n"
             "/usdtd — Xem USDT Dominance\n"
             "/report — Báo cáo thị trường ngay\n"
             "/help — Hướng dẫn\n\n"
             "💡 <b>Gõ nhanh:</b> btc, eth, sol, hype... để xem giá ngay!")
        user_state[chat_id] = {}
        return

    if text == "/help":
        send(chat_id,
             "📖 <b>Hướng dẫn:</b>\n\n"
             "⚡ Xem giá nhanh: gõ <b>btc</b> hoặc <b>eth</b>\n"
             "💵 USDT Dominance: gõ <b>/usdtd</b>\n"
             "🔔 Đặt alert: gõ <b>/alert</b>\n"
             f"🌅 Báo cáo sáng tự động lúc <b>{REPORT_HOUR:02d}:{REPORT_MINUTE:02d}</b>")
        return

    if text == "/report":
        send(chat_id, "⏳ Đang lấy dữ liệu thị trường...")
        send_morning_report()
        return

    if text.lower() in ["/usdtd", "usdt.d", "usdtd"]:
        send_usdt_dominance(chat_id)
        return

    if text.lower().startswith("/price"):
        parts = text.split()
        if len(parts) < 2:
            send(chat_id, "💡 Dùng: /price BTC hoặc /price BTCUSDT")
            return
        symbol = resolve_symbol(parts[1])
        send_price_info(chat_id, symbol)
        return

    if text == "/list":
        if not alerts:
            send(chat_id, "📭 Chưa có alert nào!")
            return
        msg = "📋 <b>Danh sách alert:</b>\n\n"
        for i, a in enumerate(alerts):
            msg += f"{i+1}. {a['symbol']} {a['condition'].upper()} ${a['price']:,.2f}\n"
        send(chat_id, msg)
        return

    if text == "/delete":
        if not alerts:
            send(chat_id, "📭 Chưa có alert nào để xoá!")
            return
        msg = "🗑 <b>Chọn số thứ tự alert muốn xoá:</b>\n\n"
        for i, a in enumerate(alerts):
            msg += f"{i+1}. {a['symbol']} {a['condition'].upper()} ${a['price']:,.2f}\n"
        send(chat_id, msg)
        user_state[chat_id] = {"step": "delete"}
        return

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

    lower = text.lower().replace("/", "").replace("-", "")
    if lower in SHORT_NAME:
        send_price_info(chat_id, SHORT_NAME[lower])
        return

    if state.get("step") == "delete":
        try:
            idx = int(text) - 1
            if 0 <= idx < len(alerts):
                removed = alerts.pop(idx)
                save_alerts(alerts)
                send(chat_id, f"✅ Đã xoá: <b>{removed['symbol']} {removed['condition'].upper()} ${removed['price']:,.2f}</b>")
            else:
                send(chat_id, "❌ Số không hợp lệ!")
        except:
            send(chat_id, "❌ Vui lòng nhập số thứ tự!")
        user_state[chat_id] = {}
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

    send(chat_id, "💡 Gõ /start để xem hướng dẫn")

def handle_callback(chat_id, callback_id, data):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
                  json={"callback_query_id": callback_id})

    state = user_state.get(chat_id, {})

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
            send(chat_id,
                 f"{emoji} <b>Alert đã đặt!</b>\n\n"
                 f"Coin: <b>{symbol}</b>\n"
                 f"Điều kiện: <b>{condition.upper()}</b>\n"
                 f"Giá: <b>${price:,.2f}</b>\n\n"
                 f"Bot sẽ báo khi giá chạm mức này! 🔔")
        user_state[chat_id] = {}
        return

def price_checker():
    while True:
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
        time.sleep(30)

def main():
    print(f"✅ Bot đang chạy... Báo cáo sáng lúc {REPORT_HOUR:02d}:{REPORT_MINUTE:02d}")
    send(CHAT_ID,
         f"🤖 Bot đã khởi động!\n"
         f"🌅 Báo cáo sáng tự động lúc <b>{REPORT_HOUR:02d}:{REPORT_MINUTE:02d}</b>\n"
         f"Gõ /start để xem hướng dẫn")

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
