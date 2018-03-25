#!/usr/bin/python3
# -*- coding: utf-8 -*-

#icalendar
from icalendar import Calendar, parser_tools, Event
from datetime import datetime, timezone, timedelta, date
from dateutil.relativedelta import relativedelta

#config
import configparser

#sys & os
import sys
import os.path
from shutil import copyfile
import hashlib
import pathlib

#request & parsers
import requests #pour l'injection http
import urllib.parse
import re

#logging
import logging
logging.basicConfig(filename=os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'obm.log'),level=logging.DEBUG)

#global config
gconfig = None

#misc helpers
def doubledecode(s, as_unicode=True):
    """Double decode for wrong encoding"""
    s = s.decode('utf8')
    # remove the windows gremlins O^1
    for src, dest in cp1252.items():
        s = s.replace(src, dest)
    s = s.encode('raw_unicode_escape')
    if as_unicode:
        # return as unicode string
        s = s.decode('utf8', 'ignore')
    return s

cp1252 = {
    # from http://www.microsoft.com/typography/unicode/1252.htm
    u"\u20AC": u"\x80", # EURO SIGN
    u"\u201A": u"\x82", # SINGLE LOW-9 QUOTATION MARK
    u"\u0192": u"\x83", # LATIN SMALL LETTER F WITH HOOK
    u"\u201E": u"\x84", # DOUBLE LOW-9 QUOTATION MARK
    u"\u2026": u"\x85", # HORIZONTAL ELLIPSIS
    u"\u2020": u"\x86", # DAGGER
    u"\u2021": u"\x87", # DOUBLE DAGGER
    u"\u02C6": u"\x88", # MODIFIER LETTER CIRCUMFLEX ACCENT
    u"\u2030": u"\x89", # PER MILLE SIGN
    u"\u0160": u"\x8A", # LATIN CAPITAL LETTER S WITH CARON
    u"\u2039": u"\x8B", # SINGLE LEFT-POINTING ANGLE QUOTATION MARK
    u"\u0152": u"\x8C", # LATIN CAPITAL LIGATURE OE
    u"\u017D": u"\x8E", # LATIN CAPITAL LETTER Z WITH CARON
    u"\u2018": u"\x91", # LEFT SINGLE QUOTATION MARK
    u"\u2019": u"\x92", # RIGHT SINGLE QUOTATION MARK
    u"\u201C": u"\x93", # LEFT DOUBLE QUOTATION MARK
    u"\u201D": u"\x94", # RIGHT DOUBLE QUOTATION MARK
    u"\u2022": u"\x95", # BULLET
    u"\u2013": u"\x96", # EN DASH
    u"\u2014": u"\x97", # EM DASH
    u"\u02DC": u"\x98", # SMALL TILDE
    u"\u2122": u"\x99", # TRADE MARK SIGN
    u"\u0161": u"\x9A", # LATIN SMALL LETTER S WITH CARON
    u"\u203A": u"\x9B", # SINGLE RIGHT-POINTING ANGLE QUOTATION MARK
    u"\u0153": u"\x9C", # LATIN SMALL LIGATURE OE
    u"\u017E": u"\x9E", # LATIN SMALL LETTER Z WITH CARON
    u"\u0178": u"\x9F", # LATIN CAPITAL LETTER Y WITH DIAERESIS
}

def fileSHA ( filepath ) :
    """ Compute SHA256 of a file.
        Input : filepath : full path and name of file 
        Output : string : contains the hexadecimal representation of the SHA of the file.
                          returns '0' if file could not be read (file not found, no read rights...)
    """
    try:
        f = open(filepath,'rb')
        digest = hashlib.sha256()
        while True:
            buf = f.read() 
            if not buf:
                break
            digest.update(buf)
        f.close()
    except:
        return '0'
    else:
        return digest.hexdigest()

#config helpers
def localpath():
    """Path of launcher, supposed to be the root of the tree"""
    return(os.path.dirname(os.path.abspath(sys.argv[0])))

