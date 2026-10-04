#!/usr/bin/env python3

import datetime
import math
import time
import sys
from collections import namedtuple
from os.path import dirname, abspath, join as pathjoin
import argparse
import getpass
import shutil
import subprocess
from configparser import ConfigParser


root_dir = dirname(abspath(__file__))
sys.path.insert(0, pathjoin(root_dir, 'crontab'))
from modules.praytimes import PrayTimes

from crontab import CronTab

# Players that playAzaan.sh knows how to drive, mapped to the command each one
# needs on PATH. Add a player here and a matching case in playAzaan.sh.
SUPPORTED_PLAYERS = {'vlc': 'cvlc', 'paplay': 'paplay'}
DEFAULT_PLAYER = 'vlc'

# Calculation methods that PrayTimes knows. The same list is used for the
# --method choices and to check a method edited by hand in settings.ini.
SUPPORTED_METHODS = list(PrayTimes.methods)

PRAYERS = ('fajr', 'dhuhr', 'asr', 'maghrib', 'isha')

# Every job this script adds has this comment, so that the next run can remove
# them and leave the other jobs in the user's crontab alone.
JOB_COMMENT = 'rpiAdhanClockJob'

# Each line that this script and playAzaan.sh write to adhan.log starts with a
# timestamp in this format. Each update deletes the lines that are older than
# LOG_DAYS days (#7).
LOG_TIME_FORMAT = '%Y-%m-%d %H:%M:%S'
LOG_DAYS = 30

# After a reboot, the update waits for the clock to synchronize (#15): it asks
# timedatectl every TIME_SYNC_INTERVAL seconds, for at most TIME_SYNC_TIMEOUT
# seconds. On this Pi, NTP synchronizes about 40 seconds after the boot.
TIME_SYNC_TIMEOUT = 15 * 60
TIME_SYNC_INTERVAL = 5


class ConfigError(Exception):
    """A setting is missing or bad, or a prayer time cannot be calculated.

    main() prints it and exits 1 before it changes the crontab.
    """


Settings = namedtuple('Settings', [
    'lat', 'lon', 'method', 'default_azaan_vol', 'fajr_azaan_vol',
    'surah_baqarah', 'surah_volume', 'player',
    'offsets',  # minutes to add to each prayer time, by prayer name
    'warnings'])  # messages for the user about values that fell back to a default

# One cron job. A day or weekday of None means every day ('*'). A job with
# reboot runs once each time the Pi starts (@reboot), and has no time.
Job = namedtuple('Job', ['hour', 'minute', 'day', 'weekday', 'command', 'reboot'],
                 defaults=(False,))


def parseArgs():
    parser = argparse.ArgumentParser(description='Calculate prayer times and install cronjobs to play Adhan')
    parser.add_argument('--lat', type=float, dest='lat',
                        help='Latitude of the location, for example 30.345621')
    parser.add_argument('--lon', type=float, dest='lon',
                        help='Longitude of the location, for example 60.512126')
    parser.add_argument('--method', choices=SUPPORTED_METHODS,
                        dest='method',
                        help='Method of calculation')
    parser.add_argument('--azaan-volume', type=int, dest='default_azaan_vol',
                        help='Volume for azaan (other than fajr) in millibels, 1500 is loud and -30000 is quiet (default 0)')
    parser.add_argument('--fajr-azaan-volume', type=int, dest='fajr_azaan_vol',
                        help='Volume for fajr azaan in millibels, 1500 is loud and -30000 is quiet (default 0)')
    parser.add_argument('--player', choices=sorted(SUPPORTED_PLAYERS), dest='player',
                        help=f'Program used to play the adhan (default {DEFAULT_PLAYER})')
    parser.add_argument('--wait-for-time-sync', action='store_true', dest='wait_for_time_sync',
                        help='Wait until the clock is synchronized before the update. '
                             'The update after a reboot uses this')
    return parser


