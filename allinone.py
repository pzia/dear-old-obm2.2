#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
All in one :
- get tmp ics file from Google Calendar, and import
- retrieve OBM ics file, and filter
- publish
"""

#imports
import obmlib

if __name__ == '__main__':

    #download tmp calendar and insert into obm
    s = obmlib.upload_from_external()

    #download obm calendar and filter
    s = obmlib.download_and_filter(s)
    
    #download and build ical from group
    s = obmlib.parse_group_to_ical(s)

    #s = obmlib.purge(s, config)
    #FIXME : Do we want to purge automatically ?
    
    #FIXME : publish
    obmlib.publish()