def get_config(cname = 'obm.ini'):
    """Load config as a dict"""
    #Configuration
    global gconfig
    if gconfig == None :
        logging.info("Load config")
        gconfig = configparser.ConfigParser()
        gconfig.readfp(open(os.path.join(localpath(), cname)))
        logging.info("Config loaded, user %s" % gconfig.get('User', 'login'))
    return gconfig

def get_path(pathname_config, filename_config = None):
    """Helper to get pathname from config, and create if necessary"""
    #check path
    config = get_config()
    conf_path = os.path.join(localpath(), config.get('Path', pathname_config))
    if not os.path.exists(conf_path) :
        logging.debug("Creating %s", conf_path)
        os.mkdir(conf_path)
    if filename_config is not None:
        filename = config.get("Files", filename_config)
        conf_path = os.path.join(conf_path, filename)
    return(conf_path)

#ical parsing
def filter_from_icalendar(gcal, maxage = None):
    """Filter ical, keep only events where age < maxage"""
    config = get_config()
    if maxage == None :
        maxage = config.getint("User", "maxage")

    ncal = Calendar() #New Calendar
    oldest = datetime.now(timezone.utc)-timedelta(days=maxage)
    for component in gcal.walk():
        if component.name == "VEVENT":
            dt = component.get('dtstart').dt
            if type(dt) == type(date.today()) :
                dt = datetime.combine(dt, datetime.min.time()).replace(tzinfo=timezone.utc)
            logging.debug("VEVENT %s, %s", dt, component.get('summary'))
            if dt > oldest : #keep this one
                ncal.add_component(component)
                logging.debug("Keeping %s, %s", dt, component.get('summary'))
            elif component.has_key('rrule'): #recurring event
                rrule = component.get('rrule')
                if 'UNTIL' not in rrule or rrule['UNTIL'][0] > oldest : #OK, keep this one
                    ncal.add_component(component)
                    logging.debug("Keeping recur event %s, %s", dt, component.get('summary'))
    return(ncal)

def get_old_from_ical(pathname, limit, age, userid, owner):
    """def get_ranOBM Specific
    * Get up to <limit> events from file <icsname> older than <age> days
    * queuing for delete those where <owner> is the organizer
    * queuing for decline the others (WORKING BUT USELESS, doesn't reduce the ics file)
    """

    #FIXME : Split get old (to ical object) and purge/decline to obm

    logging.debug("Getting %s events older than %s for user %s and owner %s", limit, age, userid, owner)
    g = open(pathname,'rb')
    #time limit
    olddate = datetime.now(timezone.utc)-timedelta(days=age)

    #open calendar
    gcal = Calendar.from_ical(g.read())
    topurge = [] #for events to delete
    todecline = [] #for other events we don't want to see anymore

    for component in gcal.walk(): #for each event
        if limit == 0 :
            break #enough !
        if component.name == "VEVENT": #OK, this is a meeting
            dtstart = component.get('dtstart') #start of event
            dt = dtstart.dt
            if dt > olddate :
                continue #keep this one, not too old
            if component.has_key('rrule'): #event with repeat
                rrule = component.get('rrule')
                until = rrule['UNTIL'][0]
                if until > olddate :
                    continue #old, but repeat recently
            tsid = dt.strftime('%s') #epoc for date start
            uid = component.get('uid').split("@")[1] #event id is left part of 1234@obm
            duration = component.get('duration')
            summary = component.get('summary')
            organizer = component.get('organizer') #organizer is actual owner in OBM
            dbegin = dt.isoformat() #isoformat for date start
            event_id = "event_%s_user_%s_%s" % (uid, userid, tsid) #make event id for deleting
            if owner not in organizer : #created by someone else, can't delete
                #decline_data = {
                #    'action': 'update_decision',
                #    'calendar_id': uid,
                #    'entity_kind' : 'user',
                #    'entity_id' : userid,
                #    'rd_decision_event' : 'DECLINED'
                #}
                #FIXME : decline is useless because still present in ical export
                #todecline.append(decline_data)
                continue
            else : #event is owned
                delete_data = {
                    'action': "quick_delete",
                    "ajax" : "1",
                    "all_day" : "0",
                    'calendar_id': uid,
                    'context' : 'week',
                    'date_begin' : dbegin,
                    'duration' : duration.dt.seconds,
                    'event_id': event_id,
                    'entity': "user",
                    "entity_id":userid,
                    "entity_kind":"user",
                    "old_date_begin": dbegin,
                    "title": summary
                    }
                topurge.append(delete_data)
            limit -= 1 #one more
    g.close()
    #FIXME : event listing, and pre-processing
    return(topurge, todecline)

