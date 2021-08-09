import re
from abc import abstractmethod, ABC

from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from . import strings
from .strings import Buttons


class CallbackQueryActions:
    show_list_part = 'list'
    show_item = 'item'
    start_torrent = 'run'
    stop_torrent = 'stop'
    show_ftp = 'ftp'
    share_ftp = '+ftp'
    unshare_ftp = '-ftp'
    share_torrent = '+shr'
    unshare_torrent = '-shr'
    move_torrent = 'move'
    delete_torrent = 'del'
    confirm_deletion = 'del2'


class PreferenceActions:
    default_share = 'shr'


def query_pattern(action_names, **part_patterns):
    # additional regex optimization is not worth it
    action_name = '|'.join(map(re.escape, action_names))
    part_groups = ','.join(
        f'(?P<{part_name}>{pattern})' for part_name, pattern in part_patterns.items()
    )
    return re.compile(
        f'^(?P<action>{action_name})={part_groups}$'
    )


def item_query_pattern(action_names):
    return query_pattern(action_names, item=r'\w+', list_location=r'\d+,\w+')


def query_action(action_name, **parts):
    return f'{action_name}={",".join(value for value in parts.values())}'


def item_query_action(action_name, item, list_location):
    return query_action(action_name, item=item, list_location=list_location)


def build_list_location(offset, category):
    return f'{offset},{category}'


def split_list_location(location):
    offset, category = location.split(',')
    return {'offset': offset, 'category': category}


class CallbackQueryPatterns:
    # if more preferences are added, use one regex for all?
    default_share = query_pattern(
        [PreferenceActions.default_share],
        value=r'[?01]'
    )

    # "offset" and "hash" actions were used in previous versions
    show_list_part = query_pattern(
        [CallbackQueryActions.show_list_part, 'offset'],
        offset=r'\w+', category=r'\w+'
    )
    show_item = item_query_pattern([
        CallbackQueryActions.show_item, 'hash'
    ])
    toggle_torrent_status = item_query_pattern([
        CallbackQueryActions.start_torrent,
        CallbackQueryActions.stop_torrent
    ])
    ftp_control = item_query_pattern([
        CallbackQueryActions.show_ftp,
        CallbackQueryActions.share_ftp,
        CallbackQueryActions.unshare_ftp
    ])
    edit_share_status = item_query_pattern([
        CallbackQueryActions.share_torrent,
        CallbackQueryActions.unshare_torrent
    ])
    move_torrent = item_query_pattern([
        CallbackQueryActions.move_torrent
    ])
    delete_torrent = item_query_pattern([
        CallbackQueryActions.delete_torrent,
        CallbackQueryActions.confirm_deletion
    ])


class InlineKeyboard(ABC):
    def build(self):
        return InlineKeyboardMarkup(self._buttons())

    @abstractmethod
    def _buttons(self):
        raise NotImplementedError()


class PreferencesKeyboard(InlineKeyboard):
    EDIT = '?'

    def __init__(self, preferences):
        self.preferences = preferences

    def _buttons(self):
        default_share = InlineKeyboardButton(
            Buttons.default_share,
            callback_data=query_action(PreferenceActions.default_share, value=self.EDIT)
        )
        return [
            [default_share],
        ]


class PreferenceEditKeyboard(InlineKeyboard):
    def __init__(self, pref_name):
        # NOTE pref_name -- full preference name (attr of PreferenceActions). rewrite later?
        self.pref_name = pref_name

    def _buttons(self):
        options = getattr(strings.Preferences, self.pref_name).values()
        return [
            [InlineKeyboardButton(
                description,
                callback_data=query_action(getattr(PreferenceActions, self.pref_name), value=value))
            ] for description, value in options
        ]


class ListNavigationKeyboard(InlineKeyboard):
    LEFT = 'left'
    RIGHT = 'right'

    # pass args in initializer?
    def __init__(self, items, elements_per_page, current_offset, total_count, list_category):
        self.items = items
        self.step = elements_per_page
        self.offset = current_offset
        self.max_index = total_count
        self.category = list_category

    def _buttons(self):
        left_offset = self.offset - self.step if self.offset > 0 else self.LEFT
        right_offset = (self.offset + self.step if self.offset + self.step < self.max_index
                        else self.RIGHT)
        navigation_row = [
            InlineKeyboardButton(
                Buttons.left,
                callback_data=query_action(
                    CallbackQueryActions.show_list_part,
                    offset=left_offset, category=self.category
                )
            ),
            InlineKeyboardButton(
                Buttons.refresh,
                callback_data=query_action(
                    CallbackQueryActions.show_list_part,
                    offset=self.offset, category=self.category
                )
            ),
            InlineKeyboardButton(
                Buttons.right,
                callback_data=query_action(
                    CallbackQueryActions.show_list_part,
                    offset=right_offset, category=self.category
                )
            )
        ]

        if not self.items:  # still need update button. Full row is used for consistency
            return [navigation_row]
        buttons = [
            InlineKeyboardButton(
                str(index + 1),
                callback_data=item_query_action(
                    CallbackQueryActions.show_item,
                    item, build_list_location(self.offset, self.category)
                )
            ) for index, item in enumerate(self.items)
        ]
        if len(self.items) <= 6:
            rows = [buttons]
        else:  # too many buttons for a nice single row
            # if odd, extra button goes to the first row
            mid_point = len(self.items) - len(self.items) // 2
            rows = [buttons[:mid_point], buttons[mid_point:]]
        rows.append(navigation_row)
        return rows


