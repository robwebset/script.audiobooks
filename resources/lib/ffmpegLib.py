# -*- coding: utf-8 -*-
import sys
import locale
import re
import subprocess
import traceback
import xbmc
import xbmcvfs
import xbmcaddon

from ctypes import CDLL, RTLD_GLOBAL
from ctypes import Structure, POINTER
from ctypes import c_int, c_uint, c_char, c_char_p, c_void_p, c_int64

from settings import Settings
from settings import log
from settings import os_path_join
from settings import dir_exists

ADDON = xbmcaddon.Addon(id='script.audiobooks')


class AVRational(Structure):
    _fields_ = [
        ('num', c_int),
        ('den', c_int)
    ]


class AVDictionary(Structure):
    pass


class AVDictionaryEntry(Structure):
    _fields_ = [
        ('key', c_char_p),
        ('value', c_char_p)
    ]


class AVChapter(Structure):
    _fields_ = [
        ('id', c_int),
        ('time_base', AVRational),
        ('start', c_int64),
        ('end', c_int64),
        ('metadata', POINTER(AVDictionary)),
    ]


class AVInputFormat(Structure):
    pass


class AVFormatContext(Structure):
    # Note: Not complete, only up until the values required, needs that many as it shifts the memory bytes
    _fields_ = [
        ('av_class', c_void_p),
        ('iformat', c_void_p),
        ('oformat', c_void_p),
        ('priv_data', c_void_p),
        ('pb', c_void_p),
        ('ctx_flags', c_int),
        ('nb_streams', c_uint),
        ('streams', c_void_p),
        ('filename', c_char * 1024),
        ('start_time', c_int64),
        ('duration', c_int64),
        ('bit_rate', c_int),
        ('packet_size', c_uint),
        ('max_delay', c_int),
        ('flags', c_int),
        ('probesize', c_uint),
        ('max_analyze_duration', c_int),
        ('key', c_void_p),
        ('keylen', c_int),
        ('nb_programs', c_uint),
        ('programs', c_void_p),
        ('video_codec_id', c_int),
        ('audio_codec_id', c_int),
        ('subtitle_codec_id', c_int),
        ('max_index_size', c_uint),
        ('max_picture_buffer', c_uint),
        ('nb_chapters', c_uint),
        ('chapters', POINTER(POINTER(AVChapter))),
        ('metadata', POINTER(AVDictionary))
    ]


# Between ffmpeg v2 and ffmpeg v3 the structure changes slightly
class AVFormatContext3(Structure):
    # Note: Not complete, only up until the values required, needs that many as it shifts the memory bytes
    _fields_ = [
        ('av_class', c_void_p),
        ('iformat', c_void_p),
        ('oformat', c_void_p),
        ('priv_data', c_void_p),
        ('pb', c_void_p),
        ('ctx_flags', c_int),
        ('nb_streams', c_uint),
        ('streams', c_void_p),
        ('filename', c_char * 1024),
        ('start_time', c_int64),
        ('duration', c_int64),
        ('bit_rate', c_int64),
        ('packet_size', c_uint),
        ('max_delay', c_int),
        ('flags', c_int),
        ('probesize', c_int64),
        ('max_analyze_duration', c_int64),
        ('key', c_void_p),
        ('keylen', c_int),
        ('nb_programs', c_uint),
        ('programs', c_void_p),
        ('video_codec_id', c_int),
        ('audio_codec_id', c_int),
        ('subtitle_codec_id', c_int),
        ('max_index_size', c_uint),
        ('max_picture_buffer', c_uint),
        ('nb_chapters', c_uint),
        ('chapters', POINTER(POINTER(AVChapter))),
        ('metadata', POINTER(AVDictionary))
    ]


FFMPEG_INSTANCE = None
FFMPEG_VERSION = 2


