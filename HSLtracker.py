"""
HSLtracker.py (c) Jonne Davidsson
Tracks and displays Helsinki Public Transportation information
based on Points of Interest
Outputs states on a BlinkyTape
RED - alert point - The moment you need to move out to catch the Transportation
YELLOW (blink) - Transport stationary at alert point
MAGENTA (blink) - Number of tracked targets
CYAN (blink) - Transport in PassBy POI a.k.a You didn't make it
License: MIT

Requirements:

pyserial
ipython
https://pypi.python.org/pypi/geopy
https://github.com/Blinkinlabs/BlinkyTape_Python

"""
import sys, time, traceback
from BlinkyTape import BlinkyTape
from datetime import datetime
import requests
from geopy.distance import great_circle

# GLOBAL SETTINGS

# Refresh rates for different situations (s)
refresh_rate_normal = 30
refresh_rate_intensive = 5

# Bounding Box for trackable targets
bbox = { 'llc': (24.9140367, 60.1444105), 'urc': (24.9437070, 60.1666600) }

# Line numbers and trigger data to track
triggers = [ { 'line': "1006", 'direction': "1", 'alert_poi': (24.924765, 60.161483), 'passby_poi': (24.928901, 60.161841) },
             { 'line': "1006T", 'direction': "1", 'alert_poi': (24.924765, 60.161483), 'passby_poi': (24.928901, 60.161841) }]

# Home stop location (Currently not used)
target_location = (24.930020, 60.161904)

# Search radius around POI's
search_radius = 75.0 # meters
# Threshold to update target move state
move_threshold = 15.0 # meters

# GET URL for HSL
url = "http://83.145.232.209:10001/?type=vehicles&lng1=" + str(bbox['llc'][0]) + "&lat1=" + str(bbox['llc'][1]) + "&lng2=" + str(bbox['urc'][0]) +  "&lat2=" + str(bbox['urc'][1])

# BlinkyTape port
#port = "/dev/ttyACM0" # RaspPi default
port = "/dev/tty.usbmodem1411" # OSX

# OTHER GLOBALS
active_targets = []

# BlinkyTape
bt = BlinkyTape(port)
color_list = []
brightness_factor = 0.2 # 0 ... 1

# Show that we're alive for headless set-ups
for i in xrange(0, 60):
    color_list.append((0,0,0))
    bt.displayColor(i*3, i*3, i*3)
    time.sleep(0.1)

def insideBBOX(tgt, bbox):
    if tgt[0] >= bbox['llc'][0] and tgt[0] < bbox['urc'][0] and tgt[1] >= bbox['llc'][1] and tgt[1] < bbox['urc'][1]:
        return True
    else:
        return False

def insidePOI(tgt, poi, r):
    d = great_circle(poi, tgt).meters
    if d < r:
        return True
    else:
        return False

# Returns a parsed list from an array of text lines
def parseRequestArray(req):
    tracking_list = []

    for line in req:
        a = line.split(";")
        # loop through trackable line numbers
        for trigger in triggers:
            if a[1] == trigger['line'] and a[5] == trigger['direction']:
                tracking_object = { 'id': "0", 'line': "0", 'pos': (0,0), 'pos_old': (0,0), 'alert_active': False, 'passby_active': False, 'isMoving': False, 'alert_poi': (0,0), 'passby_poi': (0,0) }
                tracking_object['id'] = a[0]
                tracking_object['line'] = a[1]
                tracking_object['pos'] = (float(a[2]), float(a[3]))
                tracking_object['alert_poi'] = trigger['alert_poi']
                tracking_object['passby_poi'] = trigger['passby_poi']

                tracking_list.append(tracking_object)

    return tracking_list

# Runs necessary update functions
def update(t_list):
    global active_targets

    if len(t_list) == 0:
        active_targets = []
        return -1

    # Empty targets -> fill the list
    if len(active_targets) == 0:
        for t in t_list:
            active_targets.append(t)

    # Otherwise update existing
    else:
        # Housekeeping
        updateActiveTargets(t_list)

    updateActiveStates()
    updateMovingStates()

# Deletes an element from the list by ID
def delById(t_list, tid):
    list_tmp = list(t_list)
    i = 0

    for t in t_list:
        if t['id'] == tid:
            del list_tmp[i]

        i += 1

    t_list = []
    t_list = list(list_tmp)

    return t_list

# Checks if an id exists
def idExists(t_list, tid):
    for t in t_list:
        if t['id'] == tid:
            return True

    return False

# Updates old and new positions for ID
def updatePositionForId(pos, tid):
    global active_targets

    for a in active_targets:
        if a['id'] == tid:
            a['pos_old'] = a['pos']
            a['pos'] = pos

# Removes non-existing, updates existing and adds new items to tracking list
def updateActiveTargets(t_list):
    global active_targets

    newCnt = 0
    delCnt = 0

    upd_targets = list(active_targets)
    # First we remove the ones that are not in the new list
    for t in t_list:
        if idExists(active_targets, t['id']) == False:
            upd_targets = delById(upd_targets, t['id'])
            delCnt += 1

    active_targets = []
    active_targets = list(upd_targets)

    for t in t_list:
        if idExists(active_targets, t['id']) == True:
            # Existing ID -> update position
            updatePositionForId(t['pos'], t['id'])
        else:
            active_targets.append(t)
            newCnt += 1

    return (newCnt, delCnt)

