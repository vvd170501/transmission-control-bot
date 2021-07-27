#!/usr/bin/env python3

import argparse
import logging
import re
import sys
import traceback
from enum import Enum
from functools import wraps
from pathlib import Path
from signal import SIGINT, SIGTERM, SIGABRT

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, \
                     InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater,\
                         CommandHandler, MessageHandler, ConversationHandler, CallbackQueryHandler
from telegram.ext.filters import Filters
from telegram.error import BadRequest
import yaml

import strings
import keyboard_utils as kb
from driver import Driver


class State(Enum):
    SELECT_DOWNLOAD_DIRECTORY = 1
    CUSTOM_DIRECTORY = 2
    SELECT_DOWNLOAD_LIMIT = 11
    SELECT_UPLOAD_LIMIT = 12
    SELECT_LIMIT_DURATION = 13
    END = ConversationHandler.END


def log_error():
    e = traceback.format_exc()
    logging.error(e)


def speed_format(kbps):
    if kbps < 1000:
        return f'{kbps} KB/s'
    return f'{kbps/1000:.2f} MB/s'


def restricted_template(func, *, whitelist):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if callable(whitelist):
            real_whitelist = whitelist()
        else:
            real_whitelist = whitelist
        if user_id not in real_whitelist:
            return
        return func(update, context, *args, **kwargs)
    return wrapped


# noinspection PyUnusedLocal
class TBot:
    valid_dirname = re.compile(r'^[\w. -]+$')

    def __init__(self, cfg_path, db_path):
        with open(cfg_path) as f:
            config = yaml.safe_load(f)

        self.password = config['password']
        self.updater = Updater(
            token=config['token'], use_context=True,
            user_sig_handler=self.signal
        )
        self.bot = self.updater.bot
        self.driver = Driver(
            db_path=db_path,
            rootdir=config['rootdir'],
            reserved_space=config['reserved_space'],
            client_cfg=config['client_cfg'],
            ftp_cfg=config['ftp'],
            job_queue=self.updater.job_queue
        )

        conversation_fallbacks = [
            CommandHandler('cancel', self.conversation_cancel),
            MessageHandler(Filters.all, self.conversation_error)
        ]

        self._add_command_handler('start', self.start, restricted=False)
        # Auth handler. If user is not authenticated, restricted commands will be silently ignored
        self._add_handler(
            MessageHandler(Filters.text & (~Filters.command), self.auth),
            group=1  # if group is 0, may interfere with other handlers. Use dynamic filter instead?
        )

        self._add_command_handler('preferences', self.preferences)
        self._add_inline_button_handler(
            kb.CallbackQueryPatterns.default_share, self.set_default_share_status
        )

        self._add_command_handler('help', self.help)
        self._add_command_handler('disk', self.show_disk_usage)
        self._add_command_handler('limit', self.limit)
        self._add_handler(ConversationHandler(
            [CommandHandler('setlimit', self._make_restricted(self.setlimit))],
            {
                State.SELECT_DOWNLOAD_LIMIT: [
                    MessageHandler(
                        Filters.text(list(strings.dl_buttons.keys())),
                        self.select_download_limit
                    )
                ],
                State.SELECT_UPLOAD_LIMIT: [
                    MessageHandler(
                        Filters.text(list(strings.ul_buttons.keys())),
                        self.select_upload_limit
                    )
                ],
                State.SELECT_LIMIT_DURATION: [
                    MessageHandler(
                        Filters.text(list(strings.dur_buttons.keys())),
                        self.select_limit_duration
                    )
                ]
            },
            conversation_fallbacks
        ))
        self._add_command_handler('my_torrents', self.my_torrents)
        self._add_command_handler('shared_torrents', self.shared_torrents)
        # Adding new torrents
        self._add_handler(ConversationHandler(
            [
                MessageHandler(
                    Filters.document.mime_type('application/x-bittorrent'),
                    self._make_restricted(self.add_torrent)
                ),
                MessageHandler(
                    Filters.regex(re.compile(r'^magnet:\?', re.I)),
                    self._make_restricted(self.add_magnet)
                ),
            ],
            {
                State.SELECT_DOWNLOAD_DIRECTORY: [
                    MessageHandler(
                        Filters.text(list(strings.dir_buttons.keys())),
                        self.select_download_directory
                    )
                ],
                State.CUSTOM_DIRECTORY: [
                    MessageHandler(Filters.text & (~Filters.command), self.custom_directory)
                ]
            },
            conversation_fallbacks
        ))

        self._add_inline_button_handler(
            kb.CallbackQueryPatterns.show_list_part, self.show_torrent_list_part
        )
        self._add_inline_button_handler(
            kb.CallbackQueryPatterns.show_item, self.torrent_info
        )
        self._add_inline_button_handler(
            kb.CallbackQueryPatterns.toggle_torrent_status, self.toggle_torrent
        )
        self._add_inline_button_handler(
            kb.CallbackQueryPatterns.edit_share_status, self.edit_share_status
        )
        self._add_inline_button_handler(
            kb.CallbackQueryPatterns.move_torrent, self.move_torrent
        )
        self._add_inline_button_handler(
            kb.CallbackQueryPatterns.delete_torrent, self.delete_torrent
        )

        if self.driver.ftp_enabled:
            self._add_command_handler('ftp', self.share_root_ftp)
            self._add_command_handler('noftp', self.unshare_root_ftp)
            self._add_inline_button_handler(
                kb.CallbackQueryPatterns.ftp_control, self.torrent_ftp_access
            )

    def run(self):
        self.updater.start_polling()
        self.updater.idle()

    def auth(self, update, context):
        user = update.effective_user.id
        # text message from a whitelisted user. Move this check to a dynamic filter?
        if user in self.driver.get_whitelist():
            return
        if update.message.text == self.password:
            self.driver.whitelist_user(user)
            msg = 'You are now authenticated!'
        else:
            msg = 'Incorrect password!'
        self.answer(update, msg)

