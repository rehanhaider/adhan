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

The "Cron jobs scheduled" part shows the jobs that the script added to your crontab:
* The first 5 jobs play the 5 adhans at today's prayer times.
* After them, there is one job for each [rule](#rules-play-a-file-at-a-time) that is on.
  The first run has no rules.
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

The script saves its settings in `~/adhan/adhan.toml`. For the next runs, you do not
have to give the arguments again. The nightly run uses the saved settings.

You are done. Connect your speakers and enjoy!

## Settings
You can give each setting on the command line, or write it in `adhan.toml`. The script
uses the value from the command line first, then the value in `adhan.toml`, then the
default. You can give the optional settings in the first run or in a later run.

Each run writes all the settings to `adhan.toml` again, with the values from the command
line. Thus the nightly run uses them too. The comments in the file are lost.

After you edit `adhan.toml`, the new values apply at the next run. To apply them now,
run the script again without arguments:

```bash
python3 ~/adhan/updateAzaanTimers.py
```

To see all the arguments, type:

```bash
python3 ~/adhan/updateAzaanTimers.py -h
```

If a value is not correct, the script stops and writes the reason to the output. It does
not change your crontab or `adhan.toml`. The adhan jobs of the last correct run stay. These
are not correct:
* A file that is not [TOML](https://toml.io/). For example, a text must be in double
  quotes: `method = "Karachi"`, not `method = Karachi`.
* A table or a key that is not in the tables below, for example a key with a typo.
* A value of the wrong type, for example `volume = "0"` or `enabled = "true"`. A number
  has no quotes. `true` and `false` have no quotes.
* A value that is not in the range of its setting, or an audio file that is not there.

### The file adhan.toml
This is the `adhan.toml` that the first run writes:

```toml
# The settings of the adhan clock. See README.md.
# updateAzaanTimers.py writes this file again on each run, so comments are lost.

[location]
lat = 28.4792507
lon = 77.535747
method = "Karachi"
asr = "Standard"

[audio]
player = "vlc"
leadin_seconds = 0
volume = 0
file = "Adhan-Makkah1.mp3"

[prayers.fajr]
file = "Adhan-fajr.mp3"
volume = 0
offset_minutes = 0
enabled = true

[prayers.dhuhr]
offset_minutes = 0
enabled = true

[prayers.asr]
offset_minutes = 0
enabled = true

[prayers.maghrib]
offset_minutes = 0
enabled = true

[prayers.isha]
offset_minutes = 0
enabled = true
```

Only `lat`, `lon` and `method` are necessary. Each key that is not in the file has its
default value. For example, this file is also correct. It plays Fajr more quietly, plays
Maghrib 3 minutes later, turns off the Isha adhan and plays Surah Baqarah on Fridays at
07:00 (see [Rules](#rules-play-a-file-at-a-time)):

```toml
[location]
lat = 51.5072
lon = -0.1276
method = "MWL"
asr = "Hanafi"

[audio]
leadin_seconds = 2

[prayers.fajr]
volume = -1000

[prayers.maghrib]
offset_minutes = 3

[prayers.isha]
enabled = false

[[rule]]
name = "Surah Baqarah"
days = ["fri"]
at = "07:00"
file = "002-surah-baqarah-mishary.mp3"
```

The tables of `adhan.toml` are:
* `[location]`: the location, the calculation method and the Asr school.
* `[audio]`: the player, the lead-in, and the volume and file of each prayer that has no
  volume or file of its own.
* `[prayers.fajr]`, `[prayers.dhuhr]`, `[prayers.asr]`, `[prayers.maghrib]` and
  `[prayers.isha]`: the settings of one prayer.
* `[[rule]]`: one rule, which plays a file at a time. There can be many rules. See
  [Rules](#rules-play-a-file-at-a-time).

### Location and calculation method
| Command line | `adhan.toml` | Values |
|---|---|---|
| `--lat` | `[location] lat` | A number from -90 to 90. Required on the first run. |
| `--lon` | `[location] lon` | A number from -180 to 180. Required on the first run. |
| `--method` | `[location] method` | One of the [calculation methods](#calculation-methods), in quotes. Required on the first run. |

### Asr school
The Asr school sets the method for the Asr time. The Hanafi school gives a later Asr time.

| Command line | `adhan.toml` | Values | Default |
|---|---|---|---|
| `--asr` | `[location] asr` | `"Standard"` or `"Hanafi"` | `"Standard"` |

For example:

```bash
python3 ~/adhan/updateAzaanTimers.py --asr Hanafi
```

### Volume
You set the volume in millibels. `0` is the normal volume of the file. `1500` is loud.
`-30000` is almost silent. The maximum gain is 8 times the normal volume (+18 dB).

| Command line | `adhan.toml` | Applies to | Default |
|---|---|---|---|
| `--fajr-azaan-volume` | `[prayers.fajr] volume` | Fajr | `0` |
| `--azaan-volume` | `[audio] volume` | Each prayer that has no volume of its own | `0` |
| none | `[prayers.dhuhr] volume`, and the same for `asr`, `maghrib` and `isha` | That prayer | The `[audio] volume` |

A volume is a whole number.

`playAzaan.sh` changes the millibels to the volume scale of the selected player. Thus the
same numbers work as they did with omxplayer.

### Offsets
An offset moves a prayer time by a number of minutes. A positive number makes the adhan
later. A negative number makes it earlier.

| Command line | `adhan.toml` | Values | Default |
|---|---|---|---|
| `--fajr-offset`, `--dhuhr-offset`, `--asr-offset`, `--maghrib-offset`, `--isha-offset` | `[prayers.fajr] offset_minutes`, and the same for `dhuhr`, `asr`, `maghrib` and `isha` | A whole number of minutes, for example `5` or `-3` | `0` |

For example, this command plays the Isha adhan 10 minutes later:

```bash
python3 ~/adhan/updateAzaanTimers.py --isha-offset 10
```

### Turn a prayer on or off
You can turn the adhan of each prayer on or off. The script calculates the time of a prayer
that is off, but it adds no job for that prayer. The output shows "(not scheduled)" after
that prayer.

| Command line | `adhan.toml` | Values | Default |
|---|---|---|---|
| `--play-fajr` or `--no-play-fajr`, and the same for `dhuhr`, `asr`, `maghrib` and `isha` | `[prayers.fajr] enabled`, and the same for `dhuhr`, `asr`, `maghrib` and `isha` | `true` or `false` | `true` |

For example, this command turns off the Fajr adhan:

```bash
python3 ~/adhan/updateAzaanTimers.py --no-play-fajr
```

### Audio files
You can select the adhan file for each prayer. Give the name of a file in the `media`
directory, or the full path of a file. The `media` directory has these adhan files:
`Adhan-fajr.mp3`, `Adhan-Madinah.mp3`, `Adhan-Makkah1.mp3`, `Adhan-Makkah1-Dua.mp3`,
`Adhan-Makkah2.mp3`, `Adhan-Makkah-Dua.mp3` and `Adhan-Turkish.mp3`.

| Command line | `adhan.toml` | Applies to | Default |
|---|---|---|---|
| `--audio` | `[audio] file` | Each prayer that has no file of its own | `"Adhan-Makkah1.mp3"` |
| `--fajr-audio` | `[prayers.fajr] file` | Fajr | `"Adhan-fajr.mp3"` |
| `--dhuhr-audio`, `--asr-audio`, `--maghrib-audio`, `--isha-audio` | `[prayers.dhuhr] file`, and the same for `asr`, `maghrib` and `isha` | That prayer | The `[audio] file` |

For example, this command plays `Adhan-Madinah.mp3` for Isha:

```bash
python3 ~/adhan/updateAzaanTimers.py --isha-audio Adhan-Madinah.mp3
```

The script makes sure that the file of each prayer that is on is there and that it can read
the file. A file name must not contain `%`, `#` or a control character. In `adhan.toml`, put
the file name in double quotes. Write a `\` in a file name as `\\`.

### Lead-in of silence
Some speakers go to sleep when they play no sound. Such a speaker can need some time to
wake up, and then it does not play the start of the adhan. A lead-in plays seconds of
silence before the adhan, so the speaker is awake when the adhan starts.

| Command line | `adhan.toml` | Values | Default |
|---|---|---|---|
| `--leadin-seconds` | `[audio] leadin_seconds` | A whole number from `0` to `10` | `0` (no silence) |

For example:

```bash
python3 ~/adhan/updateAzaanTimers.py --leadin-seconds 2
```

`playAzaan.sh` plays `media/silence-1s.wav` one time for each second. If that file is not
there, it plays the adhan without the lead-in. With a lead-in, each adhan job has one more
number after the player, for example `... 0 vlc 2 >> ...`.

## Rules: play a file at a time
A rule plays an audio file at a time that you select: a fixed time, or a time before or
after a prayer. A rule can play every day or only on some days. You write the rules in
`adhan.toml`. There is no command-line argument for them. Each rule starts with the line
`[[rule]]`:

```toml
[[rule]]
name = "Surah Baqarah"
days = ["fri"]
at = "07:00"
file = "002-surah-baqarah-mishary.mp3"
volume = 0

[[rule]]
name = "Surah Kahf"
days = ["fri"]
at = "dhuhr - 30min"
file = "018-kahf.mp3"

[[rule]]
name = "Evening dua"
at = "maghrib + 10min"
file = "dua.mp3"
enabled = false
```

* The first rule plays Surah Al-Baqarah every Friday at 07:00. The `media` directory has
  this file.
* The second rule plays Surah Al-Kahf every Friday, 30 minutes before Dhuhr.
* The third rule plays a dua every day, 10 minutes after Maghrib. It is off.

`018-kahf.mp3` and `dua.mp3` are examples. They are not in the `media` directory. Before you
use these rules, put your files in the `media` directory.

| Key | Required | Values | Default |
|---|---|---|---|
| `name` | Yes | A name on one line. Each rule must have a different name. The output of the script shows it. | |
| `at` | Yes | A fixed time, `"HH:MM"`, for example `"07:00"`. Or a time before or after a prayer, `"<prayer> - <N>min"` or `"<prayer> + <N>min"`, for example `"dhuhr - 30min"`. The prayer is `fajr`, `sunrise`, `dhuhr`, `asr`, `maghrib` or `isha`. | |
| `days` | No | A list of days: `"mon"`, `"tue"`, `"wed"`, `"thu"`, `"fri"`, `"sat"`, `"sun"`. For example `["fri"]` or `["sat", "sun"]`. | Every day |
| `file` | Yes | The name of a file in the `media` directory, or the full path of a file, the same as an [adhan file](#audio-files). | |
| `volume` | No | A whole number of millibels, the same as the [adhan volume](#volume). | The `[audio] volume` |
| `enabled` | No | `true` or `false`. A rule that is off has no job. | `true` |

A rule plays its file in the same way as an adhan: with `playAzaan.sh`, the selected
[player](#choosing-the-player) and [lead-in](#lead-in-of-silence), and the
[hooks](#configuring-custom-actions-beforeafter-adhan).

A time before or after a prayer starts from the time of the adhan of that prayer. Thus it
includes the [offset](#offsets) of that prayer. It is also correct for a prayer that is
[off](#turn-a-prayer-on-or-off). Sunrise has no adhan and no offset. Each night, the script
calculates the time again, as it does for the adhan.

The script stops and changes nothing if a rule is not correct, for example:
* A key is not in the table above, or a value has the wrong type.
* `at` is not a correct time, or it has an unknown prayer.
* A day is not in the list above.
* Two rules have the same name.
* The file of a rule that is on is not there, or the script cannot read it.
* A time before or after a prayer is before 00:00 or after 23:59. A rule plays on the
  same day as its prayer.

Each rule that is on has one job in the crontab. The job plays only on the days of the
rule. For example, the Surah Baqarah rule gives this job:

```
0 7 * * 5 /home/USER/adhan/playAzaan.sh /home/USER/adhan/media/002-surah-baqarah-mishary.mp3 0 vlc >> /home/USER/adhan/adhan.log 2>&1 # rpiAdhanClockJob
```

### A rule before 03:15
The script runs each night at 03:15. A job at a time before 03:15 plays after the next
midnight, before the next run. Cron checks the day when it plays the job, so the rule
plays on its own days only. The time of a rule before or after a prayer comes from the
last run, the same as the time of the adhan. Thus a rule "fajr - 150min" at 03:01 on a
Friday has the time of Thursday's Fajr. A prayer time changes by approximately 1 minute
or less in one day. After a reboot, the script runs again and gives the same jobs.

### The old [surah_baqarah] table
Before [#43](https://github.com/rehanhaider/adhan/issues/43), Surah Baqarah had its own
table in `adhan.toml`, `[surah_baqarah]`. The script does not read this table now. If
your `adhan.toml` has it, the script stops and changes nothing. The output gives the rule
that you must write in place of the table. For example, replace:

```toml
[surah_baqarah]
enabled = true
volume = 0
```

with:

```toml
[[rule]]
name = "Surah Baqarah"
days = ["fri"]
at = "07:00"
file = "002-surah-baqarah-mishary.mp3"
volume = 0
```

If the table had `enabled = false`, delete it, or add `enabled = false` to the rule.

## Choosing the player
The adhan can play through VLC (`cvlc`) or the PulseAudio `paplay`. VLC is the default.

| Command line | `adhan.toml` | Values | Default |
|---|---|---|---|
| `--player` | `[audio] player` | `"vlc"` or `"paplay"` | `"vlc"` |

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
