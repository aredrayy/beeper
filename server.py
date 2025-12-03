import time
import threading
import requests
from flask import Flask, request
import sys
import json
import unicodedata

# --- CONFIGURATION ---
BEEPER_API_URL = "http://localhost:23373/v1"
ACCESS_TOKEN = "5cb7de18-8cba-483e-84a6-39036952260e"

# --- GLOBALS ---
CURRENT_CHAT_ID = None
message_buffer = []
headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
app = Flask(__name__)

def log(text):
    print(text)
    sys.stdout.flush()

# --- TEXT CLEANER ---
def clean_for_nokia(text):
    if not text: return ""
    normalized = unicodedata.normalize('NFKC', text)
    cleaned = "".join(c for c in normalized if ord(c) <= 0xFFFF)
    return cleaned

def get_smart_name(chat_obj):
    title = chat_obj.get('title')
    if not title or "@" in title:
        parts = chat_obj.get('participants', {}).get('items', [])
        for p in parts:
            if not p.get('isSelf'):
                return p.get('fullName', p.get('username'))
    return title if title else "Unknown"

# --- FLASK ENDPOINTS ---

@app.route('/get_chat_list', methods=['GET'])
def get_chat_list():
    try:
        # Get top 20 recent chats
        url = f"{BEEPER_API_URL}/chats?limit=20"
        resp = requests.get(url, headers=headers)
        
        if resp.status_code == 200:
            clean_list = []
            for c in resp.json()['items']:
                # 1. Get Name
                raw_name = get_smart_name(c)
                name = clean_for_nokia(raw_name)
                
                # 2. Check Unread Count
                # The API provides 'unreadCount' as an integer
                unread = c.get('unreadCount', 0)
                if unread > 0:
                    name = "* " + name  # Add star if unread
                
                # 3. Get Network
                net = clean_for_nokia(c.get('network', 'Beeper'))
                
                clean_list.append((name, c['id'], net))
                
            return json.dumps(clean_list, ensure_ascii=True)
    except Exception as e:
        log(f"List Error: {e}")
    return "[]"

@app.route('/select_chat', methods=['POST'])
def select_chat():
    global CURRENT_CHAT_ID, message_buffer
    new_id = request.form.get('id')
    if new_id:
        CURRENT_CHAT_ID = new_id
        message_buffer = [] 
        log(f"Switching to: {new_id}")
        
        # INSTANT LOAD
        try:
            url = f"{BEEPER_API_URL}/chats/{CURRENT_CHAT_ID}/messages?limit=10"
            resp = requests.get(url, headers=headers)
            if resp.status_code == 200:
                messages = resp.json()['items']
                for m in reversed(messages):
                    sender = clean_for_nokia(m.get('senderName', 'Unknown'))
                    body = clean_for_nokia(m.get('text', '[Media]'))
                    message_buffer.append({'sender': sender, 'msg': body})
        except:
            pass
            
    return "OK"

@app.route('/get_messages', methods=['GET'])
def get_messages():
    return json.dumps(message_buffer, ensure_ascii=True)

@app.route('/send', methods=['POST'])
def send_message():
    msg = request.form.get('msg')
    if msg and CURRENT_CHAT_ID:
        log(f"N95 sending: {msg}")
        try:
            url = f"{BEEPER_API_URL}/chats/{CURRENT_CHAT_ID}/messages"
            requests.post(url, json={"text": msg}, headers=headers)
            message_buffer.append({'sender': 'Me', 'msg': msg})
            if len(message_buffer) > 20: message_buffer.pop(0)
        except Exception as e:
            log(f"Error sending: {e}")
    return "OK"

# --- POLLER ---
def poll_beeper():
    last_message_id = None
    log("Bridge Active...")
    
    while True:
        if CURRENT_CHAT_ID:
            try:
                url = f"{BEEPER_API_URL}/chats/{CURRENT_CHAT_ID}/messages?limit=5"
                resp = requests.get(url, headers=headers)
                
                if resp.status_code == 200:
                    messages = resp.json()['items']
                    if messages:
                        newest = messages[0]
                        mid = newest['id']
                        
                        if last_message_id != mid and last_message_id is not None:
                            sender = clean_for_nokia(newest.get('senderName', 'Unknown'))
                            body = clean_for_nokia(newest.get('text', '[Media]'))
                            
                            if not newest.get('isSender', False):
                                log(f"New ({sender}): {body}")
                                message_buffer.append({'sender': sender, 'msg': body})
                                if len(message_buffer) > 20: message_buffer.pop(0)
                        
                        last_message_id = mid
            except Exception:
                pass
        time.sleep(2)

if __name__ == '__main__':
    t = threading.Thread(target=poll_beeper)
    t.daemon = True
    t.start()
    app.run(host='0.0.0.0', port=8080)