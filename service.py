# -*- coding: utf-8 -*-
import sys
import xbmc
import xbmcaddon
import xbmcvfs

# Import the common settings
from resources.lib.settings import log
from resources.lib.settings import os_path_join
from resources.lib.settings import os_path_split
from resources.lib.settings import dir_exists
from resources.lib.settings import Settings
from resources.lib.database import AudioBooksDB
from resources.lib.ffmpegLib import FFMpegLib


ADDON = xbmcaddon.Addon(id='script.audiobooks')


#########################
# Main
#########################
if __name__ == '__main__':
    log("AudioBookService: Checking audiobook database version (version %s)" % ADDON.getAddonInfo('version'))

    configPath = xbmc.translatePath(ADDON.getAddonInfo('profile'))
    databasefile = os_path_join(configPath, "audiobooks_database.db")
    log("AudioBookService: Checking database file = %s" % databasefile)

    # If the database file exists, check if it needs updating
    if xbmcvfs.exists(databasefile):
        audiobookDB = AudioBooksDB()
        audiobookDB.createDatabase()
        del audiobookDB

    if Settings.isFFmpegAutoDetect():
        log("AudioBookService: Performing refresh check on FFmpeg")
        # Turn off the search at startup as we do not want to do this every time
        Settings.clearFFmpegAutoDetect()

        # Clear the existing settings
        Settings.setFFmpegLibraryLocation("")
        Settings.setFFmpegExecLocation("")

        log("AudioBookService: Platform Type: %s" % sys.platform.lower())

        # Perform a check to see if we can automatically detect where the libraries
        # are, on windows we should already have them
        defaultFFmpegSetting = Settings.FFMPEG_NONE

        # First location to check is the location defined in the settings
        libLocation = None
        # First check the player directory
        playerDir = xbmc.translatePath('special://xbmc/system/players/dvdplayer/').decode("utf-8")
        libLocation = FFMpegLib.getPlatformLibFiles(playerDir)

        if libLocation is None:
            # Then check the root directory, sometimes they are there
            rootDir = xbmc.translatePath('special://xbmc/').decode("utf-8")
            libLocation = FFMpegLib.getPlatformLibFiles(rootDir)

        if libLocation is not None:
            libPath = os_path_split(libLocation['avutil'])[0]
            log("AudioBookService: Detected library path as %s" % libPath)
            Settings.setFFmpegLibraryLocation(libPath)
            # If the libraries are there, enable them as the default
            defaultFFmpegSetting = Settings.FFMPEG_LIB

        # Now check to see if we have one of the FFmpeg bundles installed
        if xbmc.getCondVisibility('System.HasAddon(script.module.ffmpeg)') != 1:
            log("AudioBookService: No script.module.ffmpeg bundle detected")
        else:
            log("AudioBookService: script.module.ffmpeg bundle detected")
            ffmpegModule = xbmcaddon.Addon(id='script.module.ffmpeg')
            modulePath = ffmpegModule.getAddonInfo('path')
            log("AudioBookService: FFmpeg addon path is: %s" % modulePath)

            # Make sure the addon path exists
            if not dir_exists(modulePath):
                log("AudioBookService: FFmpeg addon path does not exist: %s" % modulePath)
            else:
                # Check if there is library path available
                libPath = os_path_join(modulePath, "libs")
                if not dir_exists(libPath):
                    log("AudioBookService: No libraries included in FFmpeg bundle")
                else:
                    log("AudioBookService: Setting library path to: %s" % libPath)
                    Settings.setFFmpegLibraryLocation(libPath)
                    # If the libraries are there, enable them as the default
                    defaultFFmpegSetting = Settings.FFMPEG_LIB

                # Check if there is an executable available
                execPath = os_path_join(modulePath, "exec")
                if not dir_exists(execPath):
                    log("AudioBookService: No executable included in FFmpeg bundle")
                else:
                    log("AudioBookService: Found executable directory: %s" % execPath)
                    # Read all the files from the directory, and pick the ffmpeg executable
                    dirs, files = xbmcvfs.listdir(execPath)
                    for aFile in files:
                        if 'ffmpeg' in aFile:
                            ffmpegExec = os_path_join(execPath, aFile)
                            log("AudioBookService: Found FFmpeg executable: %s" % ffmpegExec)
                            Settings.setFFmpegExecLocation(ffmpegExec)
                            if defaultFFmpegSetting in [None, Settings.FFMPEG_NONE]:
                                defaultFFmpegSetting = Settings.FFMPEG_EXEC

        # Now update the default FFmpeg setting
        Settings.setFFmpegSetting(defaultFFmpegSetting)
    else:
        log("AudioBookService: FFmpeg check not required")
