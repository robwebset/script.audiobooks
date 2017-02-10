# -*- coding: utf-8 -*-
import os
import traceback
import xbmc
import xbmcvfs
import xbmcgui
import xbmcaddon
import mutagen

# Import the common settings
from settings import Settings
from settings import log
from settings import os_path_join
from settings import os_path_split
from database import AudioBooksDB
from ffmpegLib import FfmpegBase

ADDON = xbmcaddon.Addon(id='script.audiobooks')
FANART = ADDON.getAddonInfo('fanart')


# Generic class for handling audiobook details
class AudioBookHandler():
    def __init__(self, audioBookFilePath):
        self.filePath = audioBookFilePath
        self.fileName = os_path_split(audioBookFilePath)[-1]
        self.coverImage = None
        self.title = None
        self.chapters = []
        self.numChapters = 0
        self.position = -1
        self.chapterPosition = -1
        self.totalDuration = -1
        self.isComplete = None
        self.hasArtwork = -1

    def __lt__(self, other):
        return self.getTitle() < other.getTitle()

    @staticmethod
    def createHandler(audioBookFilePath):
        audiobookType = None
        # Check which type of Audiobook it is
        if audioBookFilePath.lower().endswith('.m4b'):
            audiobookType = M4BHandler(audioBookFilePath)
        else:
            audiobookType = FolderHandler(audioBookFilePath)

        return audiobookType

    def _getCopiedFileIfNeeded(self, fullPath):
        copiedFile = None
        if fullPath.startswith('smb://') or fullPath.startswith('nfs://'):
            try:
                # Copy the file to the local disk
                justFileName = os_path_split(fullPath)[-1]
                copiedFile = os_path_join(Settings.getTempLocation(), justFileName)
                copy = xbmcvfs.copy(fullPath, copiedFile)
                if copy:
                    log("AudioBookHandler: copy successful for %s" % copiedFile)
                else:
                    log("AudioBookHandler: copy failed from %s to %s" % (fullPath, copiedFile))
                    copiedFile = None
            except:
                log("AudioBookHandler: Failed to copy file %s to local directory" % fullPath)
                copiedFile = None

        return copiedFile

    def _removeCopiedFile(self, copiedFile):
        # If we had to copy the file locally, make sure we delete it
        if copiedFile not in [None, ""]:
            if xbmcvfs.exists(copiedFile):
                xbmcvfs.delete(copiedFile)

    def _readMetaData(self, inputFileName):
        log("AudioBookHandler: Reading Metadata for audio book %s" % inputFileName)

        # If the file is not local, we might need to copy it
        fullPath = inputFileName
        copiedFile = self._getCopiedFileIfNeeded(inputFileName)
        if copiedFile not in [None, ""]:
            fullPath = copiedFile

        title = ""
        album = ""
        artist = ""
        duration = -1
        try:
            try:
                fullPath = fullPath.encode('utf-8')
            except:
                pass
            mutagenFile = mutagen.File(fullPath, easy=True)

            if mutagenFile not in [None, ""]:
                # We construct an empty array for items that are not found
                emptyArray = [""]
                # Get all the available data
                title = mutagenFile.get('title', emptyArray)[0]
                album = mutagenFile.get('album', emptyArray)[0]
                artist = mutagenFile.get('artist', emptyArray)[0]
                if mutagenFile.info not in [None, ""]:
                    if mutagenFile.info.length not in [None, ""]:
                        duration = int(float(mutagenFile.info.length))
            del mutagenFile

            log("AudioBookHandler: title = %s, album = %s, duration = %d" % (title, album, duration))

            # If we have had to copy the file locally, check if we need to also
            # get the image as well, otherwise we might copy the file twice
            if copiedFile not in [None, ""]:
                if self._getExistingCoverImage() in [None, ""]:
                    self._saveAlbumArtFromMetadata(fullPath)
        except:
            log("AudioBookHandler: Failed to read metadata for audio book %s, %s" % (fullPath, traceback.format_exc()))
            title = None
            album = None
            artist = None
            duration = None

        # If we had to copy the file locally, make sure we delete it
        self._removeCopiedFile(copiedFile)

        return title, album, artist, duration

    def _saveAlbumArtFromMetadata(self, inputFileName):
        log("AudioBookHandler: Saving album art for audio book %s" % inputFileName)

        # If the file is not local, we might need to copy it
        fullPath = inputFileName
        copiedFile = self._getCopiedFileIfNeeded(inputFileName)
        if copiedFile not in [None, ""]:
            fullPath = copiedFile

        coverArt = None
        try:
            try:
                fullPath = fullPath.encode('utf-8')
            except:
                pass

            mutagenFile = mutagen.File(fullPath)

            if mutagenFile not in [None, ""]:
                # Get the name that the cached cover will have been stored as
                targetFile = self._getMainCoverLocation()
                log("AudioBookHandler: Cached cover target: %s" % targetFile)

                try:
                    targetFile = targetFile.encode('utf-8')
                except:
                    pass

                # Check to see if the pictures attribute is there
                if hasattr(mutagenFile, 'pictures'):
                    log("AudioBookHandler: Found pictures attribute")
                    if len(mutagenFile.pictures) > 0:
                        # write artwork to new image
                        with open(targetFile, 'wb') as img:
                            img.write(mutagenFile.pictures[0].data)
                        coverArt = targetFile

                if (coverArt in [None, ""]) and ('covr' in mutagenFile):
                    log("AudioBookHandler: Found COVR attribute")
                    if len(mutagenFile['covr']) > 0:
                        with open(targetFile, 'wb') as img:
                            img.write(mutagenFile['covr'][0])
                        coverArt = targetFile

                if (coverArt in [None, ""]):
                    for aTag in mutagenFile:
                        if 'APIC:' in aTag:
                            log("AudioBookHandler: Found APIC: attribute: %s" % aTag)
                            with open(targetFile, 'wb') as img:
                                img.write(mutagenFile[aTag].data)
                            coverArt = targetFile
                            break
            del mutagenFile
        except:
            log("AudioBookHandler: Failed to read metadata for audio book %s, %s" % (fullPath, traceback.format_exc()))
            coverArt = None

        # If we had to copy the file locally, make sure we delete it
        self._removeCopiedFile(copiedFile)

        return coverArt

    # Will load the basic details needed for simple listings
    def _loadDetails(self):
        log("AudioBookHandler: Loading audio book %s (%s)" % (self.filePath, self.fileName))

        # Check in the database to see if this audio book is already recorded
        audiobookDB = AudioBooksDB()
        audiobookDetails = audiobookDB.getAudioBookDetails(self.filePath)

        if audiobookDetails not in [None, ""]:
            self.title = audiobookDetails['title']
            self.numChapters = audiobookDetails['numChapters']
            self.position = audiobookDetails['position']
            self.chapterPosition = audiobookDetails['chapterPosition']
            self.isComplete = audiobookDetails['complete']
            self.hasArtwork = audiobookDetails['hasArtwork']
        else:
            self.position = 0
            self.chapterPosition = 0
            self.isComplete = False
            self._loadBookDetails()

            if self.title in [None, ""]:
                log("AudioBookHandler: No title found for %s, trying ffmpeg load" % self.filePath)
                self._loadDetailsFromFfmpeg()

            if self.title in [None, ""]:
                log("AudioBookHandler: No title found for %s, using filename" % self.filePath)
                self.title = self._getFallbackTitle()

            self.numChapters = len(self.chapters)

            # Now update the database entry for this audio book
            audiobookDB.addAudioBook(self.filePath, self.title, self.numChapters)

        del audiobookDB

    def _loadBookDetails(self):
        pass

    def _loadDetailsFromFfmpeg(self, includeCover=True):
        pass

    def getFile(self, tryUtf8=False):
        filePathValue = self.filePath
        if tryUtf8:
            try:
                filePathValue = filePathValue.encode("utf-8")
            except:
                pass
        return filePathValue

    def getTitle(self):
        if self.title in [None, ""]:
            self._loadDetails()
        return self.title

    def getCoverImage(self, tryUtf8=False):
        if self.coverImage is None:
            # Check to see if we already have an image available
            self.coverImage = self._getExistingCoverImage()

        # Before we go checking the actual file, see if we recorded that
        # we have already checked and there was not any
        if self.hasArtwork != 0:
            # If nothing was cached, then see if it can be extracted from the metadata
            if self.coverImage is None:
                self.coverImage = self._saveAlbumArtFromMetadata(self.filePath)

            # Last resort is to try and extract with ffmpeg
            # Only do the ffmpeg check if using the ffmpeg executable as
            # that is the only one that will get the album artwork
            if (self.coverImage is None) and (Settings.getFFmpegSetting() == Settings.FFMPEG_EXEC):
                self._loadDetailsFromFfmpeg()

            # Check if we have now found artwork that we want to store
            audiobookDB = AudioBooksDB()
            self.hasArtwork = 0
            if self.coverImage not in [None, ""]:
                self.hasArtwork = 1
            # Update the database with the artwork status
            audiobookDB.setHasArtwork(self.filePath, self.hasArtwork)
            del audiobookDB

        coverImageValue = self.coverImage
        # Make sure the cover is correctly encoded
        if tryUtf8 and (coverImageValue not in [None, ""]):
            try:
                coverImageValue = coverImageValue.encode("utf-8")
            except:
                pass

        return coverImageValue

    # Gets the fanart for the given file
    def getFanArt(self):
        baseDirectory = self.filePath
        if self.filePath.lower().endswith('.m4b'):
            # Check if there is a file just for this audiobook
            fullpathLocalImage, bookExt = os.path.splitext(self.filePath)
            fullpathLocalImage = "%s-fanart.jpg" % fullpathLocalImage

            if xbmcvfs.exists(fullpathLocalImage):
                log("AudioBookHandler: Found book fanart image %s" % fullpathLocalImage)
                return fullpathLocalImage

            # Get the name of the directory this file is in
            baseDirectory = (os_path_split(self.filePath))[0]

        # Now check if there is a default fanart file
        fanartImage = FANART
        subdirs, filesInDir = xbmcvfs.listdir(baseDirectory)
        for fileInDir in filesInDir:
            if fileInDir.lower() in ['fanart.jpg', 'fanart.png']:
                fanartImage = os_path_join(baseDirectory, fileInDir)
                break

        return fanartImage

    def getPosition(self):
        if self.position < 0:
            self._loadDetails()
        return self.position, self.chapterPosition

    def getChapterDetails(self):
        # If the chapter information has not been loaded yet, then we need to load it
        if len(self.chapters) < 1:
            self._loadBookDetails()
        if len(self.chapters) < 1:
            self._loadDetailsFromFfmpeg(includeCover=False)
        return self.chapters

    def getTotalDuration(self):
        if self.totalDuration < 0:
            # The duration is actually set by the last chapter
            self._loadBookDetails()
        if self.totalDuration < 1:
            # The duration is actually set by the last chapter
            self._loadDetailsFromFfmpeg(includeCover=False)
        return self.totalDuration

    def isCompleted(self):
        if self.isComplete is None:
            self._loadDetails()
        return self.isComplete

    def getChapterPosition(self, filename):
        # Default behaviour is to not track using the chapter
        return 0

    # Create a list item from an audiobook details
    def getPlayList(self, startTime=-1, startChapter=0):
        log("AudioBookHandler: Getting playlist to start for time %d" % startTime)
        listitem = self._getListItem(self.getTitle(), startTime)

        # Wrap the audiobook up in a playlist
        playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
        playlist.clear()
        playlist.add(self.getFile(), listitem)

        return playlist

    # Create a list item from an audiobook details
    def _getListItem(self, title, startTime=-1, chapterTitle=''):
        log("AudioBookHandler: Getting listitem for %s (Chapter: %s)" % (title, chapterTitle))

        listitem = xbmcgui.ListItem()
        # Set the display title on the music player
        # Have to set this as video otherwise it will not start the audiobook at the correct Offset place
        listitem.setInfo('video', {'Title': title})

        if chapterTitle not in [None, ""]:
            listitem.setInfo('music', {'album': chapterTitle})

        # If both the Icon and Thumbnail is set, the list screen will choose to show
        # the thumbnail
        coverImage = self.getCoverImage()
        if coverImage in [None, ""]:
            coverImage = ADDON.getAddonInfo('icon')

        listitem.setIconImage(coverImage)
        listitem.setThumbnailImage(coverImage)

        # Record if the video should start playing part-way through
        startPoint = startTime
        if startTime < 0:
            startPoint = self.getPosition()
        if startPoint > 0:
            listitem.setProperty('StartOffset', str(startPoint))

        # Stop the Lyrics addon trying to get lyrics for audiobooks
        listitem.setProperty('do_not_analyze', 'true')

        return listitem

    def _getExistingCoverImage(self):
        # Check if there is a cached version, or a local one on the drive
        fullpathLocalImage, bookExt = os.path.splitext(self.filePath)

        # Store the directory that the file is in, default the the current path
        parentPath = self.filePath

        # Check to see if this is actually a file with an extension
        if (bookExt not in [None, ""]) and (len(bookExt) < 5):
            fullpathLocalImage1 = "%s.jpg" % fullpathLocalImage
            fullpathLocalImage2 = "%s.JPG" % fullpathLocalImage
            fullpathLocalImage3 = "%s.png" % fullpathLocalImage
            fullpathLocalImage4 = "%s.PNG" % fullpathLocalImage

            if xbmcvfs.exists(fullpathLocalImage1):
                log("AudioBookHandler: Found local cached image %s" % fullpathLocalImage1)
                return fullpathLocalImage1
            if xbmcvfs.exists(fullpathLocalImage2):
                log("AudioBookHandler: Found local cached image %s" % fullpathLocalImage2)
                return fullpathLocalImage2
            if xbmcvfs.exists(fullpathLocalImage3):
                log("AudioBookHandler: Found local cached image %s" % fullpathLocalImage3)
                return fullpathLocalImage3
            if xbmcvfs.exists(fullpathLocalImage4):
                log("AudioBookHandler: Found local cached image %s" % fullpathLocalImage4)
                return fullpathLocalImage4

            # If we reach here, then we were a file, so get the directory part
            parentPath = (os_path_split(self.filePath))[0]

        # Check for a file in the same directory but with the name
        # "cover.jpg" or "folder.jpg
        dirs, files = xbmcvfs.listdir(parentPath)
        for file in files:
            if file.lower() in ['folder.jpg', 'cover.jpg', 'folder.png', 'cover.png']:
                fullpathLocalImage = os_path_join(parentPath, file)
                log("AudioBookHandler: Found local directory cover %s" % fullpathLocalImage)
                return fullpathLocalImage

        # Check for a cached cover
        return self._getCachedCover(self.fileName)

    # Checks the cache to see if there is a cover for this audiobook
    def _getCachedCover(self, fileName):
        cachedCover = None
        # check if the directory exists before searching
        dirs, files = xbmcvfs.listdir(Settings.getCoverCacheLocation())
        for aFile in files:
            # Get the filename without extension
            coverSrc, ext = os.path.splitext(aFile)

            # Get the name that the cached cover will have been stored as
            targetSrc, bookExt = os.path.splitext(fileName)

            # Make sure both are utf-8 when comparing
            try:
                coverSrc = coverSrc.encode("utf-8")
            except:
                pass
            try:
                targetSrc = targetSrc.encode("utf-8")
            except:
                pass

            if targetSrc == coverSrc:
                cachedCover = os_path_join(Settings.getCoverCacheLocation(), aFile)
                log("AudioBookHandler: Cached cover found: %s" % cachedCover)

        return cachedCover

    def _getFallbackTitle(self):
        # Remove anything after the final dot
        sections = self.fileName.split('.')
        sections.pop()
        # Replace the dots with spaces
        return ' '.join(sections)

    # Runs the ffmpeg command, returning the text output, saving the cover image if
    # a target is given in the request
    def _runFFmpegCommand(self, inputFileName, coverTargetName=None):
        # Check to see if ffmpeg is enabled
        ffmpegCmds = FfmpegBase.createHandler()

        if ffmpegCmds in [None, ""]:
            log("AudioBookHandler: ffmpeg not enabled")
            return None

        log("AudioBookHandler: Running ffmpeg for %s" % inputFileName)

        # FFmpeg will not recognise paths that start with smb:// or nfs://
        # These paths are specific to Kodi, so we need to copy the file locally
        # before we can run the FFmpeg command
        fullFileName = inputFileName
        copiedFile = self._getCopiedFileIfNeeded(inputFileName)
        if copiedFile not in [None, ""]:
            fullFileName = copiedFile

        # Check if we need the image
        coverTempName = None
        if coverTargetName not in [None, '']:
            coverTempName = os_path_join(Settings.getTempLocation(), 'maincover.jpg')
            # Remove the temporary name if it is already there
            if xbmcvfs.exists(coverTempName):
                xbmcvfs.delete(coverTempName)

        # Now make the call to gather the information
        ffmpegOutput = ffmpegCmds.getMediaInfo(fullFileName, coverTempName)
        del ffmpegCmds

        # If we had to copy the file locally, make sure we delete it
        self._removeCopiedFile(copiedFile)

        # Check if there is an image in the temporary location
        if coverTempName not in [None, ""]:
            if xbmcvfs.exists(coverTempName):
                # Now move the file to the covers cache directory
                copy = xbmcvfs.copy(coverTempName, coverTargetName)
                if copy:
                    log("AudioBookHandler: copy successful for %s" % coverTargetName)
                else:
                    log("AudioBookHandler: copy failed from %s to %s" % (coverTempName, coverTargetName))

                # Tidy up the image that we actually do not need
                xbmcvfs.delete(coverTempName)

        return ffmpegOutput

    def _getMainCoverLocation(self):
        coverFileName, oldExt = os.path.splitext(self.fileName)
        targetCoverName = "%s.jpg" % coverFileName
        coverTargetName = os_path_join(Settings.getCoverCacheLocation(), targetCoverName)

        log("AudioBookHandler: Cached cover target location is %s" % coverTargetName)
        return coverTargetName

    def getChapterStart(self, chapterNum):
        # Work out at what time the given chapter starts, this will be part way through a file
        idx = chapterNum - 1
        if (idx > -1) and (len(self.chapters) > idx):
            chapterDetails = self.chapters[idx]
            return chapterDetails['startTime']
        return 0


