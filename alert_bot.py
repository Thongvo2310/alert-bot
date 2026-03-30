import requests
import time
import threading
import json
import os
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN", "TOKEN_CUA_BAN")
CHAT_ID   = os.environ.get("CHAT_ID",   "CHAT_ID_CUA_BAN")

ALERTS_FILE       = "alerts.json"
USDTD_ALERTS_FILE = "usdtd_alerts.json"

REPORT_HOUR   = 9
REPORT_MINUTE = 0

def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

alerts          = load_json(ALERTS_FILE)
usdtd_alerts    = load_json(USDTD_ALERTS_FILE)
triggered       = set()
usdtd_triggered = set()
user_state      = {}

def safe_json(res):
    try:
        if res.status_code == 429:
            print("rate-limit 429, chờ 15s...")
            time.sleep(15)
            return None
        if res.status_code != 200:
            print(f"HTTP {res.status_code}: {res.text[:80]}")
            return None
        text = res.text.strip()
        if not text:
            return None
        return res.json()
    except Exception as e:
        print(f"JSON parse error: {e}")
        return None

CG_IDS = {"BTCUSDT": "bitcoin", "ETHUSDT": "ethereum"}

def get_price_binance(symbol):
    """Lấy giá từ Binance Spot. Fallback: CoinGecko nếu Binance bị block."""
    sym = symbol.upper()

    # 1. Binance Spot (real-time nhất)
    try:
        res  = requests.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            params={"symbol": sym},
            timeout=8
        )
        data = safe_json(res)
        if data and "lastPrice" in data:
            return float(data["lastPrice"]), float(data.get("priceChangePercent", 0))
    except Exception as e:
        print(f"Binance error ({sym}): {e}")

    # 2. CoinGecko fallback
    cg_id = CG_IDS.get(sym)
    if cg_id:
        try:
            res  = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": cg_id, "vs_currencies": "usd", "include_24hr_change": "true"},
                timeout=10
            )
            data = safe_json(res)
            if data and cg_id in data:
                price  = float(data[cg_id]["usd"])
                change = float(data[cg_id].get("usd_24h_change", 0))
                print(f"CoinGecko fallback OK: {sym} = {price}")
                return price, change
        except Exception as e:
            print(f"CoinGecko fallback error ({sym}): {e}")

    return None, None

def get_usdt_dominance():
    """Tính USDT.D từ nhiều nguồn, ưu tiên nguồn gần với TradingView nhất."""

    # 1. CoinLore - cập nhật thường xuyên hơn CoinGecko, không cần key
    try:
        # Lấy tổng market cap global
        res_g = requests.get("https://api.coinlore.net/api/global/", timeout=8)
        data_g = safe_json(res_g)
        # Lấy market cap của USDT (id=518 trên CoinLore)
        res_u = requests.get("https://api.coinlore.net/api/ticker/?id=518", timeout=8)
        data_u = safe_json(res_u)
        if data_g and data_u and isinstance(data_g, list) and isinstance(data_u, list):
            total_mcap  = float(data_g[0].get("total_mcap", 0))
            usdt_mcap   = float(data_u[0].get("market_cap_usd", 0))
            if total_mcap > 0 and usdt_mcap > 0:
                dom = round((usdt_mcap / total_mcap) * 100, 2)
                print(f"USDT.D from CoinLore: {dom}% (usdt={usdt_mcap/1e9:.1f}B / total={total_mcap/1e9:.0f}B)")
                return dom, total_mcap
    except Exception as e:
        print(f"CoinLore error: {e}")

    # 2. CoinGecko fallback
    try:
        res  = requests.get("https://api.coingecko.com/api/v3/global", timeout=10)
        data = safe_json(res)
        if data:
            dom        = data["data"]["market_cap_percentage"].get("usdt", 0)
            total_mcap = data["data"]["total_market_cap"].get("usd", 0)
            print(f"USDT.D from CoinGecko fallback: {dom}%")
            return round(dom, 2), total_mcap
    except Exception as e:
        print(f"CoinGecko error: {e}")

    return None, None

def chart_link(symbol):
    base = symbol.replace("USDT", "")
    return f"https://www.tradingview.com/chart/?symbol=BINANCE:{base}USDT"

MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "₿ BTC"}, {"text": "Ξ ETH"}, {"text": "💵 USDT.D"}],
        [{"text": "🔔 Alert BTC"}, {"text": "🔔 Alert ETH"}, {"text": "🎯 Alert USDT.D"}],
        [{"text": "📋 Danh sách Alert"}, {"text": "🗑 Xoá Alert"}],
        [{"text": "📊 Báo cáo thị trường"}],
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
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram send error: {e}")

