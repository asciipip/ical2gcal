#!/usr/bin/env python

import apiclient
import apiclient.discovery
import apiclient.errors
import codecs
import datetime
import httplib2
import icalendar
import json
import optparse
import os.path
import requests
import sys
import toml

try:
    from oauth2client.service_account import ServiceAccountCredentials
    OA2C_VERSION = 2
except ImportError:
    from oauth2client.client import SignedJwtAssertionCredentials
    OA2C_VERSION = 1

if sys.stdout.encoding is None:
    sys.stdout = codecs.getwriter('UTF-8')(sys.stdout)

parser = optparse.OptionParser()
parser.add_option('-c', '--config-file')
parser.add_option('-v', '--verbose', action='store_true')
parser.add_option('--google-calendar-id')
parser.add_option('--google-client-email')
parser.add_option('--private-key-file')
parser.add_option('--private-key-password')
parser.add_option('--icalendar-feed')
parser.add_option('--include-category', dest='include_categories', action='append')
parser.add_option('--exclude-category', dest='exclude_categories', action='append')
(options, args) = parser.parse_args()

config_file = None
if options.config_file is not None:
    if not os.path.exists(options.config_file):
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
set_option('include_categories', options, config, config_file, [])
set_option('exclude_categories', options, config, config_file, [])
options.include_categories = set(options.include_categories)
options.exclude_categories = set(options.exclude_categories)

# If we can't find the private key, assume it's a path relative to the
# location of the config file.
if not os.path.exists(options.private_key_file):
    options.private_key_file = os.path.join(os.path.dirname(options.config_file), options.private_key_file)

if OA2C_VERSION == 1:
    with open(options.private_key_file) as f:
        private_key = f.read()
    gcal_credentials = SignedJwtAssertionCredentials(options.google_client_email, private_key, 'https://www.googleapis.com/auth/calendar', private_key_password=options.private_key_password)
elif OA2C_VERSION == 2:
    try:
        gcal_credentials = ServiceAccountCredentials.from_json_keyfile_name(options.private_key_file, 'https://www.googleapis.com/auth/calendar')
    except ValueError:
        gcal_credentials = ServiceAccountCredentials.from_p12_keyfile(options.google_client_email, options.private_key_file, options.private_key_password, 'https://www.googleapis.com/auth/calendar')
else:
    assert False, 'Unknown oauth2client version'
http_auth = gcal_credentials.authorize(httplib2.Http())
service = apiclient.discovery.build('calendar', 'v3', http=http_auth)

try:
    old_events = {}
    page_token = None
    while True:
        events = service.events().list(calendarId=options.google_calendar_id, pageToken=page_token).execute()
        for event in events['items']:
            # Ignore everything not created by this script.
            if 'creator' in event and event['creator']['email'] == options.google_client_email:
                if 'iCalUID' not in event:
                    # We created it, but without an iCalUID, we can't tie it to a feed
                    # item.  Out it goes.
                    service.events().delete(calendarId=options.google_calendar_id, eventId=event['id']).execute()
                    if options.verbose:
                        print 'delete:', event['start']['dateTime'], event['summary']
                else:
                    old_events[event['iCalUID']] = event
        page_token = events.get('nextPageToken')
        if not page_token:
            break
except apiclient.errors.HttpError, e:
    print >>sys.stderr, 'Error accessing Google Calendar API:', e
    print >>sys.stderr, 'No events were synchronized.'
    sys.exit(1)
    
try:
    r = requests.get(options.icalendar_feed)
    try:
        ic = icalendar.cal.Calendar.from_ical(r.text)
    except ValueError:
        print >>sys.stderr, 'Unable to parse iCalendar data from feed:', options.icalendar_feed
        sys.exit(1)
    for sc in ic.subcomponents:
        if sc.name == 'VEVENT':
            categories = set(sc['CATEGORIES'].split(','))
            if (len(options.include_categories) == 0 or len(categories & options.include_categories) > 0) and \
               categories.isdisjoint(options.exclude_categories):
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
                            if options.verbose:
                                print '%s: "%s" != "%s"' % (k, v, old_event[k] if k in old_event else None)
                            service.events().update(calendarId=options.google_calendar_id, eventId=old_event['id'], body=event).execute()
                            updated = 'updated'
                            break
                    if options.verbose:
                        print '%s: %s %s' % (updated, event['start']['dateTime'], event['summary'])
                else:
                    service.events().insert(calendarId=options.google_calendar_id, body=event).execute()
                    if options.verbose:
                        print 'added:', event['start']['dateTime'], event['summary']
except apiclient.errors.HttpError, e:
    print >>sys.stderr, 'Error accessing Google Calendar API:', e
    print >>sys.stderr, 'Events might not have been synchronized.'
    sys.exit(1)
    
try:
    # Everything left in old_events is not in the feed anymore.  Delete it.
    for old_event in old_events.values():
        service.events().delete(calendarId=options.google_calendar_id, eventId=old_event['id']).execute()
        if options.verbose:
            print 'delete:', old_event['start']['dateTime'], old_event['summary']
except apiclient.errors.HttpError, e:
    print >>sys.stderr, 'Error accessing Google Calendar API:', e
    print >>sys.stderr, 'Old events might not have been purged.'
    sys.exit(1)