# Utility class for ffmpeg operations
class FfmpegBase():
    @staticmethod
    def createHandler():
        global FFMPEG_INSTANCE
        if FFMPEG_INSTANCE is None:
            # If set to None or Library, then we give the library a go
            # For None, if we are on Windows, then the library files are already there
            if Settings.getFFmpegSetting() == Settings.FFMPEG_LIB:
                log("FfmpegUtils: Loading Audiobook details by library")
                FFMPEG_INSTANCE = FFMpegLib()
                if not FFMPEG_INSTANCE.isSupported():
                    log("FfmpegUtils: Loading by library not supported")
                    FFMPEG_INSTANCE = None

            if FFMPEG_INSTANCE in [None, ""]:
                log("FfmpegUtils: Loading Audiobook details by executable")
                FFMPEG_INSTANCE = FfmpegCmd()
                if not FFMPEG_INSTANCE.isSupported():
                    log("FfmpegUtils: Loading by executable not supported")
                    FFMPEG_INSTANCE = None

        return FFMPEG_INSTANCE

    def getMediaInfo(self, mediaName, coverTempName=None):
        return None

    def _getDefaultChapterName(self, chapterNumber=''):
        chapterTitle = "%s %d" % (ADDON.getLocalizedString(32017), chapterNumber)
        return chapterTitle


# Class to handle using the libraries
class FFMpegLib(FfmpegBase):
    def __init__(self):
        self.av_register_all = None
        self.avformat_open_input = None
        self.avformat_close_input = None
        self.avformat_find_stream_info = None
        self.av_dict_get = None

        # Get the location of all of the libraries
        libLocation = None
        if Settings.getFFmpegSetting() == Settings.FFMPEG_LIB:
            libLocation = FFMpegLib.getPlatformLibFiles(Settings.getFFmpegLibraryLocation())

        # Make sure we have the libraries expected
        if libLocation in [None, ""]:
            return

        try:
            # Need to load in the following order, otherwise things do not work
            # avutil, avresample, avcodec, avformat
            avutil = CDLL(libLocation['avutil'], mode=RTLD_GLOBAL)
            CDLL(libLocation['swresample'], mode=RTLD_GLOBAL)
            CDLL(libLocation['avcodec'], mode=RTLD_GLOBAL)
            avformat = CDLL(libLocation['avformat'], mode=RTLD_GLOBAL)

            self.av_register_all = avformat.av_register_all
            self.av_register_all.restype = None
            self.av_register_all.argtypes = []

            self.avformat_open_input = avformat.avformat_open_input
            self.avformat_open_input.restype = c_int
            if FFMPEG_VERSION == 3:
                self.avformat_open_input.argtypes = [POINTER(POINTER(AVFormatContext3)), c_char_p, POINTER(AVInputFormat), POINTER(POINTER(AVDictionary))]
            else:
                self.avformat_open_input.argtypes = [POINTER(POINTER(AVFormatContext)), c_char_p, POINTER(AVInputFormat), POINTER(POINTER(AVDictionary))]

            self.avformat_close_input = avformat.avformat_close_input
            self.avformat_close_input.restype = None
            if FFMPEG_VERSION == 3:
                self.avformat_close_input.argtypes = [POINTER(POINTER(AVFormatContext3))]
            else:
                self.avformat_close_input.argtypes = [POINTER(POINTER(AVFormatContext))]

            self.avformat_find_stream_info = avformat.avformat_find_stream_info
            self.avformat_find_stream_info.restype = c_int
            if FFMPEG_VERSION == 3:
                self.avformat_find_stream_info.argtypes = [POINTER(AVFormatContext3), POINTER(POINTER(AVDictionary))]
            else:
                self.avformat_find_stream_info.argtypes = [POINTER(AVFormatContext), POINTER(POINTER(AVDictionary))]

            self.av_dict_get = avutil.av_dict_get
            self.av_dict_get.restype = POINTER(AVDictionaryEntry)
            self.av_dict_get.argtypes = [POINTER(AVDictionary), c_char_p, POINTER(AVDictionaryEntry), c_int]

            self.av_log_set_level = avutil.av_log_set_level
            self.av_log_set_level.restype = None
            self.av_log_set_level.argtypes = [c_int]
        except:
            log("FFMpegLib: Failed to load ffmpeg libraries: %s" % traceback.format_exc(), xbmc.LOGERROR)
            self.av_register_all = None
            self.avformat_open_input = None
            self.avformat_close_input = None
            self.avformat_find_stream_info = None
            self.av_dict_get = None

    # Check if using libraries is supported
    def isSupported(self):
        if self.av_register_all in [None, ""]:
            return False
        return True

    # Get the information for a given media file
    def getMediaInfo(self, mediaName, coverTempName=None):
        log("FFMpegLib: Get information for %s" % mediaName)

        returnData = None
        pFormatCtx = None
        try:
            # Make sure we have the libraries expected
            if self.av_register_all in [None, ""]:
                return None

            # Disable all logging from ffmpeg as that will go to standard out
            try:
                self.av_log_set_level(-8)
            except:
                log("FFMpegLib: Failed to disable ffmpeg logging")

            self.av_register_all()

            if FFMPEG_VERSION == 3:
                pFormatCtx = POINTER(AVFormatContext3)()
            else:
                pFormatCtx = POINTER(AVFormatContext)()

            # Before using the media filename need to ensure it is encoded
            # as ascii as that is what ffmpeg expects