def get_updates(offset=None):
    url    = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 10}
    if offset:
        params["offset"] = offset
    res = requests.get(url, params=params, timeout=15)
    return res.json().get("result", [])

def send_price_info(chat_id, symbol):
    price, change = get_price_binance(symbol)
    if price is None:
        send(chat_id, f"❌ Lỗi lấy giá <b>{symbol}</b>, thử lại sau!")
        return
    emoji = "📈" if change >= 0 else "📉"
    sign  = "+" if change >= 0 else ""
    name  = symbol.replace("USDT", "")
    link  = chart_link(symbol)
    send(chat_id,
         f"{emoji} <b>{name}/USDT</b>\n"
         f"Giá: <b>${price:,.2f}</b>\n"
         f"24h: {sign}{change:.2f}%\n"
         f"📊 <a href='{link}'>Xem chart TradingView</a>")

def send_usdt_dominance(chat_id):
    send(chat_id, "⏳ Đang lấy dữ liệu USDT Dominance...")
    dom, total_mcap = get_usdt_dominance()
    if dom is None:
        send(chat_id, "❌ Lỗi lấy USDT Dominance! Thử lại sau.")
        return
    total_str = f"${total_mcap/1e12:.2f}T" if total_mcap else "N/A"
    send(chat_id,
         f"💵 <b>USDT Dominance</b>\n"
         f"Dominance: <b>{dom}%</b>\n"
         f"Tổng Market Cap: {total_str}\n\n"
         f"📊 <a href='https://www.tradingview.com/chart/?symbol=CRYPTOCAP:USDT.D'>Xem chart USDT.D</a>")

def send_morning_report():
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    msg = f"🌅 <b>Báo cáo thị trường {now}</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n\n"

    btc_sym = "BTCUSDT"
    btc_price, btc_change = get_price_binance(btc_sym)
    if btc_price:
        emoji = "📈" if btc_change >= 0 else "📉"
        sign  = "+" if btc_change >= 0 else ""
        msg  += f"{emoji} <b><a href='{chart_link(btc_sym)}'>BTC</a></b>: ${btc_price:,.2f}  {sign}{btc_change:.2f}%\n\n"
    else:
        msg += "⚠️ BTC: Lỗi lấy dữ liệu\n\n"

    eth_sym = "ETHUSDT"
    eth_price, eth_change = get_price_binance(eth_sym)
    if eth_price:
        emoji = "📈" if eth_change >= 0 else "📉"
        sign  = "+" if eth_change >= 0 else ""
        msg  += f"{emoji} <b><a href='{chart_link(eth_sym)}'>ETH</a></b>: ${eth_price:,.2f}  {sign}{eth_change:.2f}%\n\n"
    else:
        msg += "⚠️ ETH: Lỗi lấy dữ liệu\n\n"

    dom, total_mcap = get_usdt_dominance()
    if dom:
        total_str = f"${total_mcap/1e12:.2f}T" if total_mcap else ""
        msg += (f"💵 <b><a href='https://www.tradingview.com/chart/?symbol=CRYPTOCAP:USDT.D'>USDT.D</a></b>: {dom}%"
                f"   | Total MCap: {total_str}\n\n")
    else:
        msg += "⚠️ USDT.D: Lỗi lấy dữ liệu\n\n"

    msg += "━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"🔔 Alerts: <b>{len(alerts)} coin + {len(usdtd_alerts)} USDT.D</b>\n"
    msg += "Chúc bạn trading vui! 🚀"
    send(CHAT_ID, msg)
    print(f"Đã gửi báo cáo lúc {now}")

def morning_report_checker():
    sent_today = None
    while True:
        now   = datetime.now()
        today = now.date()
        if now.hour == REPORT_HOUR and now.minute == REPORT_MINUTE and sent_today != today:
            send_morning_report()
            sent_today = today
        time.sleep(30)

