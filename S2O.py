from sys import exit
import logging
import os
import re
import shutil
from pathlib import Path
import traceback
import hashlib # Used to create a checksum of a file, to check if we've already indexed this one before. I wasn't sure what other way to uniquely identify different versions of the same song.



### Begin User Variables ###
step_songs_folder = Path("C:\\Games\\StepMania 5\\Songs")
osu_songs_folder = Path("E:\\osu!\\Songs")
# Locations of the stepmania songs folder and the osu mania songs folder.


song_names = ["grea", "feAr"]
# If you only want to convert specific songs or artists, input their names here. Case insensitive.
# If you put in something that can match multiple results, it will convert ALL matches.
# For example, putting in the letter "s" will match all songs that contain an s.


DELETE_ALL_SOUP_MAPS = False
# If this is True, it will delete every map that has been created by my program, SOUP.


### End User Variables ###



# Things I want to add:
# A report of all songs converted, and all songs skipped, along with their reason for being skipped.
# More file support, ofc.


def md5(fname):
	# Used to create a checksum of a file.
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def ConvertSMToOSU(osuSongsDir, stepSongsDir, songNames):
	"""
	:param osuSongsDir: Directory of Osu songs
	:param stepSongsDir: Directory of Stepmania songs.
	:param songNames: An array containing strings of songs to convert. Convert all songs if empty.
	"""
	### Begin Osu Template Data ###
	# The things that you should replace in this template:
	# AUDIO_NAME, PREV_TIME, SONG_TITLE, SONG_AUTHOR, BACKGROUND_FILE, MAP_AUTHOR, TIMING, OBJECTS, DIFF_NAME
	osu_file_template = """osu file format v14

	[General]
	AudioFilename: AUDIO_NAME
	AudioLeadIn: 0
	PreviewTime: PREV_TIME
	Countdown: 0
	SampleSet: Soft
	StackLeniency: 0.7
	Mode: 3
	LetterboxInBreaks: 0
	SpecialStyle: 0
	WidescreenStoryboard: 1

	[Editor]
	DistanceSpacing: 1.2
	BeatDivisor: 6
	GridSize: 4
	TimelineZoom: 1.2

	[Metadata]
	Title:SONG_TITLE
	TitleUnicode:SONG_TITLE
	Artist:SONG_AUTHOR
	ArtistUnicode:SONG_AUTHOR
	Creator:MAP_AUTHOR
	Version:DIFF_NAME
	Source:
	Tags:StepMania
	BeatmapID:0
	BeatmapSetID:0

	[Difficulty]
	HPDrainRate:7
	CircleSize:4
	OverallDifficulty:7.5
	ApproachRate:5
	SliderMultiplier:1.4
	SliderTickRate:2

	[Events]
	//Background and Video events
	0,0,"BACKGROUND_FILE",0,0
	//Break Periods
	//Storyboard Layer 0 (Background)
	//Storyboard Layer 1 (Fail)
	//Storyboard Layer 2 (Pass)
	//Storyboard Layer 3 (Foreground)
	//Storyboard Layer 4 (Overlay)
	//Storyboard Sound Samples

	[TimingPoints]
	TIMING

	[HitObjects]
	OBJECTS"""

	bpmTemplate = "POS,BPM,4,2,1,60,1,0"  # The second value is essentially the BPM. It is calculated as 60000 / BPM
	hitTemplate = "{0},192,{1},{2},0,{3}0:0:0:0:\n"  # 1 = key, 2 = Time, 3 = Type, 4 = special object params. See OSU file specs.txt for more info on this
	### End Template Data ###


	stepSongsDir = [x for x in stepSongsDir.iterdir() if x.is_dir()] # Get all folders contained in this directory.
	for group in stepSongsDir:
		songs = [x for x in group.iterdir() if x.is_dir()]
		for song in songs:
			try:
				# Check if this song has a .sm file we can read.
				# There is a new file format, .ssc, but I don't have many of these files to justify converting them right now.
				# As of right now, I haven't figured out how to handle BPM changes or STOPS in .sm files, so I'm going to ignore maps that contain these.
				_sm = list(Path(song).glob("*.sm"))
				if not _sm:
					logging.warning(f"Folder has no .sm file: {song}")
					continue
				with open(_sm[0]) as f:
					map = f.read()
				map = re.sub(patterns["lineComments"], "", map) # Remove all comments from file.

				# Segment the map up into its header and body
				_i = re.search(patterns["notes"], map).start(0) # Finds where the body begins (The first notes segment)
				header = map[:_i] # Contains metadata about the map
				body = map[_i:]

				# Separate the body up into each difficulty.
				_segs = re.findall(patterns["mapFull"], body) # Segment the body up into the different maps.
				difficultyMap = [] # An array we'll store the different difficulties in
				for d in _segs:
					difficultyMap.append(d[0])


				# Check if this map has BPM changes or stops. If it does, I can't convert it (yet)
				bpm = re.search(patterns["bpms"], map)
				bpm = bpm.group(2)
				if "," in bpm:
					logging.info(f"File has BPM changes. I'm not smart enough to do these yet :( {song}")
					continue
				_i = re.search(r"=", bpm).end(0)
				bpm = float(bpm[_i:])

				if re.search(patterns["stops"], map): # Checks if there's a number directly after the #STOPS segment.
					logging.info(f"File has STOPS. I'm not smart enough for these either..: {song}")
					continue

				### Start Header Data ###
				# Data collected from the header of the stepmania file.
				title = ""			# Name of the song
				artist = ""			# Artist of the song
				previewTime = 0		# What point in the song to play on preview
				audioFile = ""		# Audio file name. Duh.
				bgFile = ""			# Name of the background image.
				offset = 0			# I'm not sure what time this is in, so for now I'll assume it's in seconds.

				title = re.search(patterns["title"], header).group(2)
				artist = re.search(patterns["artist"], header).group(2)
				audioFile = re.search(patterns["audioFile"], header).group(2)
				bgFile = re.search(patterns["background"], header).group(2)
				previewTime = int(float(re.search(patterns["preview"], header).group(2)) * 1000)
				offset = float(re.search(patterns["offset"], header).group(2)) * 1000

				thisSong = f"{artist} - {title}".lower()
				inNames = True # If the name of the song is in the list of songs the user wishes convert.
				for n in song_names: # Will always be True if song_names is empty.
					inNames = False
					if n in thisSong:
						inNames = True
						break

				if not inNames: # Skip this song if it isn't in the list of names.
					break
				### End Header Data ###

				# check if converted map exists already
				checksum = md5(_sm[0])
				folderName = f"SOUP {artist} - {title} {checksum}"
				_fld = "{}\\{}".format(osuSongsDir, folderName)
				# Overwrite folder if it exists.
				if os.path.exists(_fld):
					logging.info(f"Overwriting folder {_fld}")
					shutil.rmtree(_fld)

				os.mkdir(_fld)

				for difmap in difficultyMap:
					### Start Map Data ###
					mapSegged = re.search(patterns["mapSeg"], difmap)
					gameMode = mapSegged.group(1)
					mapAuthor = mapSegged.group(2)
					diffName = mapSegged.group(3)
					diffNum = mapSegged.group(4)
					noteData = mapSegged.group(6)
					osuFileName = f"{artist} - {title} [{diffName} {diffNum}]"

					if gameMode != "dance-single": # We're only parsing for 4K right now.
						logging.info(f"Map in {song} is not dance-single, skipping...")
						continue

					# Fill in the template osu file
					copy = osu_file_template # Get a copy of the template to modify.
					copy = copy.replace("AUDIO_NAME", audioFile)
					copy = copy.replace("PREV_TIME", str(previewTime))
					copy = copy.replace("SONG_TITLE", title)
					copy = copy.replace("SONG_AUTHOR", artist)
					copy = copy.replace("BACKGROUND_FILE", bgFile)
					copy = copy.replace("MAP_AUTHOR", mapAuthor)
					copy = copy.replace("DIFF_NAME", f"{diffName} ({diffNum})")

					tickBPM = 60000 / bpm # Format Step BPM to Osu BPM
					bpmCopy = bpmTemplate
					bpmCopy = bpmCopy.replace("POS", str(int(offset * 1000)))
					bpmCopy = bpmCopy.replace("BPM", str(tickBPM))
					copy = copy.replace("TIMING", bpmCopy)

					bpms = 60000 / bpm # How much time one quarter note takes in milliseconds.


					# Collect note data.
					_segs = re.findall(patterns["measureSeg"], noteData)
					hitObjects = "" # A string that contains ALL of the osu hit objects.
					holdTime = [0, 0, 0, 0] # When the command for "hold this note" was last triggered, from left to right.
					lastTime = offset # This is the time of the last note. We start at the offset.

					for _measure in _segs:
						_lines = _measure.splitlines()
						beats = len(_lines) # Check how many lines are in this measure.
						noteMult = 4 / beats # This basically checks if we're using 4ths, 8ths, 16ths etc so we can calculate how long a note is
						for _line in _lines: # check each line
							_i = 0
							for _note in _line: # check each key
								K = 64 + (_i * 128) # Which key this note is, for 4K. From left to right.
								M = int(lastTime) # The time.
								T = 0 # Key type
								P = "" # Special params

								if _note == "0": # Nothing happens on this note.
									pass
								elif _note == "1": # Normal note
									T = 1 # Normal note. See OSU file specs.txt
									P = ""
									hitObjects += hitTemplate.format(K, M, T, P)
								elif _note == "2": # Hold start. Thankfully osu objects don't need to be sequential to work, so I can withhold this till the hold end is provided.
									holdTime[_i] = M
								elif _note == "3": # Hold end
									P = "{}:".format(M)
									T = 128
									hitObjects += hitTemplate.format(K, holdTime[_i], T, P) # Hold start
								else: # Other note that doesn't translate to mania.
									pass

								_i += 1
							lastTime += bpms * noteMult
					copy = copy.replace("OBJECTS", hitObjects)
					#break
					### End Map Data ###

					# Add audio, visual and map files to the osu songs directory.
					# Background
					if bgFile != "":
						bg = str(song) + "\\{}".format(bgFile)
						shutil.copy2(bg, _fld)

					# Audio
					audio = str(song) + "\\{}".format(audioFile)
					shutil.copy2(audio, _fld)

					# Map
					with open(f"{_fld}\\{osuFileName}.osu", "w+") as f: # Create the .osu map file..
						f.write(copy) # Write the created map to the map file.

			except Exception as e:
				traceback.print_exc()
				logging.error(f"Unknown error encountered. File: {song}\n{e}")

		break


