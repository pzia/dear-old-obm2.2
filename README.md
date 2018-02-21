# dear-old-obm2.2
Stuck with a very old corporate OBM 2.2 ? Scrap it and publish ics for mobility.

# Why ?

OBM (http://www.obm.org/) is a free collaborative software but I'm stuck with an old version (2.2) in a corporate environnement.
Waiting for the change or the upgrade, I needed to export calendars as ics files in order to add them to Google Calendar an achieve mobility.

# How ?

These scripts connect to a corporate portal, then to OBM homepage, and do the following :
* import a temporary google calendar from url
* export obm calendar as ics file
* decode and filter, and write a new ics file
* scrap a group calendar to build ics files from the participants
* publish (i.e. copy) the generated files into a subfolder (obviously readable via http)

# Configuration

* copy the obm.ini.dist as obm.ini
* complete it

# Run

./allinone.py does all the actions