#http automation
def debug(q, output=None):
    """Helper : Output Debug from http request"""
    print("---")
    print(q.url, q.status_code)
    print(q.request.headers)
    print(q.headers)
    if output != None :
        with open(output, "w") as fpage:
            fpage.write(q.text)

def connect(s = None):
    """Connect to portal and OBM, keeping cookies"""
    if s != None : #already connected
        return(s)
    logging.debug("Connecting")
    config = get_config()
    portal_start = config.get('Url', 'portal_start')
    user_login = config.get('User', 'login')
    user_pass = config.get('User', 'pass')
    portal_login = config.get('Url', 'portal_login')
    obm_login = config.get('Url', 'obm_login') #this is an url for obm login

    #working headers
    headers = {
        'Accept' : 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Encoding':'gzip,deflate',
        'Accept-Language':'fr-FR,fr;q=0.8,en-US;q=0.6,en;q=0.4',
        'Connection':'keep-alive',
        'Host':portal_start.split("//")[1],
        'Origin':portal_start,
        #Friendly user agent
        'User-Agent':'Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:23.0) Gecko/20100101 Firefox/23.0'
    }

    #Start session
    s = requests.Session()
    s.headers.update(headers)

    #1-Public homepage
    logging.debug("Portal Start")
    s.get(portal_start)

    #2-Login
    logging.debug("Portal Login")
    user_login_data = { 'identifiant': user_login, 'secret': user_pass, "apply" : 'Connexion'}
    s.headers.update({'Referer' : portal_start})
    s.post(portal_login, data=user_login_data)

    #3-OBM Login
    logging.debug("OBM login")
    user_login_data = { 'login': user_login, 'password': user_pass}
    s.headers.update({'Referer' : portal_login})
    s.post(obm_login, data=user_login_data)
    
    return(s) #We're done and logged in.

