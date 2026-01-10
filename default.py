import appuifw
import e32
import urllib
import sys
import btsocket
import socket
import random

SERVER_URL = "http://10.48.48.202:8080" 

lock = e32.Ao_lock()
timer = e32.Ao_timer()
seen_ids = []  # Tracks IDs, not count
view_mode = 'list'
loop_counter = 0

def safe_u(s):
    try:
        if isinstance(s, unicode): return s
        return str(s).decode('utf-8', 'ignore')
    except:
        return u"?"

try:
    socket.setdefaulttimeout(10)
    apid = btsocket.select_access_point() 
    apo = btsocket.access_point(apid) 
    btsocket.set_default_access_point(apo) 
    apo.start() 
    appuifw.note(u"Online", "conf")
except Exception, e:
    appuifw.note(u"Net: " + str(e), "error")

def exit_app():
    timer.cancel()
    try: apo.stop()
    except: pass
    lock.signal()

appuifw.app.exit_key_handler = exit_app
appuifw.app.title = u"Beeper N95"

# --- VIEW 1: CHAT LIST ---
def show_chat_list():
    global chat_data_list, view_mode
    view_mode = 'list'
    timer.cancel()
    appuifw.note(u"Loading...", "info")
    try:
        rnd = str(random.random())
        f = urllib.urlopen(SERVER_URL + "/get_chat_list?r=" + rnd)
        raw = f.read()
        f.close()
        chat_data_list = eval(raw, {"true":True, "false":False, "null":None})
        ui_list = []
        for c in chat_data_list:
            ui_list.append(u"%s (%s)" % (safe_u(c[0]), safe_u(c[2])))
        lb = appuifw.Listbox(ui_list, on_select_chat)
        appuifw.app.body = lb
        appuifw.app.menu = [(u"Refresh", show_chat_list), (u"Exit", exit_app)]
    except Exception, e:
        appuifw.note(u"List Err: " + str(e), "error")

def on_select_chat():
    try:
        index = appuifw.app.body.current()
        chat_id = chat_data_list[index][1]
        name = safe_u(chat_data_list[index][0])
        params = urllib.urlencode({'id': chat_id})
        urllib.urlopen(SERVER_URL + "/select_chat", params).close()
        show_chat_view(name)
    except: pass

# --- VIEW 2: CONVERSATION ---
def show_chat_view(name):
    global seen_ids, view_mode, loop_counter
    view_mode = 'chat'
    loop_counter = 0
    seen_ids = [] # Clear history so we load fresh
    
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
    if loop_counter > 9: loop_counter = 0
    appuifw.app.title = u"Chat %s" % ("." * loop_counter)

    try:
        rnd = str(random.random())
        url = SERVER_URL + "/get_messages?r=" + rnd
        f = urllib.urlopen(url)
        data = f.read()
        f.close()
        
        messages = eval(data, {"true":True, "false":False, "null":None})
        
        new_activity = False
        
        for m in messages:
            # SAFETY: Ensure ID exists
            if 'id' not in m: continue
            
            msg_id = m['id']
            if msg_id not in seen_ids:
                seen_ids.append(msg_id)
                # Keep memory usage low
                if len(seen_ids) > 60: seen_ids.pop(0)

                sender = safe_u(m['sender'])
                txt = safe_u(m['msg'])
                
                if sender == u"Me":
                    appuifw.app.body.add(u">> %s\n" % txt)
                else:
                    appuifw.app.body.add(u"%s: %s\n" % (sender, txt))
                    new_activity = True

        if new_activity:
            appuifw.note(u"New Msg", "info") # Beep
            appuifw.app.body.set_pos(appuifw.app.body.len()) # Scroll

    except:
        pass
    
    finally:
        timer.cancel()
        timer.after(4, fetch_loop)

def send_msg_ui():
    msg = appuifw.query(u"Msg:", "text")
    if msg:
        try:
            params = urllib.urlencode({'msg': msg.encode('utf-8')})
            urllib.urlopen(SERVER_URL + "/send", params).close()
            # We don't manually add it here anymore, 
            # we let the fetch_loop pick it up from the server in 2 seconds
        except:
            appuifw.note(u"Send Err", "error")

show_chat_list()
lock.wait()