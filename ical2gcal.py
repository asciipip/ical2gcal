#!/usr/bin/env python

import apiclient
import apiclient.discovery
import datetime
import httplib2
import icalendar
import json
import optparse
import os.path
import requests
import sys
import toml

from oauth2client.client import SignedJwtAssertionCredentials


parser = optparse.OptionParser()
parser.add_option('-c', '--config-file')
parser.add_option('--google-calendar-id')
parser.add_option('--google-client-email')
parser.add_option('--private-key-file')
parser.add_option('--private-key-password')
parser.add_option('--icalendar-feed')
(options, args) = parser.parse_args()

config_file = None
if options.config_file is not None:
    if not os.file.exists(options.config_file):
        print >>sys.stderr, 'Config file does not exist:', options.config_file
        sys.exit(1)
    config_file = options.config_file
elif os.path.exists('/etc/ical2gcalrc'):
    config_file = '/etc/ical2gcalrc'
elif os.path.exists(os.path.expanduser('~/.ical2gcalrc')):
    config_file = os.path.expanduser('~/.ical2gcalrc')
elif os.path.exists('ical2gcalrc'):
    config_file = 'ical2gcalrc'

def set_option(option_name, options, config, config_file, default=None):
    if vars(options)[option_name] is None:
        if config is None:
            print >>sys.stderr, 'No config file was found and not all parameters were given on the command line.'
            print >>sys.stderr, 'I can\'t work like this.'
            exit(1)
        if option_name in config:
            vars(options)[option_name] = config[option_name]
        else:
            if default is None:
                print >>sys.stderr, 'The config file (%s) does not have an "%s" option.' % (config_file, option_name)
                print >>sys.stderr, '(And it wasn\'t give on the command line either.)'
                exit(1)
            else:
                vars(options)[option_name] = default

if config_file is None:
    config = None                
else:
    config = toml.load(config_file)
    
set_option('google_calendar_id', options, config, config_file)
set_option('google_client_email', options, config, config_file)
set_option('private_key_file', options, config, config_file)
set_option('private_key_password', options, config, config_file, 'notasecret')
set_option('icalendar_feed', options, config, config_file)

with open(options.private_key_file) as f:
    private_key = f.read()
gcal_credentials = SignedJwtAssertionCredentials(options.google_client_email, private_key, 'https://www.googleapis.com/auth/calendar', private_key_password=options.private_key_password)
http_auth = gcal_credentials.authorize(httplib2.Http())
service = apiclient.discovery.build('calendar', 'v3', http=http_auth)

old_events = {}
for event in service.events().list(calendarId=options.google_calendar_id).execute()['items']:
    # Ignore everything not created by this script.
    if event['creator']['email'] == options.google_client_email:
        if 'iCalUID' not in event:
            # We created it, but without an iCalUID, we can't tie it to a feed
            # item.  Out it goes.
            service.events().delete(calendarId=options.google_calendar_id, eventId=event['id']).execute()
            print 'delete:', event['start']['dateTime'], event['summary']
        else:
            old_events[event['iCalUID']] = event

r = requests.get(options.icalendar_feed)
ic = icalendar.cal.Calendar.from_ical(r.text)
for sc in ic.subcomponents:
    if sc.name == 'VEVENT' and sc['CATEGORIES'] != 'Seminar':
        #print sc.to_ical()
        iCalUID = sc['UID']
        event = {
            'iCalUID': iCalUID,
            'summary': sc['SUMMARY'],
            'start': {'dateTime': sc['DTSTART'].dt.isoformat('T')},
            'end': {'dateTime': sc['DTEND'].dt.isoformat('T')},
            'location': sc['LOCATION'],
            'description': sc['DESCRIPTION'],
            'source': {
                'title': sc['SUMMARY'],
                'url': sc['URL'],
            },
        }
        if iCalUID in old_events:
            old_event = old_events.pop(iCalUID)
            updated = 'no update'
            for k, v in event.iteritems():
                if (k in old_event and old_event[k] != v) or \
                   (k not in old_event and v not in (None, '')):
                    print '%s: "%s" != "%s"' % (k, v, old_event[k] if k in old_event else None)
                    service.events().update(calendarId=options.google_calendar_id, eventId=old_event['id'], body=event).execute()
                    updated = 'updated'
                    break
            print '%s: %s %s' % (updated, event['start']['dateTime'], event['summary'])
        else:
            service.events().insert(calendarId=options.google_calendar_id, body=event).execute()
            print 'added:', event['start']['dateTime'], event['summary']

# Everything left in old_events is not in the feed anymore.  Delete it.
for old_event in old_events.values():
    service.events().delete(calendarId=options.google_calendar_id, eventId=old_event['id']).execute()
    print 'delete:', old_event['start']['dateTime'], old_event['summary']
    