#             decodedMediaName = mediaName
#             try:
#                 decodedMediaName = mediaName.encode(locale.getpreferredencoding())
#             except:
#                 log("FfmpegCmd: Failed file encoding 1, using default")
#            try:
#                mediaName = mediaName.decode('utf-8').encode(locale.getpreferredencoding())
#            except:
#                log("FfmpegCmd: Failed file encoding 1, using default")
#                try:
#                    mediaName = mediaName.encode(locale.getpreferredencoding())
#                except:
#                    log("FfmpegCmd: Failed file encoding 2, using default")
#                    try:
#                        mediaName = mediaName.decode().encode(locale.getpreferredencoding())
#                    except:
#                        log("FfmpegCmd: Failed file encoding 3, using default")

            res = self.avformat_open_input(pFormatCtx, mediaName, None, None)
            if res:
                log("FFMpegLib: Error returned from avformat_open_input: %s" % str(res))
                return None

            # Need to load the stream information otherwise the duration is not correct
            res = self.avformat_find_stream_info(pFormatCtx, None)
            if res < 0:
                log("FFMpegLib: Error returned from avformat_find_stream_info: %s" % str(res))
                return None

            # Total duration in seconds
            duration = 0
            if pFormatCtx.contents.duration not in [None, ""]:
                duration = int(pFormatCtx.contents.duration) / 1000000

            # Get the global metadata
            mainInfo = self._getMetadata(pFormatCtx.contents.metadata)

            title = ""
            if 'title' in mainInfo:
                title = mainInfo['title']
            album = ""
            if 'album' in mainInfo:
                album = mainInfo['album']
            artist = ""
            if 'artist' in mainInfo:
                artist = mainInfo['artist']

            log("FFMpegLib: Title = %s, Album = %s, Duration = %d" % (title, album, duration))
            chapters = []

            for i in range(pFormatCtx.contents.nb_chapters):
                chapter = pFormatCtx.contents.chapters[i]

                if chapter in [None, ""]:
                    continue

                # Need the offset multiplier for the chapter timings
                rat = 1
                if chapter.contents.time_base not in [None, ""]:
                    if (chapter.contents.time_base.num not in [None, ""]) and (chapter.contents.time_base.den not in [None, ""]):
                        rat = float(chapter.contents.time_base.num) / float(chapter.contents.time_base.den)

                # Get the metadata for the chapter
                chapterInfo = self._getMetadata(chapter.contents.metadata)

                chapterTitle = ""
                if 'title' in chapterInfo:
                    chapterTitle = chapterInfo['title']
                    if chapterTitle is None:
                        chapterTitle = ""

                # Get the time in seconds
                start_time = 0
                if chapter.contents.start not in [None, ""]:
                    start_time = int(float(chapter.contents.start) * rat)
                end_time = 0
                if chapter.contents.end not in [None, ""]:
                    end_time = int(float(chapter.contents.end) * rat)

                log("FFMpegLib: %d. ChapterTitle = %s, start = %d, end = %d" % (i + 1, chapterTitle, start_time, end_time))

                detail = {'title': chapterTitle.strip(), 'startTime': start_time, 'endTime': end_time, 'duration': end_time - start_time}
                chapters.append(detail)

            returnData = {'title': title, 'album': album, 'artist': artist, 'duration': duration, 'chapters': chapters}
        except:
            log("FFMpegLib: Failed to get data using ffmpeg library for file %s with error %s" % (mediaName, traceback.format_exc()), xbmc.LOGERROR)

        try:
            # Tidy up the data in the library
            if pFormatCtx:
                self.avformat_close_input(pFormatCtx)
        except:
            pass

        return returnData

    # Find the required library from a given directory
    @staticmethod
    def getPlatformLibFiles(parentDir):
        if parentDir in [None, ""]:
            return None

        log("FFMpegLib: Looking for libraries in %s" % parentDir)
        libLocation = {}

        # Check if the directory exists
        if dir_exists(parentDir):
            # List the contents of the directory
            dirs, files = xbmcvfs.listdir(parentDir)
            for aFile in files:
                if 'avutil' in aFile:
                    libLocation['avutil'] = os_path_join(parentDir, aFile)
                    log("FFMpegLib: Found avutil library: %s" % libLocation['avutil'])
                elif 'swresample' in aFile:
                    libLocation['swresample'] = os_path_join(parentDir, aFile)
                    log("FFMpegLib: Found swresample library: %s" % libLocation['swresample'])
                elif 'avcodec' in aFile:
                    libLocation['avcodec'] = os_path_join(parentDir, aFile)
                    log("FFMpegLib: Found avcodec library: %s" % libLocation['avcodec'])
                elif 'avformat' in aFile:
                    libLocation['avformat'] = os_path_join(parentDir, aFile)
                    log("FFMpegLib: Found avformat library: %s" % libLocation['avformat'])
        else:
            log("FFMpegLib: Directory not found %s" % parentDir)

        # Make sure we found all of the libraries
        if len(libLocation) < 4:
            return None

        # Check if this is version 3 of ffmpeg as things are slightly different
        if '-55' in libLocation['avutil']:
            global FFMPEG_VERSION
            FFMPEG_VERSION = 3

        return libLocation

    # Get media metadata
    def _getMetadata(self, meta):
        if meta in [None, ""]:
            return {}

        done = False
        metaDict = {}
        tag = POINTER(AVDictionaryEntry)()

        while not done:
            try:
                tag = self.av_dict_get(meta, ''.encode('ascii'), tag, 2)
            except:
                log("FFMpegLib: Failed to get metadata with error: %s" % traceback.format_exc(), xbmc.LOGERROR)
                tag = None

            if tag:
                log("FFMpegLib: Found key %s" % str(tag.contents.key))
                # make sure all the keys are lower case
                metaDict[tag.contents.key.lower()] = tag.contents.value
            else:
                done = True

        # return: a dict with key, value = metadata key, metadata value
        return metaDict