# CORE: pure functions, no I/O
# ---------------------------------
# ---------------------------------
def resolveSettings(args, stored):
    """Merge the command line (args) with settings.ini (stored, a ConfigParser).

    Each value comes from the command line, then settings.ini, then the
    default. Returns Settings, or raises ConfigError.
    """
    warnings = []

    # Get mandatory data. First check args, if not present check settings.ini
    try:
        if args.lat is not None:
            lat = checkCoordinate('latitude', float(args.lat), 90)
        else:
            lat = checkCoordinate('latitude', float(stored['DEFAULT']['lat']), 90)

        if args.lon is not None:
            lon = checkCoordinate('longitude', float(args.lon), 180)
        else:
            lon = checkCoordinate('longitude', float(stored['DEFAULT']['lon']), 180)

        if args.method:
            method = args.method
        else:
            method = checkMethod(stored['DEFAULT']['method'])
    except (KeyError, ValueError) as err:
        raise ConfigError(f"Incorrect value or values not provided: {err}, "
                          f"please provide --lat, --lon and --method") from err

    # Get optional data
    default_azaan_vol = getVolume(args.default_azaan_vol, stored, 'defaultAzaanVolume', warnings)
    fajr_azaan_vol = getVolume(args.fajr_azaan_vol, stored, 'fajrAzaanVolume', warnings)

    # Setup Surah Baqarah on Fridays
    try:
        surahBaqarah, surahVolume = readFriday(stored)
    except (KeyError, ValueError) as err:
        warnings.append(f"Surah Baqarah not configured, disabling it: {err}")
        surahBaqarah = False
        surahVolume = 0

    # Player used by playAzaan.sh. A value edited by hand in settings.ini is not
    # covered by argparse's choices, so validate it here too.
    if args.player:
        player = args.player
    else:
        player = stored.get('PLAYER', 'player', fallback=DEFAULT_PLAYER).strip().lower()
    if player not in SUPPORTED_PLAYERS:
        raise ConfigError(f"Unsupported player '{player}' in settings.ini, "
                          f"use one of: {', '.join(sorted(SUPPORTED_PLAYERS))}")

    offsets = readOffsets(stored)

    return Settings(lat, lon, method, default_azaan_vol, fajr_azaan_vol,
                    surahBaqarah, surahVolume, player, offsets, warnings)


def checkCoordinate(name, value, limit):
  # float() accepts 'nan' and 'inf', and PrayTimes gives wrong times or none at
  # all for values out of range. Stop before settings.ini is saved so a bad
  # value is not saved and every nightly update after it does not fail on it too.
  if not math.isfinite(value) or not -limit <= value <= limit:
    raise ConfigError(f"Invalid {name} {value}, use a number from {-limit} to {limit}")
  return value


def getVolume(arg_value, config, key, warnings):
  # Resolve each volume on its own, so a missing or bad stored value falls back
  # to 0 for that volume only and does not discard the other one.
  if arg_value is not None:
    return int(arg_value)
  try:
    return int(config['VOLUME'][key])
  except (KeyError, ValueError) as err:
    warnings.append(f"Using default {key} 0, could not read the configured one: {err}")
    return 0


def checkMethod(method):
  # PrayTimes.setMethod() ignores a name it does not know and keeps calculating
  # with the previous method, so a typo gives wrong times and no error. Accept
  # any case (karachi) but return the canonical name, so that it is saved.
  canonical = {name.lower(): name for name in SUPPORTED_METHODS}
  name = canonical.get(method.strip().lower())
  if name is None:
    raise ConfigError(f"Unsupported method '{method}' in settings.ini, "
                      f"use one of: {', '.join(SUPPORTED_METHODS)}")
  return name


def readOffsets(config):
  # The minutes to add to each prayer time, from [OFFSETS] in settings.ini
  # (#12). A missing section or prayer is 0. Stop on a value that is not a
  # whole number, and on an unknown name: a typo must not lose an offset.
  if not config.has_section('OFFSETS'):
    return dict.fromkeys(PRAYERS, 0)
  section = config['OFFSETS']
  # The keys of [DEFAULT] (lat, lon, method) are in every section too
  unknown = [key for key in section if key not in PRAYERS and key not in config.defaults()]
  if unknown:
    raise ConfigError(f"Unknown prayer '{unknown[0]}' in [OFFSETS] in settings.ini, "
                      f"use: {', '.join(PRAYERS)}")
  offsets = {}
  for name in PRAYERS:
    value = section.get(name, fallback='0')
    try:
      offsets[name] = int(value)
    except ValueError:
      raise ConfigError(f"Invalid offset '{value}' for {name} in settings.ini, "
                        f"use a whole number of minutes, for example 5 or -3") from None
  return offsets


