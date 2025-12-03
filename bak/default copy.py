import appuifw
import e32
import urllib
import sys
import btsocket # Required for N95 connection handling
import socket   # Required to set the timeout

# CONFIGURATION
# Replace with your PC's IP address
SERVER_URL = "http://192.168.1.7:8080" 

# UI Setup
lock = e32.Ao_lock()
timer = e32.Ao_timer()
content_list = []

# --- SAFEGUARD 1: CONNECTION SETUP ---
# We force the connection to open BEFORE the app creates its UI.
# This prevents the "Connect?" dialog from getting stuck behind the app.
try:
    # Set a timeout so the phone doesn't freeze if the server is off
    socket.setdefaulttimeout(10)
    
    # 1. Open the selection dialog
    apid = btsocket.select_access_point() 
    
    # 2. Create the access point object
    apo = btsocket.access_point(apid) 
    
    # 3. Set as default for urllib
    btsocket.set_default_access_point(apo) 
    
    # 4. Start the connection.
    # IF YOU ARE IN OFFLINE MODE: The phone will ask 
    # "Allow connection?" right here. Click Yes.
    apo.start() 
    
    appuifw.note(u"WiFi Connected!", "conf")
except Exception, e:
    appuifw.note(u"Conn Error: " + str(e), "error")
# -------------------------------------

def exit_handler():
    timer.cancel()
    # Clean up connection on exit
    try:
        apo.stop()
    except:
        pass
    lock.signal()

appuifw.app.exit_key_handler = exit_handler
appuifw.app.title = u"N95 Matrix"

log_box = appuifw.Text()
appuifw.app.body = log_box

def fetch_messages():
    """Polls the server using the pre-established connection"""
    try:
        f = urllib.urlopen(SERVER_URL + "/get_messages")
        data = f.read()
        f.close()
        
        # Security: Only eval if data exists
        if len(data) > 0:
            messages = eval(data)
            if messages:
                log_box.clear()
                for m in messages:
                    # Format: [Sender]: Message
                    log_box.add(u"[%s]: %s\n" % (m['sender'], m['msg']))
    except Exception, e:
        # If fetch fails, do nothing. Do not freeze the UI with an error popup.
        # We will just try again in 5 seconds.
        pass
    
    # --- SAFEGUARD 2: NON-BLOCKING LOOP ---
    # We schedule the next run in 5 seconds. 
    # This releases the processor so the "Exit" button still works.
    timer.after(5, fetch_messages)

def send_message():
    msg = appuifw.query(u"Message:", "text")
    if msg:
        try:
            params = urllib.urlencode({'msg': msg.encode('utf-8')})
            f = urllib.urlopen(SERVER_URL + "/send", params)
            f.close()
            # Cancel pending timer to avoid double-refresh
            timer.cancel()
            fetch_messages()
        except Exception, e:
            appuifw.note(u"Send Failed", "error")
            # Restart loop if we crashed
            timer.after(5, fetch_messages)

appuifw.app.menu = [
    (u"Send Message", send_message),
    (u"Exit", exit_handler)
]

# Start the first fetch
fetch_messages()

# Enter main loop (Waits for Exit button)
lock.wait()