# Class for handling m4b files
class M4BHandler(AudioBookHandler):
    def __init__(self, audioBookFilePath):
        AudioBookHandler.__init__(self, audioBookFilePath)

    def _loadBookDetails(self):
        # For the m4b book details we can just read from the meta data
        title, album, artist, duration = self._readMetaData(self.filePath)

        if title not in [None, ""]:
            self.title = title

            # Check if the title should start with the artist name
            if Settings.isShowArtistInBookList():
                if artist not in [None, ""]:
                    # Make sure the artist name is not already in the title
                    if (not title.startswith(artist)) and (not title.endswith(artist)):
                        try:
                            self.title = "%s - %s" % (artist, title)
                        except:
                            log("M4BHandler: Failed to add artist to title")

        if duration not in [None, "", 0, -1]:
            self.totalDuration = duration

    # Will load the basic details needed for simple listings
    def _loadDetailsFromFfmpeg(self, includeCover=True):
        # check if the cover is required
        coverTargetName = None
        if includeCover:
            coverTargetName = self._getMainCoverLocation()

        info = self._runFFmpegCommand(self.filePath, coverTargetName)

        # If we needed the cover, then save the details
        if includeCover:
            if xbmcvfs.exists(coverTargetName):
                self.coverImage = coverTargetName

        if info not in [None, ""]:
            self.title = info['title']

            # Check if the title should start with the artist name
            if Settings.isShowArtistInBookList() and (self.title not in [None, ""]):
                artist = info['artist']
                if artist not in [None, ""]:
                    # Make sure the artist name is not already in the title
                    if (not self.title.startswith(artist)) and (not self.title.endswith(artist)):
                        try:
                            self.title = "%s - %s" % (artist, self.title)
                        except:
                            log("M4BHandler: Failed to add artist to title")

            self.chapters = info['chapters']
            self.totalDuration = info['duration']

    def _getFallbackTitle(self):
        # Remove anything after the final dot
        sections = self.fileName.split('.')
        sections.pop()
        # Replace the dots with spaces
        return ' '.join(sections)


