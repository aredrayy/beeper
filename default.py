import appuifw
import e32
import sys
import btsocket
import socket 
import random
import urllib 

# --- CONFIGURATION ---
# Your PERMANENT Serveo Address
SERVER_HOST = "192.168.1.7"
SERVER_PORT = 8080

# Global Variables
apo = None
server_ip = None 
ui_lock = e32.Ao_lock()
timer = e32.Ao_timer()
seen_ids = []
view_mode = 'list'
loop_counter = 0
chat_data_list = [] 

def safe_u(s):
    try:
        if isinstance(s, unicode): return s
        return str(s).decode('utf-8', 'ignore')
    except:
        return u"?"

# --- NETWORK SETUP ---
def connect_network():
    global apo, server_ip
    try:
        if apo is None:
            # 1. Ask user to pick the Access Point (Select Digi Web!)
            apid = btsocket.select_access_point()
            apo = btsocket.access_point(apid)
            btsocket.set_default_access_point(apo)
            apo.start()
            
            appuifw.note(u"Resolving DNS...", "conf")
            
            # 2. Resolve the Serveo address to an IP
            try:
                server_ip = socket.gethostbyname(SERVER_HOST)
                # Show IP for debugging (Optional, but good for confidence)
                # appuifw.note(u"IP: " + str(server_ip), "conf")
            except Exception, e:
                appuifw.note(u"DNS Failed: " + str(e), "error")
                return False
        return True
    except Exception, e:
        appuifw.note(u"Setup Err: " + str(e), "error")
        return False

# --- RAW HTTP ENGINE ---
def raw_http_get(path):
    global server_ip
    
    # Ensure we are connected
    if apo is None or server_ip is None:
        if not connect_network(): return None

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(30) # Generous timeout for 3G
        
        # Connect to the IP we resolved earlier
        s.connect((server_ip, SERVER_PORT))
        
        # Standard HTTP Request
        request = "GET " + path + " HTTP/1.1\r\n"
        request += "Host: " + SERVER_HOST + "\r\n"
        request += "User-Agent: NokiaN95\r\n"
        request += "Connection: close\r\n\r\n"
        
        s.sendall(request)
        
        # Read the response
        response = ""
        while True:
            chunk = s.recv(4096)
            if not chunk: break
            response += chunk
        s.close()
        
        # Split Headers from Body
        parts = response.split('\r\n\r\n', 1)
        if len(parts) > 1:
            return parts[1]
        else:
            return None
    except Exception, e:
        return None

def exit_app():
    timer.cancel()
    try: apo.stop()
    except: pass
    ui_lock.signal()

appuifw.app.exit_key_handler = exit_app
appuifw.app.title = u"Beeper N95"

# --- APP LOGIC ---

def show_chat_list():
    global chat_data_list, view_mode
    view_mode = 'list'
    timer.cancel()
    appuifw.note(u"Loading Chats...", "info")
    
    raw = raw_http_get("/get_chat_list?r=" + str(random.random()))
    
    if raw:
        try:
            # Parse the JSON list
            chat_data_list = eval(raw, {"true":True, "false":False, "null":None})
            ui_list = []
            for c in chat_data_list:
                # Format: Name (Network)
                ui_list.append(u"%s (%s)" % (safe_u(c[0]), safe_u(c[2])))
                
            lb = appuifw.Listbox(ui_list, on_select_chat)
            appuifw.app.body = lb
            appuifw.app.menu = [(u"Refresh", show_chat_list), (u"Exit", exit_app)]
        except:
            appuifw.note(u"JSON Error", "error")
    else:
        appuifw.note(u"Net Error. Retrying...", "error")
        appuifw.app.menu = [(u"Retry", show_chat_list), (u"Exit", exit_app)]

def on_select_chat():
    global view_mode
    try:
        index = appuifw.app.body.current()
        chat_id = chat_data_list[index][1]
        name = safe_u(chat_data_list[index][0])
        
        appuifw.note(u"Entering " + name + "...", "info")
        
        if isinstance(chat_id, unicode): chat_id = chat_id.encode('utf-8')
        
        # Send command to server to switch active chat
        query = "/select_chat?id=" + urllib.quote(chat_id) + "&limit=20"
        result = raw_http_get(query)
        
        # Only open the view if server said OK (prevent ghost clicks)
        if result is not None:
            show_chat_view(name)
        else:
            appuifw.note(u"Connect Failed. Try again.", "error")
    except Exception, e:
        appuifw.note(u"Open Err: " + str(e), "error")

def show_chat_view(name):
    global seen_ids, view_mode, loop_counter
    view_mode = 'chat'
    loop_counter = 0
    seen_ids = [] 
    
    log_box = appuifw.Text()
    appuifw.app.body = log_box
    appuifw.app.title = name
    appuifw.app.menu = [
        (u"Send", send_msg_ui),
        (u"Refresh", force_refresh),
        (u"Back", show_chat_list)
    ]
    fetch_loop()

def force_refresh():
    timer.cancel()
    fetch_loop()

def fetch_loop():
    global seen_ids, loop_counter
    if view_mode != 'chat': return

    loop_counter += 1
    if loop_counter > 5: loop_counter = 0
    
    data = raw_http_get("/get_messages?r=" + str(random.random()))
    
    if data:
        try:
            # Server sends [Old -> New]
            messages = eval(data, {"true":True, "false":False, "null":None})
            
            new_activity = False
            
            for m in messages:
                if 'id' not in m: continue
                msg_id = m['id']
                if msg_id not in seen_ids:
                    seen_ids.append(msg_id)
                    if len(seen_ids) > 100: seen_ids.pop(0)

                    sender = safe_u(m['sender'])
                    txt = safe_u(m['msg'])
                    
                    if sender == u"Me":
                        appuifw.app.body.add(u">> %s\n" % txt)
                    else:
                        appuifw.app.body.add(u"%s: %s\n" % (sender, txt))
                        new_activity = True

            if new_activity:
                e32.ao_yield() 
                appuifw.app.body.set_pos(appuifw.app.body.len())
        except:
            pass
    
    # Poll every 3 seconds
    timer.cancel()
    timer.after(3, fetch_loop)

def send_msg_ui():
    msg = appuifw.query(u"Msg:", "text")
    if msg:
        try:
            safe_msg = urllib.quote(msg.encode('utf-8'))
            query = "/send?msg=" + safe_msg
            raw_http_get(query)
            appuifw.note(u"Sent!", "conf")
            timer.after(1, force_refresh)
        except:
            pass

# --- STARTUP ---
connect_network()
show_chat_list()
ui_lock.wait()