class ItemActionsKeyboard(InlineKeyboard):
    def __init__(self, item_id, list_location):
        self.item_id = item_id
        self.list_location = list_location

    def _action(self, action_name):
        return item_query_action(action_name, self.item_id, self.list_location)


class TorrentControlKeyboard(ItemActionsKeyboard):
    def __init__(self, item_id, list_location, is_active, is_owned, is_shared, need_ftp_control):
        super().__init__(item_id, list_location)
        self.is_active = is_active
        self.is_owned = is_owned
        self.is_shared = is_shared
        self.need_ftp_control = need_ftp_control

    def _own_torrent_controls_head(self):
        # need a better method name? or try rewriting logic
        toggle_btn = InlineKeyboardButton(
            Buttons.stop_torrent if self.is_active else Buttons.start_torrent,
            callback_data=self._action(
                CallbackQueryActions.stop_torrent if self.is_active
                else CallbackQueryActions.start_torrent
            )
        )
        return [
            [toggle_btn]
        ]

    def _ftp_controls(self):
        ftp_btn = InlineKeyboardButton(
            Buttons.ftp_settings,
            callback_data=self._action(CallbackQueryActions.show_ftp)
        )
        return [
            [ftp_btn]
        ]

    def _own_torrent_controls(self):
        toggle_share_btn = InlineKeyboardButton(
            Buttons.unshare_torrent if self.is_shared else Buttons.share_torrent,
            callback_data=self._action(
                CallbackQueryActions.unshare_torrent if self.is_shared
                else CallbackQueryActions.share_torrent
            )
        )
        move_btn = InlineKeyboardButton(
            Buttons.move_torrent,
            callback_data=self._action(CallbackQueryActions.show_ftp)
        )
        delete_btn = InlineKeyboardButton(
            Buttons.delete_torrent,
            callback_data=self._action(CallbackQueryActions.delete_torrent)
        )
        return [
            [toggle_share_btn],
            [move_btn],
            [delete_btn]
        ]

    def _buttons(self):
        back_btn = InlineKeyboardButton(
            Buttons.back,
            callback_data=query_action(
                # use **split_list_location(self.list_location)?
                CallbackQueryActions.show_list_part, list_location=self.list_location
            )
        )
        refresh_btn = InlineKeyboardButton(
            Buttons.refresh,
            callback_data=self._action(CallbackQueryActions.show_item)
        )
        rows = []
        if self.is_owned:
            rows += self._own_torrent_controls_head()  # start/stop
        if self.need_ftp_control:
            rows += self._ftp_controls()
        if self.is_owned:
            rows += self._own_torrent_controls()  # (un)share, move, delete
        rows += [
            [back_btn, refresh_btn]
        ]
        return rows


class FTPControlKeyboard(ItemActionsKeyboard):
    def __init__(self, item_id, list_location, is_shared):
        super().__init__(item_id, list_location)
        self.is_shared = is_shared

    def _buttons(self):
        start_btn = InlineKeyboardButton(
            Buttons.ftp_share if not self.is_shared else Buttons.ftp_renew,
            callback_data=self._action(CallbackQueryActions.share_ftp)
        )
        stop_btn = InlineKeyboardButton(
            Buttons.ftp_unshare,
            callback_data=self._action(CallbackQueryActions.unshare_ftp)
        )
        back_btn = InlineKeyboardButton(
            Buttons.back,
            callback_data=self._action(CallbackQueryActions.show_item)
        )
        return [[start_btn], [stop_btn], [back_btn]]


class DeletionConfirmationKeyboard(ItemActionsKeyboard):
    def _buttons(self):
        cancel_btn = InlineKeyboardButton(
            Buttons.cancel,
            callback_data=self._action(CallbackQueryActions.show_item)
        )
        confirmation_btn = InlineKeyboardButton(
            Buttons.delete,
            callback_data=self._action(CallbackQueryActions.confirm_deletion)
        )
        return [[cancel_btn, confirmation_btn]]


class ReturnToListKeyboard(InlineKeyboard):
    def __init__(self, list_location):
        self.list_location = list_location

    def _buttons(self):
        back_btn = InlineKeyboardButton(
            Buttons.back,
            callback_data=query_action(
                CallbackQueryActions.show_list_part,
                list_location=self.list_location
            )
        )
        return [[back_btn]]
