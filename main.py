import asyncio
import csv
import os
import requests
import threading
import http.server
import socketserver
from datetime import datetime
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from playwright.async_api import async_playwright

# --- تشغيل سيرفر وهمي لتلبية شروط Railway ومنع الكراش ---
PORT = int(os.environ.get("PORT", 8080))

class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is active and running 24/7!")

def run_dummy_server():
    with socketserver.TCPServer(("", PORT), HealthCheckHandler) as httpd:
        print(f"🌐 Dummy web server running on port {PORT}")
        httpd.serve_forever()

# إطلاق السيرفر الوهمي في خلفية مستقلة
threading.Thread(target=run_dummy_server, daemon=True).start()

# --- البيانات الأساسية ---
TELEGRAM_TOKEN = "8807749461:AAHy_xwZw6fBSPS_QhmQN-9I96FFaqZglHU"
CHAT_ID = "8178993130"
CSV_FILE = "match_monitoring.csv"

bot = Bot(token=TELEGRAM_TOKEN)
monitored_games = set()
total_logged_rows = 0

# إنشاء ملف CSV وتثبيت العناوين بالإنجليزية إن لم يكن موجوداً
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            "Timestamp", "Date", "Match ID", "Cycle Number", 
            "Start Time", "Team Left (Home)", "Team Right (Away)", 
            "Current Score", "Goal Event / Status", 
            "Team 1 Totals Odds", "Team 2 Totals Odds", "Match Totals Odds"
        ])
else:
    with open(CSV_FILE, mode='r', encoding='utf-8') as f:
        total_logged_rows = sum(1 for row in f) - 1