def DeleteSoupMaps(stepSongsDir):
	osuSoups = [x for x in osu_songs_folder.iterdir() if x.is_dir() and x.name[:5] == "SOUP "]
	for soup in osuSoups:
		logging.info(f"Deleted {soup}")
		print(f"Deleted {soup}")
		shutil.rmtree(soup)
	return


if __name__ == "__main__":
	logging.basicConfig(filename="ConversionReport.log", filemode="w", level=logging.INFO, format="%(levelname)s: %(message)s")

	### Being Regex Search Patterns ###
	patterns = {
		"title": re.compile(r"(#TITLE:)(.*)(;)"),
		"artist": re.compile(r"(#ARTIST:)(.*)(;)"),
		"audioFile": re.compile(r"(#MUSIC:)(.*)(;)"),
		"background": re.compile("(#BACKGROUND:)(.*)(;)"),
		"preview": re.compile(r"(#SAMPLESTART:)([\d\.]*)(;)"),
		"offset": re.compile(r"(#OFFSET:)([\d\.]*)(;)"),
		"bpms": re.compile(r"(#BPMS:)(.*)(;)"),
		"stops": re.compile(r"(#STOPS:)\d"),

		"notes": re.compile(r"#NOTES:"),
		"mapFull": re.compile(r"((#NOTES:)([^;]*);)"),
		# Dear God, o holy one. Please forgive me for the sin I have committed. Understand that I do this not out of ignorance of the pain it may cause,
		# but out of a lack of concern for life and its beauty. I am tainted by the luxuries of laziness and shall pay the price in eternity.
		"mapSeg": re.compile(r"(?:#NOTES:)(?:[\n\s]*)([^\n\s]*?)(?::[\n\s]*)([^\n\s]*?)(?::[\n\s]*)([^\n\s]*?)(?::[\n\s]*)([^\n\s]*?)(?::[\n\s]*)([^\n\s]*?)(?::[\n\s]*)([\d\n\s,;]*)"),
		# Header group layout: 1: Game mode 2: Map artist 3: Difficulty name 4: Difficulty number 5: Groove bullshit 6: Note data
		"measureSeg": re.compile(r"((?:[\d]+\n)*)(?:[,;])"),  # Splits up the note data into its measures.

		"lineComments": re.compile(r"(\/\/.*)"),  # Common thing, optimize this somehow?
	}
	### End Regex Search Patterns ###

	# User input checks
	DirsExist = True

	if not os.path.exists(step_songs_folder):
		print("Cannot find Stepmania songs folder.")
		logging.error("Cannot find Stepmania folder.")
		DirsExist = False
	elif not os.path.exists(osu_songs_folder) and DELETE_ALL_SOUP_MAPS is False:
		print("Cannot find Osu songs folder.")
		logging.error("Cannot find Osu songs folder.")
		DirsExist = False

	for i in range(len(song_names)):
		song_names[i] = song_names[i].lower()  # Make inputs lowercase.


	if DirsExist:
		if DELETE_ALL_SOUP_MAPS:
			DeleteSoupMaps(step_songs_folder)
		else:
			ConvertSMToOSU(osu_songs_folder, step_songs_folder, song_names)