def readFriday(config):
  # getboolean, not bool(): bool() on the string "False" is True
  return (config['FRIDAY'].getboolean('playSurahBaqarah', fallback=False),
          int(config['FRIDAY']['surahVolume']))


def prayerTimes(lat, lon, method, date, utcOffset, offsets=None):
    """The five prayer times of one day as 'HH:MM', by prayer name.

    utcOffset is in hours and includes daylight saving time. offsets has the
    minutes to add to each prayer (#12). Raises ConfigError if a time cannot
    be calculated.
    """
    calculator = PrayTimes(method)
    if offsets:
        # PrayTimes adds the offsets before it rounds to the minute
        calculator.tune(offsets)
    times = calculator.getTimes((date.year, date.month, date.day), (lat, lon), utcOffset)

    # PrayTimes returns '-----' when a time cannot be calculated, which happens
    # at extreme latitudes. Stop before rescheduling anything rather than
    # crashing part way through, so the crontab that is already installed
    # keeps working.
    invalid = [name for name in PRAYERS if ':' not in times[name]]
    if invalid:
        raise ConfigError(f"Could not calculate a time for: {', '.join(invalid)}\n"
                          "Existing cron jobs have been left untouched.")
    return {name: times[name] for name in PRAYERS}


def buildJobs(times, settings, root_dir):
    """The cron jobs for the prayer times, and the jobs that keep them current."""
    # Playback goes through playAzaan.sh, which applies the configured volume,
    # runs the before/after hooks and plays the file with the configured player.
    strPlayer = f"{root_dir}/playAzaan.sh"
    strLog = f">> {root_dir}/adhan.log 2>&1"

    def play(audio, volume):
        return f"{strPlayer} {root_dir}/media/{audio} {volume} {settings.player} {strLog}"

    jobs = []
    for name in PRAYERS:
        hour, minute = times[name].split(':')
        if name == 'fajr':
            command = play('Adhan-fajr.mp3', settings.fajr_azaan_vol)
        else:
            command = play('Adhan-Makkah1.mp3', settings.default_azaan_vol)
        jobs.append(Job(int(hour), int(minute), None, None, command))
    if settings.surah_baqarah:
        jobs.append(Job(7, 0, None, 5,
                        play('002-surah-baqarah-mishary.mp3', settings.surah_volume)))
    # Run this script again overnight. It also deletes the old lines of the log.
    jobs.append(Job(3, 15, None, None, f"python3 {root_dir}/updateAzaanTimers.py {strLog}"))
    # And after each reboot, as the Pi can be off at 03:15. That update waits
    # for the clock first, because a Pi has no clock battery (#15).
    jobs.append(Job(None, None, None, None,
                    f"python3 {root_dir}/updateAzaanTimers.py --wait-for-time-sync {strLog}",
                    reboot=True))
    return jobs


def pruneLog(lines, today, days=LOG_DAYS):
    """The lines of adhan.log that are not older than days days.

    A line with no timestamp, for example a traceback, stays or goes with the
    timestamped line above it. Lines above the first timestamp (a log from
    before #7, or a traceback in a new log) stay or go with the first
    timestamped line below them, and a log with no timestamp stays. Lines with
    a date after today stay: a Pi without a clock battery can start with a
    date that is too early, and the prune must not then delete the recent
    lines.
    """
    first_day = today - datetime.timedelta(days=days)
    kept = []
    head = []  # the lines above the first timestamp
    keep = None  # None until the first timestamp
    for line in lines:
        day = logDate(line)
        if day is not None:
            if keep is None and day >= first_day:
                kept.extend(head)
            keep = day >= first_day
        if keep is None:
            head.append(line)
        elif keep:
            kept.append(line)
    return kept if keep is not None else head


def logDate(line):
    # The date of the timestamp at the start of the line, or None
    try:
        return datetime.datetime.strptime(line[:19], LOG_TIME_FORMAT).date()
    except ValueError:
        return None
# ---------------------------------
# ---------------------------------
# CORE END


