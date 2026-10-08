# Raspberry Pi Adhan Clock
This project plays the [adhan](https://en.wikipedia.org/wiki/Adhan) on a Raspberry Pi at the
five prayer times. A Python script calculates the prayer times for your location each day.
Cron then plays each adhan at its time.

This repository is the maintained fork of
[achaudhry/adhan](https://github.com/achaudhry/adhan). See [Credits](#credits).

## Prerequisites
1. A Raspberry Pi with Raspberry Pi OS.
  1. A Raspberry Pi Zero has no audio output port. If you are new to the Raspberry Pi, use a different model.
  2. To install Raspberry Pi OS, follow the [getting started guide](https://www.raspberrypi.com/documentation/computers/getting-started.html).
2. Speakers.
3. An auxiliary audio cable.
4. A player for the adhan. Install only the player that you use (see [Choosing the player](#choosing-the-player)):
  ```bash
  sudo apt install vlc               # player = vlc (the default)
  sudo apt install pulseaudio-utils  # player = paplay
  ```

## Caution when you use Bluetooth speakers
The Bluetooth drivers of the Raspberry Pi have known problems. The speaker can disconnect
at random times. We recommend a wired speaker.

## Instructions
1. Install git. Open a terminal on the Raspberry Pi and type:
  ```bash
  sudo apt install git
  ```
2. Clone this repository into your home directory:
  ```bash
  cd ~
  git clone https://github.com/rehanhaider/adhan.git
  ```
  You now have an `adhan` directory in your home directory.

The examples in this README use `~/adhan`. You can clone the repository into a different
directory. The script finds its files from its own location, and the cron jobs use the full
path of that directory.

## Run it for the first time
Type this command:

```bash
python3 ~/adhan/updateAzaanTimers.py --lat <YOUR_LAT> --lon <YOUR_LNG> --method <METHOD>
```

Replace the arguments with your location and your calculation method:
* `--lat` and `--lon`: the latitude and longitude of your location. The script uses them to
  calculate the prayer times.
* `--method`: the [calculation method](http://praytimes.org/manual#Set_Calculation_Method)
  for the prayer times.

The script uses the timezone of the Raspberry Pi. Make sure that the timezone is correct.

### Calculation methods
| Method | Name | Parameters |
|---|---|---|
| `MWL` | Muslim World League | Fajr 18°, Isha 17° |
| `ISNA` | Islamic Society of North America (ISNA) | Fajr 15°, Isha 15° |
| `Egypt` | Egyptian General Authority of Survey | Fajr 19.5°, Isha 17.5° |
| `Makkah` | Umm Al-Qura University, Makkah | Fajr 18.5°, Isha 90 minutes after Maghrib |
| `Karachi` | University of Islamic Sciences, Karachi | Fajr 18°, Isha 18° |
| `Tehran` | Institute of Geophysics, University of Tehran | Fajr 17.7°, Isha 14°, Maghrib 4.5°, Jafari midnight |
| `Jafari` | Shia Ithna-Ashari, Leva Institute, Qum | Fajr 16°, Isha 14°, Maghrib 4°, Jafari midnight |

### The output
If the script runs correctly, the output is similar to this. `USER` is your user name.

```
2026-05-15 12:00:00 Updating the prayer times
2026-05-15 12:00:00 Using default defaultAzaanVolume 0, could not read the configured one: 'VOLUME'
2026-05-15 12:00:00 Using default fajrAzaanVolume 0, could not read the configured one: 'VOLUME'
2026-05-15 12:00:00 Surah Baqarah not configured, disabling it: 'FRIDAY'
2026-05-15 12:00:00 ---------------------------------
2026-05-15 12:00:00 Co-ordinates provided
2026-05-15 12:00:00 ---------------------------------
2026-05-15 12:00:00 Latitude:   28.4792507
2026-05-15 12:00:00 Longitude:  77.535747
2026-05-15 12:00:00 Method:     Karachi
2026-05-15 12:00:00 Asr school: Standard
2026-05-15 12:00:00 Player:     vlc
2026-05-15 12:00:00 Lead-in:    0 seconds
2026-05-15 12:00:00 ---------------------------------
2026-05-15 12:00:00
2026-05-15 12:00:00 ---------------------------------
2026-05-15 12:00:00 Prayer Times
2026-05-15 12:00:00 ---------------------------------
2026-05-15 12:00:00 Fajr:    04:01 hrs
2026-05-15 12:00:00 Dhuhr:   12:16 hrs
2026-05-15 12:00:00 Asr:     15:50 hrs
2026-05-15 12:00:00 Maghrib: 19:03 hrs
2026-05-15 12:00:00 Isha:    20:32 hrs
2026-05-15 12:00:00 ---------------------------------
2026-05-15 12:00:00
2026-05-15 12:00:00 ---------------------------------
2026-05-15 12:00:00 Cron jobs scheduled
2026-05-15 12:00:00 ---------------------------------
2026-05-15 12:00:00 1 4 * * * /home/USER/adhan/playAzaan.sh /home/USER/adhan/media/Adhan-fajr.mp3 0 vlc >> /home/USER/adhan/adhan.log 2>&1 # rpiAdhanClockJob
2026-05-15 12:00:00 16 12 * * * /home/USER/adhan/playAzaan.sh /home/USER/adhan/media/Adhan-Makkah1.mp3 0 vlc >> /home/USER/adhan/adhan.log 2>&1 # rpiAdhanClockJob
2026-05-15 12:00:00 50 15 * * * /home/USER/adhan/playAzaan.sh /home/USER/adhan/media/Adhan-Makkah1.mp3 0 vlc >> /home/USER/adhan/adhan.log 2>&1 # rpiAdhanClockJob
2026-05-15 12:00:00 3 19 * * * /home/USER/adhan/playAzaan.sh /home/USER/adhan/media/Adhan-Makkah1.mp3 0 vlc >> /home/USER/adhan/adhan.log 2>&1 # rpiAdhanClockJob
2026-05-15 12:00:00 32 20 * * * /home/USER/adhan/playAzaan.sh /home/USER/adhan/media/Adhan-Makkah1.mp3 0 vlc >> /home/USER/adhan/adhan.log 2>&1 # rpiAdhanClockJob
2026-05-15 12:00:00 15 3 * * * python3 /home/USER/adhan/updateAzaanTimers.py >> /home/USER/adhan/adhan.log 2>&1 # rpiAdhanClockJob
2026-05-15 12:00:00 @reboot python3 /home/USER/adhan/updateAzaanTimers.py --wait-for-time-sync >> /home/USER/adhan/adhan.log 2>&1 # rpiAdhanClockJob
2026-05-15 12:00:00 ---------------------------------
2026-05-15 12:00:00 Script execution finished at: 2026-05-15 12:00:00.123456
```

The first run has no `settings.ini` yet, so it uses the defaults. The lines with "Using
default" and "not configured" tell you this. The script then writes `settings.ini`, and
the next runs do not show these lines.

The "Cron jobs scheduled" part shows the jobs that the script added to your crontab:
* The first 5 jobs play the 5 adhans at today's prayer times.
* The `15 3 * * *` job runs the script again at 03:15 every night. That run calculates the
  prayer times for the new day and replaces the adhan jobs. It also deletes the lines of
  `adhan.log` that are older than 30 days, so the log does not become too large.
* The `@reboot` job runs the script each time the Raspberry Pi starts, because the Raspberry
  Pi can be off at 03:15. A Raspberry Pi has no clock battery, so this run first waits for
  the clock to synchronize, for a maximum of 15 minutes. If the clock does not synchronize,
  the run changes nothing, and the 03:15 run updates the times.

Each job ends with the comment `# rpiAdhanClockJob`. The script uses this comment to find
its own jobs. Each run removes all the jobs with this comment and adds the new jobs. Your
other cron jobs do not change. Do not add this comment to your own jobs.

The script saves its settings in `~/adhan/settings.ini`. For the next runs, you do not
have to give the arguments again. The nightly run uses the saved settings.

You are done. Connect your speakers and enjoy!

## Settings
You can give each setting on the command line, or write it in `settings.ini`. The script
uses the value from the command line first, then the value in `settings.ini`, then the
default. It saves each value from the command line in `settings.ini`. You can give the
optional settings in the first run or in a later run.

After you edit `settings.ini`, the new values apply at the next run. To apply them now,
run the script again without arguments:

```bash
python3 ~/adhan/updateAzaanTimers.py
```

To see all the arguments, type:

```bash
python3 ~/adhan/updateAzaanTimers.py -h
```

If a value is not correct, the script stops and writes the reason to the output. It does
not change your crontab or `settings.ini`. The adhan jobs of the last correct run stay.

This is the `settings.ini` that the first run writes:

```
[DEFAULT]
lat = 28.4792507
lon = 77.535747
method = Karachi
asr = Standard

[VOLUME]
defaultazaanvolume = 0
fajrazaanvolume = 0

[FRIDAY]
playsurahbaqarah = False
surahvolume = 0

[PLAYER]
player = vlc
leadin_seconds = 0

[OFFSETS]
fajr = 0
dhuhr = 0
asr = 0
maghrib = 0
isha = 0

[ENABLED]
fajr = true
dhuhr = true
asr = true
maghrib = true
isha = true

[AUDIO]
default = Adhan-Makkah1.mp3
fajr = Adhan-fajr.mp3
```

### Location and calculation method
| Command line | `settings.ini` | Values |
|---|---|---|
| `--lat` | `[DEFAULT] lat` | -90 to 90. Required on the first run. |
| `--lon` | `[DEFAULT] lon` | -180 to 180. Required on the first run. |
| `--method` | `[DEFAULT] method` | One of the [calculation methods](#calculation-methods). Required on the first run. |

### Asr school
The Asr school sets the method for the Asr time. The Hanafi school gives a later Asr time.

| Command line | `settings.ini` | Values | Default |
|---|---|---|---|
| `--asr` | `[DEFAULT] asr` | `Standard` or `Hanafi` | `Standard` |

For example:

```bash
python3 ~/adhan/updateAzaanTimers.py --asr Hanafi
```

### Volume
You set the volume in millibels. `0` is the normal volume of the file. `1500` is loud.
`-30000` is almost silent. The maximum gain is 8 times the normal volume (+18 dB).

| Command line | `settings.ini` | Applies to | Default |
|---|---|---|---|
| `--fajr-azaan-volume` | `[VOLUME] fajrazaanvolume` | Fajr | `0` |
| `--azaan-volume` | `[VOLUME] defaultazaanvolume` | Dhuhr, Asr, Maghrib and Isha | `0` |

If a volume in `settings.ini` is not a whole number, the script uses `0` and writes a
warning to the output.

`playAzaan.sh` changes the millibels to the volume scale of the selected player. Thus the
same numbers work as they did with omxplayer.

### Offsets
An offset moves a prayer time by a number of minutes. A positive number makes the adhan
later. A negative number makes it earlier.

| Command line | `settings.ini` | Values | Default |
|---|---|---|---|
| `--fajr-offset`, `--dhuhr-offset`, `--asr-offset`, `--maghrib-offset`, `--isha-offset` | `[OFFSETS] fajr`, `dhuhr`, `asr`, `maghrib`, `isha` | A whole number of minutes, for example `5` or `-3` | `0` |

For example, this command plays the Isha adhan 10 minutes later:

```bash
python3 ~/adhan/updateAzaanTimers.py --isha-offset 10
```

### Turn a prayer on or off
You can turn the adhan of each prayer on or off. The script calculates the time of a prayer
that is off, but it adds no job for that prayer. The output shows "(not scheduled)" after
that prayer.

| Command line | `settings.ini` | Values | Default |
|---|---|---|---|
| `--play-fajr` or `--no-play-fajr`, and the same for `dhuhr`, `asr`, `maghrib` and `isha` | `[ENABLED] fajr`, `dhuhr`, `asr`, `maghrib`, `isha` | `true` or `false` (also `yes`, `no`, `on`, `off`, `1`, `0`) | `true` |

For example, this command turns off the Fajr adhan:

```bash
python3 ~/adhan/updateAzaanTimers.py --no-play-fajr
```

### Audio files
You can select the adhan file for each prayer. Give the name of a file in the `media`
directory, or the full path of a file. The `media` directory has these adhan files:
`Adhan-fajr.mp3`, `Adhan-Madinah.mp3`, `Adhan-Makkah1.mp3`, `Adhan-Makkah1-Dua.mp3`,
`Adhan-Makkah2.mp3`, `Adhan-Makkah-Dua.mp3` and `Adhan-Turkish.mp3`.

| Command line | `settings.ini` | Applies to | Default |
|---|---|---|---|
| `--audio` | `[AUDIO] default` | Each prayer that has no file of its own | `Adhan-Makkah1.mp3` |
| `--fajr-audio` | `[AUDIO] fajr` | Fajr | `Adhan-fajr.mp3` |
| `--dhuhr-audio`, `--asr-audio`, `--maghrib-audio`, `--isha-audio` | `[AUDIO] dhuhr`, `asr`, `maghrib`, `isha` | That prayer | The `default` file |

For example, this command plays `Adhan-Madinah.mp3` for Isha:

```bash
python3 ~/adhan/updateAzaanTimers.py --isha-audio Adhan-Madinah.mp3
```

The script makes sure that the file of each prayer that is on is there and that it can read
the file. A file name must not contain `%`, `#` or a control character. It must not start
or end with a space.

### Lead-in of silence
Some speakers go to sleep when they play no sound. Such a speaker can need some time to
wake up, and then it does not play the start of the adhan. A lead-in plays seconds of
silence before the adhan, so the speaker is awake when the adhan starts.

| Command line | `settings.ini` | Values | Default |
|---|---|---|---|
| `--leadin-seconds` | `[PLAYER] leadin_seconds` | A whole number from `0` to `10` | `0` (no silence) |

For example:

```bash
python3 ~/adhan/updateAzaanTimers.py --leadin-seconds 2
```

`playAzaan.sh` plays `media/silence-1s.wav` one time for each second. If that file is not
there, it plays the adhan without the lead-in. With a lead-in, each adhan job has one more
number after the player, for example `... 0 vlc 2 >> ...`.

## Play Surah Baqarah on Fridays
The script can play Surah Al-Baqarah every Friday at 07:00. This feature is off by
default. There is no command-line argument for it. To turn it on, edit the `[FRIDAY]`
section of `settings.ini`:

```
[FRIDAY]
playsurahbaqarah = True
surahvolume = 0
```

`surahvolume` is the volume in millibels, the same as the [adhan volume](#volume). The
job plays `media/002-surah-baqarah-mishary.mp3` with the selected player and lead-in. The
next run adds the job. In the output, the job looks like this:

```
0 7 * * 5 /home/USER/adhan/playAzaan.sh /home/USER/adhan/media/002-surah-baqarah-mishary.mp3 0 vlc >> /home/USER/adhan/adhan.log 2>&1 # rpiAdhanClockJob
```

If a value in `[FRIDAY]` is not correct, the script turns off the Surah, writes a warning
to the output and writes the default values to `settings.ini`.

## Choosing the player
The adhan can play through VLC (`cvlc`) or the PulseAudio `paplay`. VLC is the default.

| Command line | `settings.ini` | Values | Default |
|---|---|---|---|
| `--player` | `[PLAYER] player` | `vlc` or `paplay` | `vlc` |

For example:

```bash
python3 ~/adhan/updateAzaanTimers.py --player paplay
```

You must install only the selected player. Each run of `updateAzaanTimers.py` makes sure
that the selected player is on `PATH`. If it is not, the script stops and writes the reason
to `adhan.log`. It does not change to the other player. To read MP3 files, `paplay` also
needs `libsndfile` 1.1 or newer. The script also makes sure of this.

## How playback works
Cron does not start the player directly. Each adhan job runs `playAzaan.sh`. This script:
1. Runs each executable script in `before-hooks.d/`.
2. Plays the lead-in of silence, if there is one.
3. Plays the audio with the selected player (`cvlc --play-and-exit` or `paplay`) at the
   configured volume.
4. Runs each executable script in `after-hooks.d/`.

You can play a file manually in the same way as the jobs do. The arguments are the file,
the volume in millibels, the player and the lead-in in seconds. The last 3 arguments are
optional:
```bash
cd ~/adhan
./playAzaan.sh media/Adhan-Makkah1.mp3 0 vlc
```

## Configuring custom actions before/after adhan
Sometimes you must run commands before the adhan, after the adhan, or both. For example, if
you have [Quran playing continuously](https://github.com/LintangWisesa/RPi_QuranSpeaker),
you can pause the Quran before the adhan and resume it after the adhan. Other examples are
to set your status on a social network or a calendar, or to block and unblock the Internet
with [Pi-hole rules](https://docs.pi-hole.net/).

To do this, add scripts to these directories:
- `before-hooks.d`: scripts that run before the adhan.
- `after-hooks.d`: scripts that run after the adhan.

The scripts run in alphabetical order. If a script fails, the adhan still plays.

### Example
To pause and resume the Quran with the
[RPi_QuranSpeaker](https://github.com/LintangWisesa/RPi_QuranSpeaker) project, add these
2 new files to the 2 directories. Change the path if you installed RPi_QuranSpeaker in a
different directory:

```bash
# before-hooks.d/01-pause-quran-speaker.sh
#!/usr/bin/env bash
"$HOME/RPi_QuranSpeaker/pauser.py" pause
```

```bash
# after-hooks.d/01-resume-quran-speaker.sh
#!/usr/bin/env bash
"$HOME/RPi_QuranSpeaker/pauser.py" resume
```

Make the scripts executable. A script that is not executable does not run:
```bash
cd ~/adhan
chmod u+x ./before-hooks.d/01-pause-quran-speaker.sh
chmod u+x ./after-hooks.d/01-resume-quran-speaker.sh
```

## Tips
1. To see your scheduled jobs, type `crontab -l`.
2. All the jobs write their output to `~/adhan/adhan.log`. Use the log to make sure that
   each run was successful and to find problems. Each adhan writes a line when it starts
   and a line when it ends, with the errors from the player. Each line starts with the date
   and time. The log keeps the lines of the last 30 days. To see the log, type
   `cat ~/adhan/adhan.log`.

## Credits
This repository is the maintained fork of [achaudhry/adhan](https://github.com/achaudhry/adhan).
That project used these as a starting point:
* Python code to calculate the adhan times: http://praytimes.org/code/
* Basic code to make an adhan clock from the code above: http://randomconsultant.blogspot.co.uk/2013/07/turn-your-raspberry-pi-into-azaanprayer.html
* Cron scheduler: https://pypi.python.org/pypi/python-crontab/

See the [PrayTimes manual](http://praytimes.org/manual) for more information about the
calculation of the prayer times.
