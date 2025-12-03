import time
import threading
import requests
from flask import Flask, request
import sys

# --- CONFIGURATION ---
BEEPER_API_URL = "http://localhost:23373/v1"
ACCESS_TOKEN = "5cb7de18-8cba-483e-84a6-39036952260e"

# --- GLOBAL VARIABLES ---
# We no longer hardcode the ID. We select it at startup.
CURRENT_CHAT_ID = None 
message_buffer = []
headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
app = Flask(__name__)

# --- HELPER: FORCE PRINT ---
def log(text):
    print(text)
    sys.stdout.flush()

@app.route('/get_messages', methods=['GET'])
def get_messages():
    return str(message_buffer)

@app.route('/send', methods=['POST'])
def send_message():
    msg = request.form.get('msg')
    if msg:
        log(f"N95 sending: {msg}")
        try:
            url = f"{BEEPER_API_URL}/chats/{CURRENT_CHAT_ID}/messages"
            requests.post(url, json={"text": msg}, headers=headers)
            # Add to buffer immediately
            message_buffer.append({'sender': 'Me', 'msg': msg})
            if len(message_buffer) > 20: message_buffer.pop(0)
        except Exception as e:
            log(f"Error sending: {e}")
    return "OK"

# --- INTERACTIVE CHAT PICKER ---
def pick_chat():
    global CURRENT_CHAT_ID
    
    while True:
        print("\n" + "="*40)
        print("      NOKIA N95 CHAT SWITCHER      ")
        print("="*40)
        print("Type a name to search (e.g., 'Andrei')")
        query = input("> ")
        
        if not query: continue
        
        print(f"Searching Beeper for '{query}'...")
        try:
            # Search API
            # Docs: https://developers.beeper.com/desktop-api-reference/resources/chats/methods/search
            search_url = f"{BEEPER_API_URL}/chats/search?query={query}&limit=10"
            results = requests.get(search_url, headers=headers).json()
            items = results.get('items', [])
            
            if not items:
                print("❌ No chats found. Try a different name.")
                continue
                
            print("\n--- RESULTS ---")
            # Create a selection list
            options = []
            for idx, chat in enumerate(items):
                title = chat.get('title')
                # Fallback if title is missing/self
                if not title or "@" in title:
                    parts = chat.get('participants', {}).get('items', [])
                    for p in parts:
                        if not p.get('isSelf'):
                            title = p.get('fullName', p.get('username'))
                            break
                
                # Get the Network (WhatsApp, Telegram, etc.)
                network = chat.get('network', 'Unknown')
                
                print(f"[{idx+1}] {title} ({network})")
                options.append(chat['id'])
                
            print("----------------")
            selection = input("Pick a number (or 'Enter' to search again): ")
            
            if selection.isdigit():
                choice = int(selection) - 1
                if 0 <= choice < len(options):
                    CURRENT_CHAT_ID = options[choice]
                    print(f"\n✅ SELECTED: {items[choice].get('title', 'Chat')}")
                    print(f"   ID: {CURRENT_CHAT_ID}")
                    return # Exit the loop and start the server
            
        except Exception as e:
            print(f"Search Error: {e}")
            print("Is Beeper Desktop running?")
            time.sleep(2)

# --- BACKGROUND POLLER ---
def poll_beeper():
    log("Bridge Active. Waiting for messages...")
    last_message_id = None
    
    # 1. Load initial history
    try:
        url = f"{BEEPER_API_URL}/chats/{CURRENT_CHAT_ID}/messages?limit=5"
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            messages = resp.json()['items']
            for m in reversed(messages):
                mid = m['id']
                sender = m.get('senderName', 'Unknown')
                body = m.get('text', '[Media]')
                message_buffer.append({'sender': sender, 'msg': body})
                last_message_id = mid
    except:
        pass

    # 2. Poll loop
    while True:
        try:
            url = f"{BEEPER_API_URL}/chats/{CURRENT_CHAT_ID}/messages?limit=5"
            resp = requests.get(url, headers=headers)
            
            if resp.status_code == 200:
                messages = resp.json()['items']
                for m in reversed(messages):
                    mid = m['id']
                    if last_message_id != mid:
                        sender = m.get('senderName', 'Unknown')
                        body = m.get('text', '[Media]')
                        
                        if not m.get('isSender', False):
                            log(f"New ({sender}): {body}")
                            message_buffer.append({'sender': sender, 'msg': body})
                            if len(message_buffer) > 20: message_buffer.pop(0)
                        
                        last_message_id = mid
        except Exception:
            pass
        time.sleep(2)

if __name__ == '__main__':
    # 1. Pick the chat FIRST
    pick_chat()
    
    # 2. Then start the bridge
    t = threading.Thread(target=poll_beeper)
    t.daemon = True
    t.start()
    
    print("Starting Nokia Interface on http://192.168.1.7:8080...")
    app.run(host='0.0.0.0', port=8080)