# SHELL: reads and writes the crontab, settings.ini and the system
# ---------------------------------
# ---------------------------------
def checkPlayer(player):
  # Note that CronTab.find_command() cannot do this: it searches existing cron
  # jobs, not PATH, and returns a generator (always truthy).
  # Fail loudly rather than fall back to another player: the configured player
  # is the one that will run at prayer time, so it is the one that must work.
  command = SUPPORTED_PLAYERS[player]
  if not shutil.which(command):
    raise ConfigError(f"Player '{player}' is selected but {command} was not found on PATH, "
                      f"please install it or choose another player with --player")
  if player == 'paplay':
    # paplay reads files through libsndfile, which only supports MP3 from 1.1
    formats = subprocess.run([command, '--list-file-formats'],
                             capture_output=True, text=True).stdout
    if not any(line.split('\t')[0] == 'm1a' for line in formats.splitlines()):
      raise ConfigError("paplay cannot play MP3 files on this system (libsndfile 1.1 or newer "
                        "is needed), please upgrade it or use --player vlc")


def saveSettings(config, args, settings, file_path):
    # Change only the values that come from the command line or that had to be
    # resolved, so the rest of settings.ini stays as the user wrote it
    if args.lat is not None:
        config['DEFAULT']['lat'] = str(settings.lat)
    if args.lon is not None:
        config['DEFAULT']['lon'] = str(settings.lon)
    config['DEFAULT']['method'] = settings.method
    config["VOLUME"] = {
        "defaultAzaanVolume": str(settings.default_azaan_vol),
        "fajrAzaanVolume": str(settings.fajr_azaan_vol)
        }
    try:
        readFriday(config)
    except (KeyError, ValueError):
        config["FRIDAY"] = {"playSurahBaqarah": str(settings.surah_baqarah),
                            "surahVolume": str(settings.surah_volume)}
    config["PLAYER"] = {"player": settings.player}
    config["OFFSETS"] = {name: str(settings.offsets[name]) for name in PRAYERS}

    with open(file_path, 'w') as configfile:
        config.write(configfile)


def log(text=''):
    """Print text for adhan.log, with the date and time before each line."""
    stamp = datetime.datetime.now().strftime(LOG_TIME_FORMAT)
    for line in str(text).split('\n'):
        # flush, so that the lines stay in order with a traceback on stderr
        print(f'{stamp} {line}'.rstrip(), flush=True)


def pruneLogFile(path, today):
    """Delete the lines of the log that pruneLog() does not keep, in place.

    Change the same file. Do not write a new file and rename it: the cron job
    that runs this script adds its output to the log with >> (O_APPEND), and
    after a rename that output goes to the old file, which is deleted.
    """
    # surrogateescape and newline='' write back the lines that stay byte for
    # byte, also when a player wrote bytes that are not UTF-8
    with open(path, 'r+', encoding='utf-8', errors='surrogateescape', newline='') as fh:
        lines = fh.readlines()
        kept = pruneLog(lines, today)
        if kept != lines:
            fh.seek(0)
            fh.write(''.join(kept))
            fh.truncate()


def applyJobs(cron, jobs):
    """Replace the jobs of this script in cron with jobs. Other jobs stay."""
    cron.remove_all(comment=JOB_COMMENT)
    added = []
    for job in jobs:
        item = cron.new(command=job.command, comment=JOB_COMMENT)
        if job.reboot:
            item.every_reboot()
        else:
            item.minute.on(job.minute)
            item.hour.on(job.hour)
            if job.day is not None:
                item.day.on(job.day)
            if job.weekday is not None:
                item.dow.on(job.weekday)
        added.append(item)
    return added


def waitForTimeSync(timeout, interval=TIME_SYNC_INTERVAL):
    """Wait until timedatectl says that the clock is synchronized.

    Return True when it is, or False after timeout seconds or if timedatectl
    is not there. A Pi has no clock battery: at boot, fake-hwclock sets the
    time that it saved last, and the date is wrong until NTP synchronizes it.
    """
    # monotonic, because the clock jumps when it synchronizes
    deadline = time.monotonic() + timeout
    while True:
        try:
            # It can fail early in the boot. Then ask again.
            answer = subprocess.run(['timedatectl', 'show', '-p', 'NTPSynchronized', '--value'],
                                    capture_output=True, text=True, timeout=30).stdout
        except FileNotFoundError:
            log("timedatectl was not found, so the script cannot know if the clock is correct")
            return False
        except subprocess.TimeoutExpired:
            answer = ''
        if answer.strip() == 'yes':
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            log(f"The clock did not synchronize in {timeout} seconds")
            return False
        time.sleep(min(interval, remaining))