class FfmpegCmd(FfmpegBase):
    def __init__(self):
        # Check to see if ffmpeg is enabled
        self.ffmpeg = Settings.getFFmpegExecLocation()

        if self.ffmpeg in [None, ""]:
            log("FfmpegCmd: ffmpeg not enabled")
        else:
            log("FfmpegCmd: ffmpeg location %s" % self.ffmpeg)

    # Check if using executable is supported
    def isSupported(self):
        if self.ffmpeg in [None, ""]:
            return False
        return True

    def getMediaInfo(self, mediaName, coverTempName=None):

        # Use ffmpeg to read the audio book and extract all of the details
        startupinfo = None
        if sys.platform.lower() == 'win32':
            # Need to stop the dialog appearing on windows
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        info = None
        try:
            # Generate the ffmpeg command
            ffmpegCmd = [self.ffmpeg, '-hide_banner', '-y', '-i', mediaName]

            # Handle non ascii characters in the file name path
            try:
                ffmpegCmd[4] = ffmpegCmd[4].decode('utf-8').encode(locale.getpreferredencoding())
            except:
                log("FfmpegCmd: Failed file system encoding ffmpeg command 1, using default")
                try:
                    ffmpegCmd[4] = ffmpegCmd[4].encode(locale.getpreferredencoding())
                except:
                    log("FfmpegCmd: Failed file system encoding ffmpeg command 2, using default")
                    try:
                        ffmpegCmd[4] = ffmpegCmd[4].decode().encode(locale.getpreferredencoding())
                    except:
                        log("FfmpegCmd: Failed file system encoding ffmpeg command 3, using default")

            # Add the output image to the command line if it is needed
            if coverTempName is not None:
                try:
                    coverTempName = coverTempName.decode('utf-8').encode(locale.getpreferredencoding())
                except:
                    log("FfmpegCmd: Failed file system encoding coverTempName ffmpeg command 1, using default")
                    try:
                        coverTempName = coverTempName.encode(locale.getpreferredencoding())
                    except:
                        log("FfmpegCmd: Failed file system encoding coverTempName ffmpeg command 2, using default")
                ffmpegCmd.append(coverTempName)

            # Make the ffmpeg call
            try:
                log("FfmpegCmd: running subprocess command %s" % str(ffmpegCmd))
                info = subprocess.check_output(ffmpegCmd, shell=False, startupinfo=startupinfo, stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as error:
                # This exception will be thrown if ffmpeg prints to STDERR, which it will do if
                # you try and run the command without an output (i.e. image file), but in most
                # cases it does actually have the information we need
                log("FfmpegCmd: CalledProcessError received, processing remaining output")
                info = error.output
            except:
                # Unfortunately there are still systems that use Python 2.6 which does not
                # have check_output, so it that fails, we just use Popen
                log("FfmpegCmd: subprocess failed, trying Popen: %s" % traceback.format_exc())
                proc = subprocess.Popen(ffmpegCmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                info = ""
                for outStr in proc.communicate():
                    if outStr not in [None, ""]:
                        info = "%s%s\n" % (info, outStr)
        except:
            log("FfmpegCmd: Failed to get data using ffmpeg for file %s with error %s" % (mediaName, traceback.format_exc()), xbmc.LOGERROR)

        # Now the command has been run
        ffmpegOutput = None
        if info not in [None, ""]:
            ffmpegOutput = self._processFFmpegOutput(info)

        if ffmpegOutput in [None, ""]:
            try:
                log("FfmpegCmd: Still no output from ffmpeg, trying Popen with joined arguments")
                joinedCmd = ' '.join(ffmpegCmd)
                proc = subprocess.Popen(joinedCmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                info = ""
                for outStr in proc.communicate():
                    if outStr not in [None, ""]:
                        info = "%s%s\n" % (info, outStr)
                if info not in [None, ""]:
                    ffmpegOutput = self._processFFmpegOutput(info)
            except:
                log("FfmpegCmd: Failed to get data using ffmpeg for %s with error %s" % (joinedCmd, traceback.format_exc()))

        return ffmpegOutput

    # Handles the processing of the text output of ffmpeg
    def _processFFmpegOutput(self, info):
        log("FfmpegCmd: FFmpeg info is: %s" % info)

        # The pattern to find chapter info
        chapter_pattern = re.compile('^Chapter #(\d+)[\.:](\d+): start (\d+\.\d+), end (\d+\.\d+)$', re.IGNORECASE)
        # The pattern that finds the title for a chapter
        title_pattern = re.compile('^\s*title\s*:\s*(.*)$', re.IGNORECASE)
        album_pattern = re.compile('^\s*album\s*:\s*(.*)$', re.IGNORECASE)
        artist_pattern = re.compile('^\s*artist\s*:\s*(.*)$', re.IGNORECASE)
        # The pattern to find the total duration
        duration_pattern = re.compile('^\s*Duration\s*:\s*(.*), start', re.IGNORECASE)

        title = None
        album = None
        artist = None
        duration = None
        chapters = []
        totalDuration = None

        # Get the title from the output
        lines = info.split('\n')
        linenum = 0

        chapterNum = 1
        while linenum < len(lines):
            line = lines[linenum]
            line = line.strip()

            # ffmpeg will list the details, first as input and then as output, so we process the input
            # and then stop when we reach output
            if line.startswith('Output '):
                break

            # Check for the first title as that will be the main title
            if title in [None, ""]:
                main_title_match = title_pattern.match(line)
                if main_title_match:
                    title = main_title_match.group(1)
                    log("FfmpegCmd: Found title in ffmpeg output: %s" % title)

            if album in [None, ""]:
                main_album_match = album_pattern.match(line)
                if main_album_match:
                    album = main_album_match.group(1)
                    log("FfmpegCmd: Found album in ffmpeg output: %s" % album)

            if artist in [None, ""]:
                main_artist_match = artist_pattern.match(line)
                if main_artist_match:
                    artist = main_artist_match.group(1)
                    log("FfmpegCmd: Found artist in ffmpeg output: %s" % artist)

            if duration in [None, 0, ""]:
                main_duration_match = duration_pattern.match(line)
                if main_duration_match:
                    duration = self._getSecondsInTimeString(main_duration_match.group(1))
                    log("FfmpegCmd: Found duration in ffmpeg output: %s" % duration)

            # Chapters are listed in the following format
            # ---
            # Chapter #0:29: start 26100.000000, end 27000.000000
            # Metadata:
            #   title           : Part 30
            # ---
            chapter_match = chapter_pattern.match(line)
            # If we found a chapter, skip ahead to the title and ignore the lines between them
            if not chapter_match:
                linenum += 1
                continue

            # Now extract all of the details
            title_match = title_pattern.match(lines[linenum + 2])
            linenum += 3

            # chapter_num = chapter_match.group(1)
            # chapter_subnum = chapter_match.group(2)
            start_time = int(float(chapter_match.group(3)))
            end_time = int(float(chapter_match.group(4)))
            chapterDuration = end_time - start_time

            chapterTitle = ""
            if title_match:
                chapterTitle = title_match.group(1)

            if chapterTitle in [None, ""]:
                chapterTitle = "%s %d" % (ADDON.getLocalizedString(32017), chapterNum)

            chapterNum += 1
            log("FfmpegCmd: Chapter details. Title: %s, start_time: %s, end_time: %s, duration: %d" % (chapterTitle, start_time, end_time, chapterDuration))

            detail = {'title': chapterTitle.strip(), 'startTime': start_time, 'endTime': end_time, 'duration': chapterDuration}
            chapters.append(detail)

            # The total Duration is always the end of the last chapter
            totalDuration = end_time

        # If there is no duration, then use the last chapter duration
        if duration in [None, 0, '']:
            duration = totalDuration

        if (title in [None, ""]) and (album in [None, ""]) and (duration in [None, ""]) and (len(chapters) < 1):
            returnData = None
        else:
            returnData = {'title': title, 'album': album, 'artist': artist, 'duration': duration, 'chapters': chapters}
        return returnData

    # Converts a time string 00:00:00.00 to the total number of seconds
    def _getSecondsInTimeString(self, fullTimeString):
        # Start by splitting the time into sections
        hours = 0
        minutes = 0
        seconds = 0

        try:
            timeParts = list(reversed(fullTimeString.split(':')))
            if len(timeParts) > 2:
                hours = int(timeParts[2])
            if len(timeParts) > 1:
                minutes = int(timeParts[1])
            if len(timeParts) > 1:
                seconds = int(float(timeParts[0]))
        except:
            # time sections are not numbers
            log("FfmpegCmd: Exception Details: %s" % traceback.format_exc())
            hours = 0
            minutes = 0
            seconds = 0

        totalInSeconds = (((hours * 60) + minutes) * 60) + seconds
        log("FfmpegCmd: Time %s, splits into hours=%d, minutes=%d, seconds=%d, total=%d" % (fullTimeString, hours, minutes, seconds, totalInSeconds))

        # Return the total time in seconds
        return totalInSeconds
