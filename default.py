import appuifw
import e32
import urllib
import sys
import btsocket
import socket

SERVER_URL = "http://192.168.1.7:8080" 

lock = e32.Ao_lock()
timer = e32.Ao_timer()
current_messages_count = 0
chat_data_list = []
# 'list' or 'chat' - Used to prevent running code on wrong screen
view_mode = 'list' 

# --- ROBUST DECODER ---
# Fixes "ascii codec can't decode"
def safe_u(s):
    try:
        # If it's already unicode (PyS60 JSON parser does this), return it
        if isinstance(s, unicode):
            return s
        # If it's standard string bytes, decode utf-8
        return str(s).decode('utf-8', 'ignore')
    except:
        return u"???"

# --- CONNECTION ---
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
        f = urllib.urlopen(SERVER_URL + "/get_chat_list")
        raw = f.read()
        f.close()
        
        chat_data_list = eval(raw)
        
        ui_list = []
        for c in chat_data_list:
            # c = [Name, ID, Network]
            name = safe_u(c[0])
            net = safe_u(c[2])
            ui_list.append(u"%s (%s)" % (name, net))
            
        lb = appuifw.Listbox(ui_list, on_select_chat)
        appuifw.app.body = lb
        appuifw.app.menu = [(u"Refresh List", show_chat_list), (u"Exit", exit_app)]
        
    except Exception, e:
        appuifw.note(u"List Err: " + str(e), "error")

def on_select_chat():
    try:
        index = appuifw.app.body.current()
        chat_name = safe_u(chat_data_list[index][0])
        chat_id = chat_data_list[index][1]
        
        appuifw.note(u"Opening...", "info")
        
        # Tell PC to switch
        params = urllib.urlencode({'id': chat_id})
        urllib.urlopen(SERVER_URL + "/select_chat", params).close()
        
        show_chat_view(chat_name)
    except Exception, e:
        appuifw.note(u"Select Err: " + str(e), "error")

# --- VIEW 2: CONVERSATION ---
def show_chat_view(name):
    global current_messages_count, view_mode
    view_mode = 'chat'
    
    # Reset count so we load the history that the server just prepared
    current_messages_count = 0
    
    log_box = appuifw.Text()
    appuifw.app.body = log_box
    appuifw.app.title = name
    
    appuifw.app.menu = [
        (u"Send", send_msg_ui),
        (u"Back", show_chat_list),
        (u"Exit", exit_app)
    ]
    
    # Start loop
    fetch_loop()

def fetch_loop():
    global current_messages_count
    
    # SAFEGUARD: Only run if we are actually looking at the chat
    if view_mode == 'chat':
        try:
            f = urllib.urlopen(SERVER_URL + "/get_messages")
            data = f.read()
            f.close()
            
            messages = eval(data)
            total = len(messages)
            
            if total > current_messages_count:
                new_items = messages[current_messages_count:]
                for m in new_items:
                    sender = safe_u(m['sender'])
                    txt = safe_u(m['msg'])
                    appuifw.app.body.add(u"<%s> %s\n" % (sender, txt))
                
                current_messages_count = total
        except:
            pass
        
        # Keep looping
        timer.after(2, fetch_loop)

def send_msg_ui():
    msg = appuifw.query(u"Msg:", "text")
    if msg:
        try:
            params = urllib.urlencode({'msg': msg.encode('utf-8')})
            urllib.urlopen(SERVER_URL + "/send", params).close()
        except:
            appuifw.note(u"Send Failed", "error")

show_chat_list()
lock.wait()