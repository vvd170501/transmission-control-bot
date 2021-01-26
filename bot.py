import json
import logging
import os
import pathlib
import re
import time
import traceback
from enum import Enum
from functools import wraps, partial
from io import BytesIO

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, ConversationHandler, CallbackQueryHandler
from telegram.ext.filters import Filters
from telegram.error import BadRequest
from transmission_rpc import Client as Transmission

import strings
from db import BotDB

valid_dirname = re.compile(r'^[\w. -]+$')
offset_query = re.compile(r'^offset=(\w+),(\w+)$')
hash_query = re.compile(r'^hash=(\w+),(\d+),(\w+)$')
toggle_query = re.compile(r'^(run|stop)=(\w+),(\d+),(\w+)$')
del_query = re.compile(r'^(del2?)=(\w+),(\d+),(\w+)$')

BASE_DIR = pathlib.Path(__file__).parent

logging.basicConfig(filename=str(BASE_DIR.joinpath('tbot.log').absolute()), style="{", format="[{asctime}] {levelname} - {message}", datefmt="%Y-%m-%d %H:%M:%S")


class State(Enum):
    SELDIR = 1
    MKDIR = 2
    SELDL = 11
    SELUL = 12
    SELDUR = 13

State.END = ConversationHandler.END

def log_error():
    e=traceback.format_exc()
    logging.error(e)


def speed_format(kbps):
    if kbps < 1000:
        return f'{kbps} KB/s'
    return f'{kbps/1000:.2f} MB/s'    

def restricted_template(func, *, whitelist):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in whitelist:
            return
        return func(update, context, *args, **kwargs)
    return wrapped


class TBot():
    def __init__(self, cfg_path, db_path):
        with open(cfg_path) as f:
            config = json.load(f)

        self.admins = config['admins']
        self.rootdir = config['rootdir']
        self.reserved_space = config['reserved_space']
        self.password = config['password']
        self.client = Transmission(**config['client_cfg'])
        self.updater = Updater(token=config['token'], use_context=True)
        self.dispatcher = self.updater.dispatcher
        self.jq = self.updater.job_queue
        self.db = BotDB(db_path)

        self.try_create_limit_timer()
        self.create_dl_checker()
        self.create_db_updater()
        self.create_disk_checker()

        restricted = partial(restricted_template, whitelist=self.db.whitelist())

        conv_fallbacks = [
            CommandHandler('cancel', self.conv_cancel),
            MessageHandler(Filters.all, self.conv_error)
        ]

        self.handlers = {}
        self.handlers['start'] = (CommandHandler('start', self.start), 0)
        self.handlers['help'] = (CommandHandler('help', restricted(self.help)), 0)
        self.handlers['limit'] = (CommandHandler('limit', restricted(self.limit)), 0)
        self.handlers['setlimit'] = (ConversationHandler(
            [CommandHandler('setlimit', restricted(self.setlimit))],
            {
                State.SELDL: [MessageHandler(Filters.text(list(strings.dl_buttons.keys())), self.sel_dl)],
                State.SELUL: [MessageHandler(Filters.text(list(strings.ul_buttons.keys())), self.sel_ul)],
                State.SELDUR: [MessageHandler(Filters.text(list(strings.dur_buttons.keys())), self.sel_dur)]
            },
            conv_fallbacks
        ), 0)

        self.handlers['mytorr'] = (CommandHandler('my_torrents', restricted(self.my_torrents)), 0)
        self.handlers['alltorr'] = (CommandHandler('all_torrents', restricted(self.all_torrents), filters=Filters.user(user_id=self.admins)), 0)

        self.handlers['newtorr'] = (ConversationHandler(
            [
                MessageHandler(Filters.document.mime_type('application/x-bittorrent'), restricted(self.add_torrent)),
                MessageHandler(Filters.regex(re.compile(r'^magnet:\?', re.I)), restricted(self.add_magnet))
            ],
            {
                State.SELDIR: [MessageHandler(Filters.text(list(strings.dir_buttons.keys())), self.sel_dir)],
                State.MKDIR: [MessageHandler(Filters.text & (~Filters.command), self.make_dir)]
            },
            conv_fallbacks
        ), 0)
        
        self.handlers['list_offset'] = (CallbackQueryHandler(self.list_offset, pattern=offset_query), 0)
        self.handlers['torrent_info'] = (CallbackQueryHandler(self.torrent_info, pattern=hash_query), 0)
        self.handlers['toggle_torrent'] = (CallbackQueryHandler(self.toggle_torrent, pattern=toggle_query), 0)
        self.handlers['del_torrent'] = (CallbackQueryHandler(self.del_torrent, pattern=del_query), 0)

        self.handlers['disk'] = (CommandHandler('disk', restricted(self.show_disk_usage)), 0)
        self.handlers['auth']= (MessageHandler(Filters.text & (~Filters.command), self.auth), 1)

        for h, gr in self.handlers.values():
            self.dispatcher.add_handler(h, group=gr)

        self.updater.start_polling()
        self.updater.idle()

    def answer(self, update, context, msg, **kwargs):
        context.bot.send_message(chat_id=update.effective_chat.id, text=msg, **kwargs)

    def answer_callback(self, update, context, msg, **kwargs):
        context.bot.answer_callback_query(update.callback_query.id, text=msg, **kwargs)

