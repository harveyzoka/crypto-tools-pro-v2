import argparse, time
import ccxt
import requests

def telegram_send(token, chat_id, text):
    if not token or not chat_id:
        return False, "token/chat_id missing"
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id, "text": text}, timeout=10)
        return r.ok, r.text
    except Exception as e:
        return False, str(e)

def current_price(exchange, symbol):
    ex = getattr(ccxt, exchange)()
    ticker = ex.fetch_ticker(symbol)
    return float(ticker["last"])

def main():
    p = argparse.ArgumentParser(description="Simple price alert with optional Telegram push")
    p.add_argument("--exchange", default="binance", help="binance | bybit | ...")
    p.add_argument("--symbol", default="BTC/USDT", help="e.g., BTC/USDT")
    p.add_argument("--upper", type=float, default=None, help="Alert when price >= upper")
    p.add_argument("--lower", type=float, default=None, help="Alert when price <= lower")
    p.add_argument("--interval", type=int, default=5, help="Poll seconds")
    p.add_argument("--telegram_token", default=None)
    p.add_argument("--telegram_chat_id", default=None)
    args = p.parse_args()

    print(f"Watching {args.exchange} {args.symbol} (every {args.interval}s)")
    print(f"UPPER={args.upper} LOWER={args.lower}")
    last_state = None
    while True:
        try:
            px = current_price(args.exchange, args.symbol)
            state = "mid"
            if args.upper is not None and px >= args.upper: state = "high"
            if args.lower is not None and px <= args.lower: state = "low"
            if state != last_state:
                msg = f"{args.symbol} price={px:.4f} crossed into {state.upper()}"
                print("[ALERT]", msg)
                if args.telegram_token and args.telegram_chat_id and state in ("high","low"):
                    ok, resp = telegram_send(args.telegram_token, args.telegram_chat_id, msg)
                    print("Telegram:", "OK" if ok else resp[:120])
                last_state = state
            time.sleep(args.interval)
        except Exception as e:
            print("Error:", e)
            time.sleep(max(2, args.interval))

if __name__ == "__main__":
    main()