def handle_message(chat_id, text):
    text  = text.strip()
    state = user_state.get(chat_id, {})

    if text == "/start":
        send(chat_id,
             "👋 <b>Chào mừng đến Alert Bot!</b>\n\n"
             "• <b>₿ BTC / Ξ ETH</b> — Xem giá ngay\n"
             "• <b>💵 USDT.D</b> — Xem USDT Dominance\n"
             "• <b>🔔 Alert BTC/ETH</b> — Đặt alert giá\n"
             "• <b>🎯 Alert USDT.D</b> — Alert theo dominance\n"
             "• <b>📋 Danh sách / 🗑 Xoá</b> — Quản lý alert\n"
             "• <b>📊 Báo cáo</b> — Thị trường tổng quan",
             reply_markup=MAIN_KEYBOARD)
        user_state[chat_id] = {}
        return

    if text == "₿ BTC" or text.lower() in ["btc", "bitcoin"]:
        send_price_info(chat_id, "BTCUSDT")
        return
    if text == "Ξ ETH" or text.lower() in ["eth", "ethereum"]:
        send_price_info(chat_id, "ETHUSDT")
        return
    if text == "💵 USDT.D" or text.lower() in ["/usdtd", "usdt.d", "usdtd"]:
        send_usdt_dominance(chat_id)
        return
    if text == "📊 Báo cáo thị trường" or text == "/report":
        send(chat_id, "⏳ Đang lấy dữ liệu...")
        send_morning_report()
        return

    if text in ["🔔 Alert BTC", "🔔 Alert ETH"]:
        symbol = "BTCUSDT" if "BTC" in text else "ETHUSDT"
        price, _ = get_price_binance(symbol)
        price_str = f" (hiện tại: ${price:,.2f})" if price else ""
        user_state[chat_id] = {"step": "wait_price", "symbol": symbol}
        send(chat_id, f"💰 Alert <b>{symbol}</b>{price_str}\n\nNhập mức giá (USD):\nVí dụ: <b>90000</b>")
        return

    if text == "🎯 Alert USDT.D":
        dom, _ = get_usdt_dominance()
        dom_str = f" (hiện tại: {dom}%)" if dom else ""
        user_state[chat_id] = {"step": "usdtd_wait_value"}
        send(chat_id, f"🎯 <b>Alert USDT.D</b>{dom_str}\n\nNhập ngưỡng %:\nVí dụ: <b>5.5</b>")
        return

    if text == "📋 Danh sách Alert":
        text = "/list"
    if text == "🗑 Xoá Alert":
        text = "/delete"

    if text == "/list":
        if not alerts and not usdtd_alerts:
            send(chat_id, "📭 Chưa có alert nào!", reply_markup=MAIN_KEYBOARD)
            return
        msg = "📋 <b>Danh sách alert:</b>\n\n"
        for i, a in enumerate(alerts):
            emoji = "📈" if a["condition"] == "above" else "📉"
            msg  += f"{i+1}. {emoji} {a['symbol']} {a['condition'].upper()} ${a['price']:,.2f}\n"
        if usdtd_alerts:
            msg += "\n<b>USDT.D alerts:</b>\n"
            for i, a in enumerate(usdtd_alerts):
                emoji = "📈" if a["condition"] == "above" else "📉"
                msg  += f"D{i+1}. {emoji} USDT.D {a['condition'].upper()} {a['value']}%\n"
        msg += "\n<i>Xoá coin: 🗑 Xoá Alert\nXoá USDT.D: /delusdtd [số]</i>"
        send(chat_id, msg, reply_markup=MAIN_KEYBOARD)
        return

    if text == "/delete":
        if not alerts:
            send(chat_id, "📭 Không có coin alert nào!", reply_markup=MAIN_KEYBOARD)
            return
        msg = "🗑 <b>Nhập số thứ tự muốn xoá:</b>\n\n"
        for i, a in enumerate(alerts):
            emoji = "📈" if a["condition"] == "above" else "📉"
            msg  += f"{i+1}. {emoji} {a['symbol']} {a['condition'].upper()} ${a['price']:,.2f}\n"
        send(chat_id, msg)
        user_state[chat_id] = {"step": "delete"}
        return

    if text.lower().startswith("/delusdtd"):
        parts = text.split()
        if len(parts) < 2:
            if not usdtd_alerts:
                send(chat_id, "📭 Không có USDT.D alert nào!", reply_markup=MAIN_KEYBOARD)
                return
            msg = "🗑 <b>USDT.D alerts (gõ /delusdtd [số] để xoá):</b>\n\n"
            for i, a in enumerate(usdtd_alerts):
                emoji = "📈" if a["condition"] == "above" else "📉"
                msg  += f"{i+1}. {emoji} USDT.D {a['condition'].upper()} {a['value']}%\n"
            send(chat_id, msg)
            return
        try:
            idx = int(parts[1]) - 1
            if 0 <= idx < len(usdtd_alerts):
                removed = usdtd_alerts.pop(idx)
                save_json(USDTD_ALERTS_FILE, usdtd_alerts)
                send(chat_id, f"✅ Đã xoá: USDT.D {removed['condition'].upper()} {removed['value']}%",
                     reply_markup=MAIN_KEYBOARD)
            else:
                send(chat_id, "❌ Số không hợp lệ!")
        except:
            send(chat_id, "❌ Vui lòng nhập số!")
        return

    # Conversation steps
    if state.get("step") == "delete":
        try:
            idx = int(text) - 1
            if 0 <= idx < len(alerts):
                removed = alerts.pop(idx)
                save_json(ALERTS_FILE, alerts)
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
            symbol = state.get("symbol", "")
            send(chat_id,
                 f"📊 Giá: <b>${price:,.2f}</b>\n\nBáo khi <b>{symbol}</b>:",
                 reply_markup={"inline_keyboard": [[
                     {"text": "📈 Above (vượt lên)", "callback_data": "cond_above"},
                     {"text": "📉 Below (rớt xuống)", "callback_data": "cond_below"}
                 ]]})
        except:
            send(chat_id, "❌ Vui lòng nhập số hợp lệ! Ví dụ: 90000")
        return

    send(chat_id, "💡 Gõ /start hoặc dùng nút bên dưới!", reply_markup=MAIN_KEYBOARD)