# --------------------------------------------------------------------------------------------------
# oneline commands
# --------------------------------------------------------------------------------------------------

    def start(self, update, context):
        self.answer(update, context, 'Input password to continue!')

    def help(self, update, context):
        context.bot.send_message(chat_id=update.effective_chat.id, text=strings.help)

    def limit(self, update, context):
        active, descr = self.get_limit_info()
        self.answer(update, context, descr)

    def show_disk_usage(self, update, context):
        # disk = [ used | available | root-reserved ]
        # available = [ reported as available | reserved by us ]
        used, avail = self.get_disk_stats()
        avail = max(0, avail - self.reserved_space)
        self.answer(update, context, strings.disk_usage.format(strings.format_size(used), strings.format_size(used + avail), used / (used + avail) * 100))

    def auth(self, update, context):
        user = update.effective_user.id
        if user in self.db.whitelist():
            return
        if update.message.text == self.password:
            self.db.whitelist_user(user)
            msg = 'You are now authorized!'
        else:
            msg = 'Incorrect password!'
        self.answer(update, context, msg)

# --------------------------------------------------------------------------------------------------
# setlimit conversation
# --------------------------------------------------------------------------------------------------

    def setlimit(self, update, context):
        self.answer(update, context, strings.select_dl, reply_markup=ReplyKeyboardMarkup(strings.dl_kb, resize_keyboard=True))
        return State.SELDL

    def sel_dl(self, update, context):
        context.chat_data['dl'] = strings.dl_buttons[update.message.text]
        self.answer(update, context, strings.select_ul, reply_markup=ReplyKeyboardMarkup(strings.ul_kb, resize_keyboard=True))
        return State.SELUL

    def sel_ul(self, update, context):
        context.chat_data['ul'] = strings.ul_buttons[update.message.text]
        if not (context.chat_data['dl'] or context.chat_data['ul']):
            self.cancel_limit_timer()
            self.reset_limit_now()
            self.answer(update, context, strings.limit_reset, reply_markup=ReplyKeyboardRemove())
            self.notify_limit_change(update.effective_user.id)
            context.chat_data.clear()
            return State.END
        self.answer(update, context, strings.select_dur, reply_markup=ReplyKeyboardMarkup(strings.dur_kb, one_time_keyboard=True, resize_keyboard=True))
        return State.SELDUR

    def sel_dur(self, update, context):
        params = {}
        self.set_limit(context.chat_data['dl'], context.chat_data['ul'])
        self.answer(update, context, strings.limit_set, reply_markup=ReplyKeyboardRemove())
        context.chat_data.clear()
        duration = strings.dur_buttons[update.message.text]
        self.db.set_timer(time.time() + duration if duration is not None else None)
        self.try_create_limit_timer()
        self.notify_limit_change(update.effective_user.id)
        return State.END