# --------------------------------------------------------------------------------------------------
# oneline commands
# --------------------------------------------------------------------------------------------------

    def start(self, update, context):
        self.answer(update, 'Input password to continue!')

    def help(self, update, context):
        self.answer(update, strings.help(self.driver.ftp_enabled))

    def limit(self, update, context):
        self.answer(update, self.driver.get_speed_limits())

    def show_disk_usage(self, update, context):
        self.answer(update, self.driver.get_disk_usage())

    def share_root_ftp(self, update, context):
        self.answer(update, self.driver.share_root_ftp())

    def unshare_root_ftp(self, update, context):
        self.answer(update, self.driver.unshare_root_ftp())

# --------------------------------------------------------------------------------------------------
# preferences
# --------------------------------------------------------------------------------------------------

    def preferences(self, update, context):
        # TODO!!
        ...

    def set_default_share_status(self, update, context):
        # TODO!!
        ...

# --------------------------------------------------------------------------------------------------
# setlimit conversation
# --------------------------------------------------------------------------------------------------

    def setlimit(self, update, context):
        self.answer(
            update,
            strings.select_download_limit,
            reply_markup=ReplyKeyboardMarkup(strings.download_limit_choices, resize_keyboard=True)
        )
        return State.SELECT_DOWNLOAD_LIMIT

    def select_download_limit(self, update, context):
        context.chat_data['dl'] = strings.dl_buttons[update.message.text]
        self.answer(
            update,
            strings.select_upload_limit,
            reply_markup=ReplyKeyboardMarkup(strings.upload_limit_choices, resize_keyboard=True)
        )
        return State.SELECT_UPLOAD_LIMIT

    def select_upload_limit(self, update, context):
        context.chat_data['ul'] = strings.ul_buttons[update.message.text]
        if not (context.chat_data['dl'] or context.chat_data['ul']):
            # Unset limits
            # TODO!!
            ...
            context.chat_data.clear()
            return State.END
        self.answer(
            update,
            strings.select_duration,
            reply_markup=ReplyKeyboardMarkup(
                strings.limit_duration_choices, one_time_keyboard=True, resize_keyboard=True
            )
        )
        return State.SELECT_LIMIT_DURATION

    def select_limit_duration(self, update, context):
        # TODO!!
        ...
        return State.END