def parse_group_to_ical(s = None, group_id = None, from_month = -1, to_month = 3):
    """
    Connect and parse group calendar from obm ihm
    Write ics files
    """
    config = get_config()
    s = connect(s) #connect if not connected
    
    if group_id == None :
        group_id = config.get("Group", "group_id")
    obm_index = config.get("Url", "obm_login")

    list_dates = []
    today = datetime.now(timezone.utc)
    for m in range(from_month, to_month+1):
        list_dates.append(datetime.now(timezone.utc)+relativedelta(months=m))
    
    #Group select
    logging.debug("Change to group %s", group_id)
    datas = {
        'date' : today.isoformat(),
        'group_id' : group_id,
        'new_group' : "1"
    }
    q = s.get(obm_index, params = datas)

    #Month view
    logging.debug("Change to month")
    datas = {
        'date' : today.isoformat(),
        'cal_range' : 'month'
    }
    q = s.get(obm_index, params=datas)
    #get persons : user_id <=> user_name
    l = re.findall(r'<li.*?class="(eventOwner\d+).*?data-user-(\d+).*?&nbsp;(.*?)\n\s+<\/li>', q.text, re.MULTILINE|re.DOTALL)
    persons = {}
    persons[config.get('User', 'user_id')] = config.get('User', 'login')
    for p in l:
        persons[p[1]] = p[2]

    #parse calendar for 3 months : FIXME : better range
    calendars = {}
    for dmonth in list_dates:
        logging.debug("Month of %s", dmonth.isoformat())
        datas = {
            'date' : dmonth.isoformat(),
        }
        q = s.get(obm_index, params=datas)
        #debug(q, "month.html")

        #find all events
        l = re.findall(r'Event\(({.*?})', q.text)
        for t in l :
            ev = {}
            nl = re.findall(r'(\w+):([^\']*?),', t) + re.findall(r'(\w+):\'((?:[^\'\\]|\\.)*)\',', t)
            for tt in nl :
                ev[tt[0]] = tt[1].replace("\\n", "\n").replace("\\'", "\'").replace('&quot;', '&')
            
            user_id = ev['entity_id']
            if user_id not in calendars :
                calendars[user_id] = Calendar()
                calendars[user_id].add('prodid', '-//OBM Scrapping//')
                calendars[user_id].add('version', '2.0')
            event = Event()
            event.add('dtstart', datetime.utcfromtimestamp(int(ev['time'])))
            event.add('dtend', datetime.utcfromtimestamp(int(ev['time'])+int(ev['duration'])))
            event.add("summary", ev['title'].strip("\n .;-"))
            event.add('description', ev['description'].strip("\n .;-"))
            event.add('location', ev['location'].strip("\n .;-"))
            calendars[user_id].add_component(event)

    work_path = get_path('work_directory')
    for cal in calendars :
        fname = persons[cal].replace(' ', '').replace('-', '').lower()+'.ics'
        fpath = os.path.join(work_path, fname)
        write_calendar(fpath, calendars[cal])
    return(s)

def write_calendar(filepath, ical):
    """Write <ical> object to ics in work directory with <name>"""
    f = open(filepath, 'wb')
    f.write(ical.to_ical())
    f.close()

def icalendar_from_file(pathname = None, ddecode = False):
    """load ics file into icalendar object"""
    if pathname == None :
        pathname = get_path('work_directory', 'obm_ics')
    g = open(pathname,'rb')
    if ddecode :
        icaldata = doubledecode(g.read().replace(b'\r', b''))
    else :
        icaldata = g.read()
    g.close()
    cal = Calendar().from_ical(icaldata)
    return(cal)

def publish(filelist = None):
    """Copy ics files from work to publish directory"""
    config = get_config()
    workpath = get_path('work_directory')
    publishpath = get_path('publish_directory')
    logging.debug("Publishing from %s to %s", workpath, publishpath)
    if filelist == None :
        filelist = [p for p in pathlib.Path(workpath).iterdir() if p.is_file()]
    for f in filelist :
        fpath = os.path.join(workpath, f.name)
        dpath = os.path.abspath(os.path.join(publishpath, f.name))
        logging.debug("Copy file %s to %s", fpath, dpath)
        copyfile(fpath, dpath)
    hook = config.get('Hook', 'post-publish', fallback=False)
    if hook:
        #FIXME : Execute something
        pass

def purge(s = None):
    """Delete (and decline) old events"""
    config = get_config()
    s = connect(s) #connect if not connected

    user_id = config.get('User', 'user_id')
    user_login = config.get('User', 'login')
    obm_ics = config.get('Files', 'obm_ics') #ics file from obm, previously downloaded
    obm_login = config.get('Url', 'obm_login')
    purge_limit = config.getint('Purges', 'limit') #block size for delete
    purge_age = config.getint('Purges', 'age') #minage for events to delete

    #4-OBM Purge
    topurge, todecline = get_old_from_ical(obm_ics, userid=user_id, owner=user_login, limit=purge_limit, age=purge_age)
    todecline = [] #FIXME : deactivate decline because useless, should keep only the purge ?

    for delete_data in topurge:
        logging.debug("Quick delete of %s at %s", delete_data['event_id'], delete_data['date_begin'])
        #print(delete_data['date_begin']) #print something to show we're working
        q = s.post(obm_login, data=delete_data)
        if q.status_code != 200:
            logging.error("ERROR with %s at %s" % (delete_data['event_id'], delete_data['date_begin']))
        
    for decline_data in todecline:
        logging.debug("Quick decline %s by %s", decline_data['calendar_id'], decline_data['entity_id'])
        #print("-%s-" % decline_data['calendar_id']) #print something to show we're working
        q = s.get(obm_login, data=decline_data)
        if q.status_code != 200: #FIXME : not useful
            logging.error("ERROR declining %s by %s" % (decline_data['calendar_id'], decline_data['entity_id']))
        
    return(s) #return session for later use