# Updates our movement states
def updateMovingStates():
    global active_targets

    cnt = 0

    for t in active_targets:
        if great_circle(t['pos'], t['pos_old']).meters >= move_threshold:
            t['isMoving'] = True
            cnt += 1
        else:
            t['isMoving'] = False

    return cnt

# Updates our POI states
def updateActiveStates():
    global active_targets

    alertCnt = 0
    passbyCnt = 0

    for t in active_targets:
        if insidePOI(t['pos'], t['alert_poi'], search_radius):
            t['alert_active'] = True
            alertCnt += 1
        else:
            t['alert_active'] = False

        if insidePOI(t['pos'], t['passby_poi'], search_radius):
            t['passby_active'] = True
            passbyCnt += 1
        else:
            t['passby_active'] = False

    return (alertCnt, passbyCnt)

# Passby POI movement
def hasPassbyAndMoving():
    for t in active_targets:
        if t['isMoving'] == True and t['passby_active'] == True:
            return True

    return False

# Alert POI Movement
def hasAlertAndMoving():
    for t in active_targets:
        if t['isMoving'] == True and t['alert_active'] == True:
            return True

    return False

# Alert POI Movement
def hasAlertAndNotMoving():
    for t in active_targets:
        if t['alert_active'] == True and t['isMoving'] == False:
            return True

    return False

# Return true if we have moving targets
def getMoveCount():
    cnt = 0
    for t in active_targets:
        if t['isMoving'] == True:
            cnt += 1

    return cnt

# Returns true if we have any active states
def hasActive():
    for t in active_targets:
        if t['alert_active'] == True:
            return True
        if t['passby_active'] == True:
            return True

    return False

# Ticker
def tickTock(i):
    t = time.time()

    if i % 2 == 0:
        print 'Tick', t
        return True
    else:
        print 'Tock', t
        return False

def sendNextPixel(color):
    bt.sendPixel(int(color[0] * brightness_factor), int(color[1] * brightness_factor), int(color[2] * brightness_factor))

# Keeps the original color and blinks at a specific range
def blinkPosition(start, end, cnt, color):
    global color_list
    color_tmp = list(color_list)

    for i in xrange(start, end):
        color_tmp[i] = color

    for i in xrange(cnt + 1):
        for j in xrange(60):
            if i % 2 == 0:
                sendNextPixel(color_tmp[j])
            else:
                sendNextPixel(color_list[j])

        bt.show()
        time.sleep(0.5)

    for i in xrange(60):
        sendNextPixel(color_list[i])

    bt.show()

def fillColorList(color):
    global color_list

    for i in xrange(60):
        color_list[i] = color

def updateBlinky(alert, alertStatic, passby, trackCnt):
    global color_list

    red = (255, 0, 0)
    yellow = (255, 255, 0)
    cyan = (0, 255, 255)
    magenta = (255, 0, 255)
    white = (255, 255, 255)

    # PassBy blinking
    if passby == True:
        blinkPosition(0, 60, 10, cyan)

    # Fill our pixels
    if alert == True:
        fillColorList(red)
    else:
        fillColorList((0, 0, 0))

    if alertStatic == True:
        for i in xrange(15, 45):
            color_list[i] = yellow

    # Finally show the pixels
    for i in xrange(60):
        sendNextPixel(color_list[i])

    bt.show()

    # Anything we're tracking?
    if trackCnt > 0:
        blinkPosition(45, 60, trackCnt, magenta)

    return True

# The Loop
def loop():
    refresh_rate = refresh_rate_intensive
    i = 0
    alert = False
    alert_start_secs = 0

    while True:
        try:
            # Make the GET request to the API url
            r = requests.get(url)
            # Rearrange it to understandable format
            r_array = ((r.text).rstrip()).split('\n')
            t_list = parseRequestArray(r_array)

            # Run necessary updates
            update(t_list)

            # Get all the updated states
            alertNoMovement = hasAlertAndNotMoving()
            alertMovement = hasAlertAndMoving()
            passbyMovement = hasPassbyAndMoving()
            moveCnt = getMoveCount()
            trackCnt = len(active_targets)

            print "Tracking:", trackCnt, "Moving:", moveCnt, "Alert:", alert, "PassBy:", passbyMovement
            # Update the API request rate based on activity
            if alertMovement == True or alertNoMovement == True:
                refresh_rate = refresh_rate_intensive
                alert_start_secs = time.time()
                alert = True
            else:
                if time.time() - alert_start_secs > 60:
                    refresh_rate = refresh_rate_normal

            if passbyMovement == True:
                alert = False

            # Update our ticker
            tt = tickTock(i)

            # Update BlinkyTape
            updateBlinky(alert, alertNoMovement, passbyMovement, trackCnt)

            # Sleep for a moment
            time.sleep(refresh_rate)
            i += 1

        except:
            # Blue indicates an error
            bt.displayColor(0, 0, 100)
            print 'Error. Sleep(120).'
            traceback.print_exc(file=sys.stdout)
            time.sleep(120) # wait 2 min
            pass

# main - The body of this script
def main(argv):
    print 'HSLTracker v0.1'
    print 'Bounding Box    :', bbox['llc'], bbox['urc']
    print 'POI Radius      :', search_radius
    print 'Update Intervals:', refresh_rate_normal, refresh_rate_intensive
    print ' '
    print 'Tracking Lines  : <line> <direction> <alert_poi> <passby_poi>'
    for t in triggers:
        print t['line'], t['direction'], t['alert_poi'], t['passby_poi']

    # Start The Loop
    print ' '
    print 'Program running...'
    loop()

if __name__ == "__main__":
    main(sys.argv[1:])
