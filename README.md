# Transmission remote control bot

This is a Telegram bot for remote control of transmission-daemon.

## Features
 - Transmission remote control via Telegram
   - Add new torrents by sending a `.torrent` file or a magnet link
   - List/start/pause/delete your torrents
   - Set/show download/upload bandwidth limits (shared among all users)
 - Multi-user support, each user has their own torrents
 - Torrents may be shared between users
 - Torrent sharing via FTP

## Configuration file
The bot loads configuration from a `config.yaml` file. See [example](https://github.com/vvd170501/transmission-control-bot/blob/master/config.yaml) for more info

## TODO:
 - [ ] Move all strings to a separate module
 - [ ] Add language choice (?)
 - [ ] Add disk quotas (?)
 - [ ] Add FTP access for standard categories
 - [ ] User-configurable FTP time-limit (?)
