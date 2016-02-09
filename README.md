# ical2gcal

Takes entries from an [iCalendar][] feed and puts them into a Google
Calendar.

  [iCalendar]: https://tools.ietf.org/html/rfc5545

This is semantically a little different from simply adding the iCalendar
feed to Google Calendar, in that it merges the iCalendar feed's entries
into an existing calendar rather than having them presented as a separate
calendar in the Google Calendar interface.


## Needs Python Packages

 * googleapi https://github.com/google/google-api-python-client
 * httplib2 https://github.com/jcgregorio/httplib2
 * icalendar http://icalendar.readthedocs.org/
 * requests http://docs.python-requests.org/
 * toml https://github.com/uiri/toml


## Setting Up Permissions

This program is intended to run without user interaction, so it operates
under the Google API's "server-to-server" model using a service account.
Unfortunately, that means the initial authorization process is a little
involved.

Follow [Google's service account instructions][service-account] to get a
private key for the application:

  1. Open the [Google Developer Credentials Page][google-dev-credentials].
  2. Log in with your Google account, if necessary.
  3. Create a new project.  Give it a useful name (e.g. "ical2gcal").
  4. Continue to your new project.
  5. Click on the "Enable the APIs you want to use" link, find the
     Calendar API, and enable it.
  6. After enabling the Calendar API, click on the "Go to Credentials"
     button.  In the text at the top of that page, there will be a link to
     create a service account.  Click on that link.
  7. Click "Create service account".
  8. Give the account a name and ID.  Make a note of the ID.
  9. Check "Furnish a new private key".  Change the key type to P12.  (The
     recommended JSON format should work with relatively recent versions
     of the Python library, but only P12 has been tested.)
  10. Click "Create".
  11. Save the file it sends you and click "Close".

  [service-account]: https://support.google.com/cloud/answer/6158849#serviceaccounts
  [google-dev-credentials]: https://console.developers.google.com/projectselector/apis/credentials

Next, you need to grant the service account access to your Google
Calendar:

  1. In [Google Calendar][gcal], hover over the calendar in the "My
     calendars" list and click the down arrow that appears to the right of
     the calendar name.  Click "Calendar settings".
  2. Make a note of the Calendar ID in the "Calendar Address" section of
     the page.  You'll need this later.
  3. Click the "Share this Calendar" tab.
  4. Enter the service account ID into the blank Person space.  Change the
     permission settings to "Make changes to events".
  5. Click the "Add Person" button.
  6. Click the "Save" button.

  [gcal]: https://calendar.google.com

## The Config File

The config file is a [TOML][] config file.  All settings except
"private\_key\_password" are mandatory.  (The password defaults to
"notasecret", Google's default.  Unless you're being surprisingly paranoid
with your setup, changing the password won't make things any more secure.)

  [TOML]: https://github.com/toml-lang/toml

The settings are:

 * `google_calendar_id` - The ID of the calendar you're adding events to.
   Should be something like "hdkilefshi678sdfbjk12jio@group.calendar.google.com".
 * `google_client_email` - The service account ID.
 * `private_key_file` - The file you downloaded with your service
   account's private key.
 * `private_key_password` - The password for the private key file, if you
   changed it.
 * `icalendar_feed` - The URL of the iCalendar feed to pull from.