def handle_callback(chat_id, callback_id, data):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
                  json={"callback_query_id": callback_id})
    state = user_state.get(chat_id, {})

    if data.startswith("usdtd_"):
        parts     = data.split("_")
        condition = parts[1]
        value     = float(parts[2])
        usdtd_alerts.append({"condition": condition, "value": value})
        save_json(USDTD_ALERTS_FILE, usdtd_alerts)
        emoji = "📈" if condition == "above" else "📉"
        send(chat_id,
             f"{emoji} <b>USDT.D Alert đã đặt!</b>\n\n"
             f"Báo khi USDT.D <b>{condition.upper()} {value}%</b>\n\n"
             f"Xoá: /delusdtd 1\n"
             f"📊 <a href='https://www.tradingview.com/chart/?symbol=CRYPTOCAP:USDT.D'>Xem chart USDT.D</a>",
             reply_markup=MAIN_KEYBOARD)
        user_state[chat_id] = {}
        return

    if data.startswith("cond_"):
        condition = data.replace("cond_", "")
        symbol    = state.get("symbol")
        price     = state.get("price")
        if symbol and price:
            alerts.append({"symbol": symbol, "condition": condition, "price": price})
            save_json(ALERTS_FILE, alerts)
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

def price_checker():
    while True:
        for alert in alerts[:]:
            key = f"{alert['symbol']}_{alert['condition']}_{alert['price']}"
            try:
                price, _ = get_price_binance(alert["symbol"])
                if price is None:
                    continue
                hit = (alert["condition"] == "above" and price >= alert["price"]) or \
                      (alert["condition"] == "below" and price <= alert["price"])
                if hit and key not in triggered:
                    emoji = "📈" if alert["condition"] == "above" else "📉"
                    name  = alert["symbol"].replace("USDT", "")
                    link  = chart_link(alert["symbol"])
                    send(CHAT_ID,
                         f"🚨 <b>ALERT TRIGGERED!</b>\n\n"
                         f"{emoji} <b>{name}/USDT</b>\n"
                         f"Giá hiện tại: <b>${price:,.2f}</b>\n"
                         f"Điều kiện: {alert['condition'].upper()} ${alert['price']:,.2f}\n\n"
                         f"📊 <a href='{link}'>Xem chart TradingView</a>")
                    triggered.add(key)
                    print(f"Alert: {key} triggered")
                elif not hit and key in triggered:
                    triggered.discard(key)
            except Exception as e:
                print(f"price check error: {e}")

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
                                 f"{emoji} USDT.D hiện tại: <b>{dom}%</b>\n"
                                 f"Điều kiện: {a['condition'].upper()} {a['value']}%\n\n"
                                 f"💡 Xem xét lại vị thế BTC!\n"
                                 f"📊 <a href='https://www.tradingview.com/chart/?symbol=CRYPTOCAP:USDT.D'>Xem chart USDT.D</a>")
                            usdtd_triggered.add(key)
                        elif not hit and key in usdtd_triggered:
                            usdtd_triggered.discard(key)
            except Exception as e:
                print(f"usdtd check error: {e}")

        time.sleep(30)

def main():
    print(f"Bot chạy... báo cáo lúc {REPORT_HOUR:02d}:{REPORT_MINUTE:02d}")
    send(CHAT_ID,
         f"🤖 <b>Bot đã khởi động!</b>\n"
         f"📡 BTC/ETH: Binance real-time\n"
         f"💵 USDT.D: CoinGecko\n"
         f"🌅 Báo cáo sáng: <b>{REPORT_HOUR:02d}:{REPORT_MINUTE:02d}</b>\n"
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
            print(f"main loop error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
