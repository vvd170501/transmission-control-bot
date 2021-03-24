# Transmission remote control bot

This is a Telegram bot for remote control of transmission-daemon.

## Features
 - Transmission remote control via Telegram
   - Add new torrents by sending a `.torrent` file or a magnet link
   - List/start/pause/delete your torrents
   - Set/show download/upload bandwidth limits (shared among all users)
 - Multi-user support, each user has their own torrents (admins can see all torrents)
 - Torrent sharing via FTP
   - Admins may upload files via FTP (may be useful if the root download directory contains other files, e.g, is used a media library)

## Configuration file
The bot uses a `config.json` file with the following format:
 - `token`: Telegram token for the bot
 - `password`: a pasword used to authenticate new users
 - `admins`: a list of admin UIDs (may be empty)
 - `rootdir`: root directory for downloads (should be configured for transmission manually). Bot uses this variable only for checking free space.
 - `reserved_space`: minimal amount of free space (in bytes) on the partition with `rootdir`. If the amount of free space goes below this number, all torrents are automatically stopped.
 - `client_cfg`: transmission address, port and credentials
 - `ftp`:
   - `address`: address and port to listen on
   - `root`: the directory which will be shared by `/ftp` admin command (may differ from `rootdir`)
   - `tl`: time limit (in seconds) for FTP shares. After this period shares will be automatically closed

## TODO:
 - [ ] Move all strings to a separate module
 - [ ] Add language choice (?)
 - [ ] Allow using custom paths for config/db/log
 - [ ] Add disk quotas (?)
 - [ ] Allow disabling free space checker
 - [ ] Make pyftpdlib requirement optional
 - [ ] Add FTP access for standard categories
 - [ ] Allow configuring FTP time-limit
