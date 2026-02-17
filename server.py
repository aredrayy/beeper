import time
import threading
import requests
from flask import Flask, request
import sys
import json
from unidecode import unidecode

BEEPER_API_URL = "http://localhost:23373/v1"
ACCESS_TOKEN = ""

# --- GLOBALS ---
CURRENT_CHAT_ID = None
message_buffer = []
headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
app = Flask(__name__)

def log(text):
    print(text)
    sys.stdout.flush()

def clean_for_nokia(text):
    if not text: return ""
    try:
        # Converts emojis/unicode to ASCII safe for N95
        return unidecode(text)
    except:
        return "?"

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
        url = f"{BEEPER_API_URL}/chats?limit=20"
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            clean_list = []
            for c in resp.json()['items']:
                raw_name = get_smart_name(c)
                name = clean_for_nokia(raw_name)
                unread = c.get('unreadCount', 0)
                if unread > 0: name = "* " + name
                net = clean_for_nokia(c.get('network', 'Beeper'))
                clean_list.append((name, c['id'], net))
            return json.dumps(clean_list, ensure_ascii=True)
        else:
            log(f"API Error {resp.status_code}: {resp.text}")
    except Exception as e:
        log(f"List Error: {e}")
    return "[]"

# --- FIX 1: Allow GET requests so the N95 can switch chats ---
@app.route('/select_chat', methods=['GET', 'POST'])
def select_chat():
    global CURRENT_CHAT_ID, message_buffer
    
    # Check both URL params (GET) and Form data (POST)
    new_id = request.values.get('id')
    
    if new_id:
        CURRENT_CHAT_ID = new_id
        message_buffer = [] 
        log(f"Switching to: {new_id}")
        
        try:
            # Fetch history immediately
            url = f"{BEEPER_API_URL}/chats/{CURRENT_CHAT_ID}/messages?limit=20"
            resp = requests.get(url, headers=headers)
            if resp.status_code == 200:
                messages = resp.json()['items']
                for m in reversed(messages):
                    sender = clean_for_nokia(m.get('senderName', 'Unknown'))
                    body = clean_for_nokia(m.get('text', '[Media]'))
                    msg_id = m.get('id', f"hist_{time.time()}")
                    message_buffer.append({'id': msg_id, 'sender': sender, 'msg': body})
            else:
                log(f"Select Chat API Error: {resp.status_code}")
        except Exception as e:
            log(f"Select Error: {e}")
            pass
            
        return "OK"
    return "Missing ID", 400

@app.route('/get_messages', methods=['GET'])
def get_messages():
    return json.dumps(message_buffer, ensure_ascii=True)

# --- FIX 2: Allow GET requests so the N95 can send messages ---
@app.route('/send', methods=['GET', 'POST'])
def send_message():
    # Check both URL params (GET) and Form data (POST)
    msg = request.values.get('msg')
    
    if msg and CURRENT_CHAT_ID:
        log(f"N95 sending: {msg}")
        try:
            url = f"{BEEPER_API_URL}/chats/{CURRENT_CHAT_ID}/messages"
            requests.post(url, json={"text": msg}, headers=headers)
            
            fake_id = f"me_{time.time()}"
            message_buffer.append({'id': fake_id, 'sender': 'Me', 'msg': msg})
            
            if len(message_buffer) > 50: message_buffer.pop(0)
            return "OK"
        except Exception as e:
            log(f"Error sending: {e}")
            return str(e), 500
    return "Missing Data", 400

def poll_beeper():
    last_message_id = None
    log("Bridge Active... Listening for new messages...")
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
                                message_buffer.append({'id': mid, 'sender': sender, 'msg': body})
                                if len(message_buffer) > 50: message_buffer.pop(0)
                        last_message_id = mid
            except Exception:
                pass
        time.sleep(2)

if __name__ == '__main__':
    t = threading.Thread(target=poll_beeper)
    t.daemon = True
    t.start()
    app.run(host='0.0.0.0', port=8080)