def systemUtcOffset():
    # The system timezone in hours, plus 1 while daylight saving time is on
    return -(time.timezone/float(3600)) + (1 if time.localtime().tm_isdst else 0)


def main(argv=None, settings_path=None, cron=None, today=None, utcOffset=None,
         log_path=None, sync_timeout=None):
    """Delete the old lines of the log, calculate today's prayer times and
    replace the jobs of this script.

    Every argument defaults to the real one: the command line, settings.ini
    next to this script, the user's crontab, today, the system timezone,
    adhan.log next to this script and TIME_SYNC_TIMEOUT.
    On a ConfigError, print it and exit 1 before the crontab is changed. With
    --wait-for-time-sync, if the clock does not synchronize, exit 1 too.
    """
    if settings_path is None:
        settings_path = pathjoin(root_dir, 'settings.ini')
    if log_path is None:
        log_path = pathjoin(root_dir, 'adhan.log')
    if sync_timeout is None:
        sync_timeout = TIME_SYNC_TIMEOUT

    # An error that Python or argparse writes has no timestamp. After this
    # line, it stays with this run when the log is pruned.
    log("Updating the prayer times")
    args = parseArgs().parse_args(argv)

    # The date and the timezone offset come from the clock, so get them after
    # the wait. Without the clock, keep the schedule that is installed (#15).
    if args.wait_for_time_sync:
        if not waitForTimeSync(sync_timeout):
            log("The prayer times were not updated. The 03:15 update will update them.")
            sys.exit(1)
        log("The clock is synchronized")
    if cron is None:
        cron = CronTab(user=getpass.getuser())
    if today is None:
        today = datetime.date.today()
    if utcOffset is None:
        utcOffset = systemUtcOffset()

    # A log with a problem must never stop the schedule (C4 in #16), so catch
    # any error and continue. The lines above are from this run, so they stay.
    try:
        pruneLogFile(log_path, today)
    except FileNotFoundError:
        pass
    except Exception as err:
        log(f"Could not delete the old lines of {log_path}: {err}")

    config = ConfigParser()
    config.read(settings_path)

    try:
        settings = resolveSettings(args, config)
        for warning in settings.warnings:
            log(warning)
        # Check the player is usable before it is saved, so a failed --player
        # change does not leave every nightly update failing on the same value
        checkPlayer(settings.player)
        # Calculate the times before the save too, so a location where a time
        # cannot be calculated is not saved for the nightly update (#31)
        times = prayerTimes(settings.lat, settings.lon, settings.method, today, utcOffset,
                            settings.offsets)
        saveSettings(config, args, settings, settings_path)
    except ConfigError as err:
        log(err)
        sys.exit(1)

    log("---------------------------------")
    log("Co-ordinates provided")
    log("---------------------------------")
    log(f"Latitude:   {settings.lat} \nLongitude:  {settings.lon} \nMethod:     {settings.method} \nPlayer:     {settings.player}")
    log("---------------------------------")
    log()
    log("---------------------------------")
    log("Prayer Times")
    log("---------------------------------")
    for name in PRAYERS:
        offset = settings.offsets[name]
        note = f" (offset {offset:+d} minutes)" if offset else ""
        log(f"{name.capitalize() + ':':<9}{times[name]} hrs{note}")
    log("---------------------------------")

    # Add times to crontab
    log()
    log("---------------------------------")
    log("Crob jobs scheduled")
    log("---------------------------------")
    for job in applyJobs(cron, buildJobs(times, settings, root_dir)):
        log(job)
    log("---------------------------------")

    cron.write()
    log('Script execution finished at: ' + str(datetime.datetime.now()))
# ---------------------------------
# ---------------------------------
# SHELL END


if __name__ == "__main__":
    main()