async def send_status_report(active_games_count, currently_monitoring_count):
    """إرسال تقرير واحد منظم مع زر تفاعلي لتنزيل ملف الـ CSV"""
    global total_logged_rows
    report_message = (
        f"📊 <b>[System Monitoring Report]</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚽ <b>عدد المباريات الآن:</b> {active_games_count}\n"
        f"👁️ <b>جار المراقبة:</b> {currently_monitoring_count}\n"
        f"💾 <b>تم تسجيل البيانات وإرسالها لملف CSV:</b> {total_logged_rows} سجل\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    
    keyboard = [[InlineKeyboardButton("📥 تنزيل ملف البيانات (CSV)", callback_data="download_csv")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await bot.send_message(
            chat_id=CHAT_ID, 
            text=report_message, 
            parse_mode="HTML", 
            reply_markup=reply_markup
        )
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

async def telegram_updates_listener():
    """مستمع في الخلفية لتفقد الضغطات على الأزرار"""
    last_update_id = 0
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"

    while True:
        try:
            params = {"offset": last_update_id + 1, "timeout": 5}
            response = await asyncio.to_thread(requests.get, url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    for update in data.get("result", []):
                        last_update_id = update["update_id"]
                        callback_query = update.get("callback_query")
                        if callback_query:
                            query_id = callback_query.get("id")
                            data_val = callback_query.get("data")
                            
                            if data_val == "download_csv":
                                answer_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
                                await asyncio.to_thread(
                                    requests.post, 
                                    answer_url, 
                                    json={"callback_query_id": query_id, "text": "جاري تحضير وإرسال ملف البيانات..."}
                                )
                                
                                if os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0:
                                    with open(CSV_FILE, 'rb') as f:
                                        await bot.send_document(
                                            chat_id=CHAT_ID, 
                                            document=f, 
                                            caption="📁 <b>ملف بيانات مراقبة المباريات المحدث</b>",
                                            parse_mode="HTML"
                                        )
                                else:
                                    await bot.send_message(
                                        chat_id=CHAT_ID, 
                                        text="⚠️ عذراً، ملف البيانات فارغ أو غير موجود حالياً."
                                    )

        except Exception as e:
            print(f"⚠️ Telegram Updates Error: {e}")

        await asyncio.sleep(2)

async def monitor_single_game(page, game_id: str, opp1: str, opp2: str, cycle_info: str):
    """مراقبة المباراة وتحديث ملف الCSV بصمت في الخلفية"""
    global total_logged_rows
    last_score = "0-0"
    
    while True:
        try:
            game_data = await page.evaluate(f"""
                async () => {{
                    try {{
                        const res = await fetch('/service-api/LiveFeed/GetGameZip?id={game_id}&lng=en');
                        if (res.ok) {{
                            const json = await res.json();
                            return json.Value || json;
                        }}
                    }} catch(e) {{}}
                    return null;
                }}
            """)

            if not game_data:
                monitored_games.discard(game_id)
                break

            scores = game_data.get('SC', {})
            current_score = "0-0"
            if isinstance(scores, dict) and 'FS' in scores:
                current_score = f"{scores.get('FS', {}).get('S1', '0')}-{scores.get('FS', {}).get('S2', '0')}"

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            today_date = datetime.now().strftime("%Y-%m-%d")
            status_note = "Running"

            if current_score != last_score:
                status_note = f"Goal Scored ({current_score})"
                last_score = current_score

            team1_odds, team2_odds, match_totals_odds = {}, {}, {}
            raw_events = game_data.get('GE', []) or game_data.get('E', [])
            events = []
            for item in raw_events:
                if isinstance(item, list): events.extend(item)
                elif isinstance(item, dict): events.append(item)

            for ev in events:
                t_type = ev.get('T')
                val = ev.get('C')
                param = ev.get('P')

                if t_type == 9 and param is not None: match_totals_odds[f'Over {param}'] = val
                elif t_type == 10 and param is not None: match_totals_odds[f'Under {param}'] = val
                elif t_type == 11 and param is not None: team1_odds[f'Over {param}'] = val
                elif t_type == 12 and param is not None: team1_odds[f'Under {param}'] = val
                elif t_type == 13 and param is not None: team2_odds[f'Over {param}'] = val
                elif t_type == 14 and param is not None: team2_odds[f'Under {param}'] = val

            with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    now_str, today_date, game_id, cycle_info,
                    game_data.get('S', 'Live'), opp1, opp2,
                    current_score, status_note,
                    str(team1_odds), str(team2_odds), str(match_totals_odds)
                ])
            total_logged_rows += 1

            await asyncio.sleep(5)

        except Exception as e:
            print(f"⚠️ Error in game {game_id}: {e}")
            await asyncio.sleep(5)

async def main_tracker():
    """الدالة الرئيسية لمسح المباريات وإرسال التقرير الدوري"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox', 
                '--disable-setuid-sandbox', 
                '--disable-dev-shm-usage', 
                '--disable-gpu',
                '--single-process',
                '--no-zygote',
                '--disable-blink-features=AutomationControlled'
            ]
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1366, 'height': 768}
        )
        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        try:
            await page.goto('https://eg-1xbet.com/en/live/cyber', wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(5000)
        except Exception:
            pass

        while True:
            try:
                raw_result = await page.evaluate("""
                    async () => {
                        const possiblePaths = ['/service-api/LiveFeed/Get1x2_VZip', '/LiveFeed/Get1x2_VZip'];
                        for (let path of possiblePaths) {
                            try {
                                let targetUrl = `${path}?sports=85&count=150&lng=en&mode=4`;
                                const res = await fetch(targetUrl);
                                if (res.ok) {
                                    const json = await res.json();
                                    const items = json.Value || json.data || json;
                                    if (Array.isArray(items) && items.length > 0) return items;
                                }
                            } catch(e) {}
                        }
                        return [];
                    }
                """)

                active_matches = []
                for game in raw_result:
                    if not isinstance(game, dict): continue
                    champ_name = str(game.get('L', '') or game.get('LE', '') or '').lower().replace('х', 'x')
                    
                    if ('fc' in champ_name) and ('rush' in champ_name) and ('5x5' in champ_name):
                        active_matches.append(game)
                        gid = str(game.get('I') or game.get('id'))
                        
                        if gid not in monitored_games:
                            monitored_games.add(gid)
                            opp1 = game.get('O1') or game.get('O1E') or "Team Left"
                            opp2 = game.get('O2') or game.get('O2E') or "Team Right"
                            cycle_val = game.get('PN') or game.get('CR') or game.get('R') or "N/A"
                            
                            asyncio.create_task(monitor_single_game(page, gid, opp1, opp2, str(cycle_val)))

                await send_status_report(len(active_matches), len(monitored_games))

            except Exception as e:
                print(f"❌ Loop Error: {e}")

            await asyncio.sleep(30)

async def main():
    await asyncio.gather(
        main_tracker(),
        telegram_updates_listener()
    )

if __name__ == "__main__":
    asyncio.run(main())