def download_file(url, pname, s = None):
    if s == None :
        s = requests.session()

    logging.debug("Download from %s in %s", url, pname)
    q = s.get(url)
    with open(pname, 'wb') as f:
        for chunk in q.iter_content(chunk_size=1024): 
            if chunk: # filter out keep-alive new chunks
                f.write(chunk)
    logging.debug("%s downloaded" % pname)

def download_and_filter(s = None):
    """Download ics from OBM, and filter"""
    downloaded_ics = get_path("tmp_directory", 'obm_ics')
    filtered_ics = get_path("work_directory", 'obm_ics')
    s = download(s)
    cal = icalendar_from_file(downloaded_ics, True) #FIXME : should be configurable ?
    ncal = filter_from_icalendar(cal)
    write_calendar(filtered_ics, ncal)
    return(s)

def download(s = None):
    """Download ics file exported from OBM"""

    config = get_config()
    s = connect(s) #connect if not connected

    local_filename = get_path('tmp_directory', 'obm_ics')
    obm_export = config.get('Url', 'obm_export')

    logging.debug("obm Export")
    download_file(obm_export, local_filename, s)

    return(s) #return session for later use

def upload_from_external(s = None):
    """Download external ics file and upload into OBM (if new)"""
    config = get_config()
    url = config.get('Url', 'external')
    tmppath = get_path('tmp_directory', 'external_ics')
    workpath = get_path('work_directory', 'external_ics')

    #Download
    download_file(url, tmppath)

    #Filter
    scal = icalendar_from_file(tmppath)
    dcal = filter_from_icalendar(scal, 0)
    dcal.add('prodid', '-//External to OBM//')
    dcal.add('version', '2.0')
    write_calendar(workpath, dcal)
    return(upload(s))

def upload(s = None, pathname = None):
    """Import ics file into OBM"""

    config = get_config()
    s = connect(s) #connect if not connected

    if pathname == None :
        pathname = get_path('work_directory', 'external_ics')
    
    obm_import = config.get('Url', 'obm_import')
    obm_upload = config.get('Url', 'obm_login')

    s.headers.update({'Referer' : obm_import})
    files = {
        'fi_ics': (pathname, open(pathname, 'rb'), 'text/calendar', {'Expires': '0'}),
        }
    datas = {
        'action': ('', 'ics_insert')
        }

    logging.debug("OBM Import")
    s.post(obm_upload, files=files, data=datas)

    return(s) #return session for later use

def copyfile_if_new(sname, dname):
    """Copy file if new"""
    if os.path.exists(dname) and fileSHA(dname) == fileSHA(sname) :
        logging.debug("%s already exists and same as %s", dname, sname)
        return(False)

    copyfile(sname, dname)
    logging.debug("%s copied to %s", sname, dname)
    return(True)

def download_if_new(url = None, filename = None):
    """Download ics"""
    config = get_config()
    if url == None :
        url = config.get('Url', 'external')
    if filename  == None :
        filename = config.get('Files', 'external_ics')
    tmpdir = get_path("tmp_directory")
    workdir = get_path("work_directory")
    pname = os.path.join(tmpdir, filename)
    destname = os.path.join(workdir, filename)

    #Download
    download_file(url, pname)
    #Copy and back
    return(copyfile_if_new(pname, destname))