# Class for handling m4b files
class FolderHandler(AudioBookHandler):
    def __init__(self, audioBookFilePath):
        AudioBookHandler.__init__(self, audioBookFilePath)
        # The fileName value will be the directory name for Folder audiobooks
        self.chapterFiles = []

    def _loadBookDetails(self):
        # List all the files in the directory, as that will be the chapters
        dirs, files = xbmcvfs.listdir(self.filePath)
        files.sort()

        runningStartTime = 0
        for audioFile in files:
            if not Settings.isPlainAudioFile(audioFile):
                continue

            # Store this audio file in the chapter file list
            fullpath = os_path_join(self.filePath, audioFile)
            self.chapterFiles.append(fullpath)

            # Make the call to metadata to get the details of the chapter
            title, album, artist, duration = self._readMetaData(fullpath)

            chapterTitle = None
            endTime = 0
            if self.title in [None, ""]:
                if album not in [None, ""]:
                    self.title = album

                    # Check if the title should start with the artist name
                    if Settings.isShowArtistInBookList():
                        if artist not in [None, ""]:
                            # Make sure the artist name is not already in the title
                            if (not album.startswith(artist)) and (not album.endswith(artist)):
                                try:
                                    self.title = "%s - %s" % (artist, album)
                                except:
                                    log("FolderHandler: Failed to add artist to title")

            if title not in [None, ""]:
                chapterTitle = title
            if duration not in [None, 0]:
                endTime = runningStartTime + duration

            if chapterTitle in [None, ""]:
                # Now generate the name of the chapter from the audio file
                sections = audioFile.split('.')
                sections.pop()
                # Replace the dots with spaces
                chapterTitle = ' '.join(sections)

            detail = {'title': chapterTitle, 'startTime': runningStartTime, 'endTime': endTime, 'duration': duration}
            self.chapters.append(detail)
            # Set the next start time to be after this chapter
            runningStartTime = endTime

        if runningStartTime > 0:
            self.totalDuration = runningStartTime

    # Will load the basic details needed for simple listings
    def _loadDetailsFromFfmpeg(self, includeCover=True):
        # List all the files in the directory, as that will be the chapters
        dirs, files = xbmcvfs.listdir(self.filePath)
        files.sort()

        # Check if the cover image is required
        coverTargetName = None
        if includeCover and (self.coverImage in [None, ""]):
            coverTargetName = self._getMainCoverLocation()

        runningStartTime = 0
        for audioFile in files:
            if not Settings.isPlainAudioFile(audioFile):
                continue

            # Store this audio file in the chapter file list
            fullpath = os_path_join(self.filePath, audioFile)
            self.chapterFiles.append(fullpath)

            # Make the call to ffmpeg to get the details of the chapter
            info = self._runFFmpegCommand(fullpath, coverTargetName)

            # If we needed the cover, then save the details
            if coverTargetName not in [None, ""]:
                if xbmcvfs.exists(coverTargetName):
                    self.coverImage = coverTargetName
                    # Clear the cover image flag so we do not get it again
                    coverTargetName = None

            duration = 0
            chapterTitle = None
            endTime = 0
            if info not in [None, ""]:
                if self.title in [None, ""]:
                    self.title = info['album']

                    # Check if the title should start with the artist name
                    if Settings.isShowArtistInBookList():
                        artist = info['artist']
                        if artist not in [None, ""]:
                            # Make sure the artist name is not already in the title
                            if (not self.title.startswith(artist)) and (not self.title.endswith(artist)):
                                try:
                                    self.title = "%s - %s" % (artist, self.title)
                                except:
                                    log("FolderHandler: Failed to add artist to title")

                duration = info['duration']
                chapterTitle = info['title']
                if duration not in [None, 0]:
                    endTime = runningStartTime + info['duration']

            if chapterTitle in [None, ""]:
                # Now generate the name of the chapter from the audio file
                sections = audioFile.split('.')
                sections.pop()
                # Replace the dots with spaces
                chapterTitle = ' '.join(sections)

            detail = {'title': chapterTitle, 'startTime': runningStartTime, 'endTime': endTime, 'duration': duration}
            self.chapters.append(detail)
            # Set the next start time to be after this chapter
            runningStartTime = endTime

        if runningStartTime > 0:
            self.totalDuration = runningStartTime

    # Create a list item from an audiobook details
    def getPlayList(self, startTime=-1, startChapter=0):
        log("FolderHandler: Getting playlist to start for time %d" % startTime)

        # Wrap the audiobook up in a playlist
        playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
        playlist.clear()

        # Add each chapter file
        idx = 0
        startPosition = 0
        if startTime > 0:
            startPosition = startTime

        # Start on the correct chapter
        if startChapter > 1:
            idx = startChapter - 1

        while idx < len(self.getChapterDetails()):
            chapterDetail = self.chapters[idx]
            listitem = self._getListItem(self.getTitle(), startPosition, chapterDetail['title'])
            playlist.add(self.chapterFiles[idx], listitem)
            # Once we set the correct starting position for the main chapter, reset it
            # that that the next chapters start at the beginning
            startPosition = 0
            idx += 1

        return playlist

    def getChapterPosition(self, filename):
        chapterPosition = 0
        if len(self.chapterFiles) < 1:
            self._loadBookDetails()
            # Only load specific details if the basic version failed
        if len(self.chapterFiles) < 1:
            self._loadDetailsFromFfmpeg(False)

        # Make sure the filename passed in is not utf-8 othersise it will not work
        compareFilename = filename
        try:
            compareFilename = compareFilename .decode('utf-8')
        except:
            pass

        if compareFilename in self.chapterFiles:
            chapterPosition = self.chapterFiles.index(compareFilename)
            chapterPosition += 1
            log("FolderHandler: Found Chapter at position %d for %s" % (chapterPosition, filename))

        return chapterPosition

    def getChapterStart(self, chapterNum):
        # As each chapter is in it's own file, it will always start at zero
        return 0

    def _getFallbackTitle(self):
        # Replace the dots with spaces
        return self.fileName.replace('.', ' ')

    def _saveAlbumArtFromMetadata(self, fullPath):
        dirs, files = xbmcvfs.listdir(self.filePath)

        coverImg = None
        for audioFile in files:
            fullPath = os_path_join(self.filePath, audioFile)
            coverImg = AudioBookHandler._saveAlbumArtFromMetadata(self, fullPath)
            if coverImg not in [None, ""]:
                break
        return coverImg

    def _getExistingCoverImage(self):
        # Call the common cover file check first
        coverImg = AudioBookHandler._getExistingCoverImage(self)

        # There is an extra check that we can make for folder audiobooks
        # so if one has not been found then look in the folder for folder.jpg
        if coverImg is None:
            dirs, files = xbmcvfs.listdir(self.filePath)

            for coverFile in files:
                if coverFile.lower() in ['folder.jpg', 'folder.png']:
                    coverImg = os_path_join(self.filePath, coverFile)
                    break

        return coverImg