# --------------------------------------------------------------------------------------------------
# torrent management
# --------------------------------------------------------------------------------------------------

    def show_torrents(self, update, context, torrents, category, offset=0, message=None):
        # TODO cache torrent list in chat_data? (WTF?)
        elements_per_page = 10

        total_count = len(torrents)
        if offset >= total_count:  # e.g. last page contained only one torrent and it was deleted
            # show the current last page instead
            if total_count == 0:
                offset = 0
            else:
                # max multiple of elements_per_page below total_count
                offset = (total_count - 1) // elements_per_page * elements_per_page
        torrents = torrents[offset:offset + elements_per_page]

        # TODO!!
        ftp = ...
        msg_text = ...  # strings.format_torrents(torrents, offset, total_count, ftp)
        hashes = [torrent.hashString for torrent in torrents]  # !! get hashes from driver?
        markup = kb.ListNavigationKeyboard(
            hashes, elements_per_page, offset, total_count, category
        ).build()
        if message is None:
            self.answer(update, msg_text, reply_markup=markup)
        else:
            message.edit_text(msg_text, reply_markup=markup)

    def show_torrent_list_part(self, update, context):
        offset, category = context.match.groups()
        if offset == 'left':
            self.answer_callback(update, strings.left)
            return
        if offset == 'right':
            self.answer_callback(update, strings.right)
            return
        if category == 'my':
            # TODO!!
            torrents = ...
        else:
            # TODO!!
            torrents = ...
        try:
            self.show_torrents(update, context, torrents, category, int(offset),
                               message=update.callback_query.message)
        except BadRequest:  # Same text
            pass
        update.callback_query.answer()

    def my_torrents(self, update, context):
        uid = update.effective_user.id
        # TODO!!
        torrents = ...
        self.show_torrents(update, context, torrents, 'my')

    def shared_torrents(self, update, context):
        uid = update.effective_user.id
        # TODO!!
        torrents = ...
        self.show_torrents(update, context, torrents, 'shr')

    def _show_torrent_info(self, update, context, item_id, list_location, stopping=False):
        user = update.effective_user.id

        markup = kb.TorrentControlKeyboard(
            item_id, list_location, ..., ..., ..., self.driver.ftp_enabled
        ).build()

        # TODO!!
        ...

    def torrent_info(self, update, context):
        item_id, list_location = context.match.groups()
        self._show_torrent_info(update, context, item_id, list_location)
        update.callback_query.answer()

    def toggle_torrent(self, update, context):
        action, t_hash, list_location = context.match.groups()
        if action == 'run':
            # TODO!!
            ...
        else:
            # TODO!!
            ...
        self._show_torrent_info(update, context, t_hash, list_location, action != 'run')
        update.callback_query.answer()

    def torrent_ftp_access(self, update, context):
        # TODO allow filtered access to categories
        # TODO select tl (manually / based on size? 1h/18GB(5MBps))
        action, t_hash, list_location = context.match.groups()  # !!

        if action == '-':
            # TODO!!
            ...
            self._show_torrent_info(update, context, t_hash, list_location)
            # NOTE was before _show_torrent_info. check order
            self.answer_callback(update, strings.ftp_stop_access)
            return
        # (optionally open FTP access and) show status
        if action == '+':
            # TODO!!
            ...
        else:
            # TODO!!
            ...
        msg_text = ...
        try:
            update.callback_query.message.edit_text(
                msg_text,
                reply_markup=kb.FTPControlKeyboard(t_hash, list_location, ...).build(),  # !!
                parse_mode='markdown'
            )
        except BadRequest:
            pass
        update.callback_query.answer()

    def edit_share_status(self, update, context):
        # TODO!!
        ...

    def move_torrent(self, update, context):
        # TODO!!
        ...

    def delete_torrent(self, update, context):
        action, item_id, list_location = context.match.groups()
        if action == kb.CallbackQueryActions.confirm_deletion:
            # TODO!!
            ...
            update.callback_query.message.edit_text(
                strings.deleted,
                reply_markup=kb.ReturnToListKeyboard(list_location).build()
            )
        else:
            # TODO!!
            ...
            update.callback_query.message.edit_text(
                strings.del_confirm.format(...),  # !!
                reply_markup=kb.DeletionConfirmationKeyboard(item_id, list_location).build()
            )
        update.callback_query.answer()

