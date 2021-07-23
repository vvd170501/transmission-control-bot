# Transmission remote control bot

This is a Telegram bot for remote control of transmission-daemon.

## Features
 - Transmission remote control via Telegram
   - Add new torrents by sending a `.torrent` file or a magnet link
   - List/start/pause/delete your torrents
   - Set/show download/upload bandwidth limits (shared among all users)
 - Multi-user support, each user has their own torrents (admins can see all torrents)
 - Torrent sharing via FTP
   - Admins may upload files via FTP (may be useful if the root download directory contains other files, e.g, is used as a media library)

## Configuration file
The bot loads configuration from a `config.yaml` file. See [example](https://github.com/vvd170501/transmission-control-bot/blob/master/config.yaml) for more info

## TODO:
 - [ ] Move all strings to a separate module
 - [ ] Add language choice (?)
 - [ ] Add disk quotas (?)
 - [ ] Allow disabling free space checker
 - [ ] Make pyftpdlib requirement optional
 - [ ] Add FTP access for standard categories
 - [ ] User-configurable FTP time-limit (?)