# --------------------------------------------------------------------------------------------------
# torrent management
# --------------------------------------------------------------------------------------------------

    def show_torrents(self, update, context, torrents, cat, offset=0, message=None):
        #TODO cache torrent list in chat_data?
        def build_menu(torrents, offset, n):
            if not torrents:
                return None
            buttons = [InlineKeyboardButton(str(i+1), callback_data=f'hash={t.hashString},{offset},{cat}') for i, t in enumerate(torrents)]
            cols = [len(torrents)]
            if len(torrents) > 6:
                cols = [len(torrents) - len(torrents) // 2, len(torrents) // 2]
            rows = []
            col_offset = 0
            for col_n in cols:
                rows.append(buttons[col_offset:col_offset + col_n])
                col_offset += col_n
            left_btn = InlineKeyboardButton('⬅', callback_data=f'offset={offset - 10},{cat}' if offset > 0 else f'offset=left,{cat}')
            refresh_btn = InlineKeyboardButton('🔄', callback_data=f'offset={offset},{cat}')
            right_btn = InlineKeyboardButton('➡', callback_data=f'offset={offset + 10},{cat}' if offset + 10 < n else f'offset=right,{cat}')
            rows.append([left_btn, refresh_btn, right_btn])
            return InlineKeyboardMarkup(rows)

        n = len(torrents)
        torrents = torrents[offset:offset + 10]
        msg = strings.format_torrents(torrents, offset, n)
        markup = build_menu(torrents, offset, n)
        if message is None:
            self.answer(update, context, msg, reply_markup=markup)
        else:
            message.edit_text(msg, reply_markup=markup)

    def list_offset(self, update, context):
        offset, owner = context.match.groups()
        if offset == 'left':
            self.answer_callback(update, context, strings.left)
            return
        if offset == 'right':
            self.answer_callback(update, context, strings.right)
            return
        if owner == 'my':
            uid = update.effective_user.id
            torrents = self._get_torrents(self.db.owned_torrents(uid))
        else:
            torrents = self._get_torrents(None)
        try:
            self.show_torrents(update, context, torrents, owner, int(offset), message=update.callback_query.message)
        except BadRequest:
            pass
        update.callback_query.answer()

    def my_torrents(self, update, context):
        uid = update.effective_user.id
        torrents = self._get_torrents(self.db.owned_torrents(uid))
        self.show_torrents(update, context, torrents, 'my')

    def all_torrents(self, update, context):
        torrents = self._get_torrents(None)
        self.show_torrents(update, context, torrents, 'all')

    def _get_torrents(self, ids):
        if ids is not None and not ids:
            return []
        return sorted(self.client.get_torrents(ids=ids, arguments=['id', 'hashString', 'name', 'status', 'progress', 'sizeWhenDone', 'leftUntilDone']), key=lambda t: (t.name, t.hashString))

    def _torrent_info(self, update, context, t_hash, offset, owner, stopping=False):
        def build_menu(t_hash, offset, owner, active):
            action = 'stop' if active else 'run'
            toggle_btn = InlineKeyboardButton('⏸ Остановить' if active else '▶ Запустить', callback_data=f'{action}={t_hash},{offset},{owner}')
            delete_btn = InlineKeyboardButton('❌ Удалить торрент и скачанные файлы', callback_data=f'del={t_hash},{offset},{owner}')
            back_btn = InlineKeyboardButton('↩ Назад', callback_data=f'offset={offset},{owner}')
            refresh_btn = InlineKeyboardButton('🔄', callback_data=f'hash={t_hash},{offset},{owner}')
            return InlineKeyboardMarkup([[toggle_btn], [delete_btn], [back_btn, refresh_btn]])

        torrent = self.client.get_torrent(t_hash)
        msg = strings.format_torrent(torrent, override_status='stopping' if stopping else None)
        try:
            update.callback_query.message.edit_text(msg, reply_markup=build_menu(t_hash, offset, owner, torrent.status!='stopped' and not stopping))
        except BadRequest:
            pass
        update.callback_query.answer()


    def torrent_info(self, update, context):
        t_hash, offset, owner = context.match.groups()
        self._torrent_info(update, context, t_hash, offset, owner)

    def toggle_torrent(self, update, context):
        action, t_hash, offset, owner = context.match.groups()
        if action == 'run':
            self.client.start_torrent(t_hash)
        else:
            self.client.stop_torrent(t_hash)
        self._torrent_info(update, context, t_hash, offset, owner, action != 'run')
        update.callback_query.answer()

    def del_torrent(self, update, context):
        action, t_hash, offset, owner = context.match.groups()
        if action == 'del2':
            self.client.remove_torrent(t_hash, delete_data=True)
            self.db.remove_torrent(t_hash)
            back_btn = InlineKeyboardButton('↩ Назад', callback_data=f'offset={offset},{owner}')
            update.callback_query.message.edit_text(strings.deleted, reply_markup=InlineKeyboardMarkup([[back_btn]]))
        else:
            torrent = self.client.get_torrent(t_hash, arguments=['id', 'hashString', 'name'])
            cancel_btn = InlineKeyboardButton('🚫 Отмена', callback_data=f'hash={t_hash},{offset},{owner}')
            ok_btn = InlineKeyboardButton('❌ Удалить', callback_data=f'del2={t_hash},{offset},{owner}')
            update.callback_query.message.edit_text(strings.del_confirm.format(torrent.name), reply_markup=InlineKeyboardMarkup([[cancel_btn, ok_btn]]))
        update.callback_query.answer()

# --------------------------------------------------------------------------------------------------
# new torrent conversation
# --------------------------------------------------------------------------------------------------

    def add_torrent(self, update, context):
        context.chat_data['torrent'] = update.message.document
        self.answer(update, context, strings.select_dir, reply_markup=ReplyKeyboardMarkup(strings.dir_kb, one_time_keyboard=True, resize_keyboard=True))
        return State.SELDIR

    def add_magnet(self, update, context):
        context.chat_data['magnet'] = update.message.text
        self.answer(update, context, strings.select_dir, reply_markup=ReplyKeyboardMarkup(strings.dir_kb, one_time_keyboard=True, resize_keyboard=True))
        return State.SELDIR

    def sel_dir(self, update, context):
        if not strings.dir_buttons[update.message.text]:
            self.answer(update, context, strings.make_dir, reply_markup=ReplyKeyboardRemove())
            return State.MKDIR
        self._add_torrent(strings.dir_buttons[update.message.text], context, update)
        return State.END

    def make_dir(self, update, context):
        dirname = update.message.text
        if valid_dirname.match(dirname) and dirname not in ['.', '..']:
            self._add_torrent(dirname, context, update)
        else:
            self.answer(update, context, strings.invalid_dirname)
            return State.MKDIR
        return State.END

    def _add_torrent(self, dirname, context, update):
        def client_add(torr_data):
            try:
                session = self.client.get_session()
                torr = self.client.add_torrent(torr_data, download_dir=str(pathlib.Path(session.download_dir).joinpath(dirname).absolute()))
            except Exception as e:
                self.answer(update, context, strings.error, reply_markup=ReplyKeyboardRemove())
                log_error()
                return

            try:
                t_hash = torr.hashString
            except AttributeError:
                logging.error(f'Transmission did not return hash for {torr!r}')
                self.client.remove_torrent(torr.id, delete_data=True)
                self.answer(update, context, strings.nohash, reply_markup=ReplyKeyboardRemove())
                return
            
            uid = update.effective_user.id
            if self.db.has_torrent(t_hash):
                self.answer(update, context, strings.duplicate, reply_markup=ReplyKeyboardRemove())
                return
            self.db.add_torrent(t_hash, uid, active=True)
            self.answer(update, context, strings.added, reply_markup=ReplyKeyboardRemove())

        if context.chat_data.get('torrent'):
            try:
                tfile = context.chat_data['torrent'].get_file()
                with BytesIO() as buf:
                    tfile.download(out=buf)
                    buf.seek(0)
                    client_add(buf)
            except Exception as e:
                self.answer(update, context, strings.error_load_file, reply_markup=ReplyKeyboardRemove())
                log_error()
            del context.chat_data['torrent']
        else:
            client_add(context.chat_data['magnet'])
            del context.chat_data['magnet']

# --------------------------------------------------------------------------------------------------
# conversation fallbacks
# --------------------------------------------------------------------------------------------------

    def conv_cancel(self, update, context):
        context.chat_data.clear()
        self.answer(update, context, strings.cancelled, reply_markup=ReplyKeyboardRemove())
        return State.END

    def conv_error(self, update, context):
        self.answer(update, context, strings.howtocancel)

# --------------------------------------------------------------------------------------------------
# jobs
# --------------------------------------------------------------------------------------------------

    def try_create_limit_timer(self):
        self.cancel_limit_timer()
        timer = self.db.get_timer()
        if timer is None:
            return
        dt = timer - time.time()
        if dt <= 0:
            self.reset_limit_now()
            self.notify_limit_change() #TODO refactor?
        else:
            self.jq.run_once(self.reset_limit, dt)

    def cancel_limit_timer(self):
        for job in self.jq.get_jobs_by_name('reset_limit'):
            job.schedule_removal()

    def create_dl_checker(self): #TODO is db threadsafe? add lock/etc
        self.jq.run_repeating(self.check_downloads, 60, first=5)
 
    def create_disk_checker(self):
        self.jq.run_repeating(self.check_disk, 60 * 10, first=75)
       
    def create_db_updater(self): #TODO is db threadsafe? add lock/etc
        self.jq.run_repeating(self.update_db, 60 * 15, first=30)

# --------------------------------------------------------------------------------------------------
# job callbacks
# --------------------------------------------------------------------------------------------------

    def reset_limit_now(self):
        self.set_limit(None, None)
        self.db.set_timer(None)

    def reset_limit(self, context):
        self.reset_limit_now()
        self.notify_limit_change()

    def process_finished(self, torrents):
        for t_hash, t_name in torrents:
            owner = self.db.get_owner(t_hash)
            if owner is not None:
                self.notify_download_finished(owner, t_name)
        self.db.mark_finished([t[0] for t in torrents])


    def check_downloads(self, context):
        active = self.db.get_active()
        if not active:
            return
        finished = [(t.hashString, t.name)
                    for t in self.client.get_torrents(ids=list(active), arguments=['id', 'hashString', 'name', 'status', 'leftUntilDone'])  # id is used by client
                    if t.status in ['seeding', 'stopped'] and t.leftUntilDone == 0]
        if finished:
            self.process_finished(finished)

    def check_disk(self, context):
        used, avail = self.get_disk_stats()
        if avail <= self.reserved_space and not self.db.disk_full():
            #TODO thread-safety for client and db?
            self.update_db(context) # is it ok?  #if executed with db updater (in different thread) (is it possible?)
            active = self.db.get_active()
            if active:
                self.client.stop_torrent(ids=list(active))
                self.db.mark_finished(list(self.db.get_active()))
            self.notify_disk_full(True)
            self.db.set_disk_full(True)
        if avail > self.reserved_space and self.db.disk_full():
            self.notify_disk_full(False)
            self.db.set_disk_full(False)

    def update_db(self, context):
        torrents = self.client.get_torrents(arguments=['id', 'hashString', 'name', 'status', 'leftUntilDone'])  # id is used by client
        active = self.db.get_active()
        finished = [(t.hashString, t.name) for t in torrents if t.status in ['seeding', 'stopped'] and t.leftUntilDone == 0 and t.hashString in active]
        if finished:
            self.process_finished(finished)
        self.db.update_torrents([(t.hashString, t.status not in ['seeding', 'stopped'] or t.leftUntilDone > 0) for t in torrents])

# --------------------------------------------------------------------------------------------------
# notifications
# --------------------------------------------------------------------------------------------------

    def notify_limit_change(self, origin=None):
        # TODO async? is session threadsafe?
        # NOTE is spam limit an issue?
        active, descr = self.get_limit_info()
        if active:
            msg = strings.notif_limit_set + descr
        else:
            msg = strings.notif_limit_reset
        for user in self.db.whitelist():
            if user != origin:
                self.updater.bot.send_message(chat_id=user, text=msg, disable_notification=True)

    def notify_download_finished(self, user, title):
        self.updater.bot.send_message(chat_id=user, text=strings.finished.format(title))

    def notify_disk_full(self, full):
        # TODO async?
        # NOTE is spam limit an issue?
        msg = strings.disk_full if full else strings.disk_ok
        for user in self.db.whitelist():
            self.updater.bot.send_message(chat_id=user, text=msg)

# --------------------------------------------------------------------------------------------------
# utils
# --------------------------------------------------------------------------------------------------

    def get_limit_info(self):
        session = self.client.get_session()
        if session.speed_limit_down_enabled:
            dl_limit = speed_format(session.speed_limit_down)
        else:
            dl_limit = '-'
        if session.speed_limit_up_enabled:
            ul_limit = speed_format(session.speed_limit_up)
        else:
            ul_limit = '-'
        timer = self.db.get_timer()
        if dl_limit == ul_limit == '-' or timer is None:
            return not dl_limit == ul_limit == '-', strings.perm_limit.format(dl_limit, ul_limit)
        else:
            timer_end = time.strftime('%H:%M:%S %Z', time.localtime(timer)) if timer > time.time() else strings.soon
            return True, strings.temp_limit.format(dl_limit, ul_limit, timer_end)

    def set_limit(self, dl, ul):
        params = {
            'speed_limit_down_enabled': dl is not None,
            'speed_limit_up_enabled': ul is not None
        }
        if dl is not None:
            params['speed_limit_down'] = dl
        if ul is not None:
            params['speed_limit_up'] = ul
        self.client.set_session(**params)

    def get_disk_stats(self):
        stats = os.statvfs(self.rootdir)
        used = (stats.f_blocks - stats.f_bfree) * stats.f_bsize
        avail = stats.f_bavail * stats.f_bsize
        return used, avail

# --------------------------------------------------------------------------------------------------
# BOT END
# --------------------------------------------------------------------------------------------------

def main():
    cfg_path = str(BASE_DIR.joinpath('config.json').absolute())
    db_path = str(BASE_DIR.joinpath('data.db').absolute())
    bot = TBot(cfg_path, db_path)


if __name__ == '__main__':
    main()