# --------------------------------------------------------------------------------------------------
# new torrent conversation
# --------------------------------------------------------------------------------------------------

    def _goto_directory_selection(self, update):
        self.answer(
            update, strings.select_dir,
            reply_markup=ReplyKeyboardMarkup(
                strings.dir_kb,
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return State.SELECT_DOWNLOAD_DIRECTORY

    def add_torrent(self, update, context):
        context.chat_data['torrent'] = update.message.document
        return self._goto_directory_selection(update)

    def add_magnet(self, update, context):
        context.chat_data['magnet'] = update.message.text
        return self._goto_directory_selection(update)

    def select_download_directory(self, update, context):
        if not strings.dir_buttons[update.message.text]:
            self.answer(update, strings.custom_directory, reply_markup=ReplyKeyboardRemove())
            return State.CUSTOM_DIRECTORY
        # TODO!! async???
        ...
        return State.END

    def custom_directory(self, update, context):
        dirname = update.message.text
        if self.valid_dirname.match(dirname) and dirname not in ['.', '..']:
            # TODO!!
            ...
            return State.END
        self.answer(update, strings.invalid_dirname)
        return State.CUSTOM_DIRECTORY

# --------------------------------------------------------------------------------------------------
# conversation fallbacks
# --------------------------------------------------------------------------------------------------

    def conversation_cancel(self, update, context):
        context.chat_data.clear()
        self.answer(update, strings.cancelled, reply_markup=ReplyKeyboardRemove())
        return State.END

    def conversation_error(self, update, context):
        self.answer(update, strings.howtocancel)

# --------------------------------------------------------------------------------------------------
# utils
# --------------------------------------------------------------------------------------------------

    def _make_restricted(self, function):
        return restricted_template(function, whitelist=self.driver.get_whitelist)

    def _add_handler(self, handler, group=0):
        # A shortcut for adding handlers
        self.updater.dispatcher.add_handler(handler, group=group)

    def _add_command_handler(self, command, callback, restricted=True, **kwargs):
        if restricted:
            callback = self._make_restricted(callback)
        self._add_handler(CommandHandler(command, callback, **kwargs))

    def _add_inline_button_handler(self, pattern, callback):
        # Handlers are restricted, just in case.
        # Is it possible for a client to send a callback query without pressing any actual buttons?
        self._add_handler(CallbackQueryHandler(self._make_restricted(callback), pattern=pattern))

    def answer(self, update, msg, **kwargs):
        self.bot.send_message(chat_id=update.effective_chat.id, text=msg, **kwargs)

    def answer_callback(self, update, msg, **kwargs):
        self.bot.answer_callback_query(update.callback_query.id, text=msg, **kwargs)

    def signal(self, signum, frame):
        if signum not in [SIGINT, SIGTERM, SIGABRT]:
            return
        if hasattr(self, 'ftpd'):
            self.ftpd.force_stop()

# --------------------------------------------------------------------------------------------------
# BOT END
# --------------------------------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', metavar='FILE', help='Config file', required=True)
    parser.add_argument('--db', metavar='FILE',
                        help='DB file (default: "config_directory/data.db")')
    parser.add_argument('--log', metavar='FILE', help='Log file (default: write to stderr)')
    args = parser.parse_args()

    logging_cfg = {
        'style': '{',
        'format': '[{asctime}] {threadName}:{levelname} - {message}',
        'datefmt': '%Y-%m-%d %H:%M:%S'
    }
    if args.log:
        logging_cfg['filename'] = args.log
    else:
        logging_cfg['stream'] = sys.stderr
    logging.basicConfig(**logging_cfg)
    db_path = args.db or str(Path(args.config).parent.joinpath('data.db').absolute())
    bot = TBot(args.config, db_path)
    bot.run()


if __name__ == '__main__':
    main()
