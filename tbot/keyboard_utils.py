import re

from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from strings import Buttons


class CallbackQueryActions:
    default_share_status = 'shr'
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
    return location.split(',')


class CallbackQueryPatterns:
    # "offset" and "hash" actions were used in previous versions
    default_share_status = query_pattern(
        [CallbackQueryActions.default_share_status],
        value=r'[01]'
    )

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


class PreferencesKeyboard:
    ...  # TODO!!


class ListNavigationKeyboard:
    LEFT = 'left'
    RIGHT = 'right'

    # pass args in initializer?
    def build(self, items, elements_per_page, current_offset, total_count, list_category):
        step = elements_per_page
        left_offset = current_offset - step if current_offset > 0 else self.LEFT
        right_offset = current_offset + step if current_offset + step < total_count else self.RIGHT
        navigation_row = [
            InlineKeyboardButton(
                Buttons.left,
                callback_data=query_action(
                    CallbackQueryActions.show_list_part,
                    offset=left_offset, category=list_category
                )
            ),
            InlineKeyboardButton(
                Buttons.refresh,
                callback_data=query_action(
                    CallbackQueryActions.show_list_part,
                    offset=current_offset, category=list_category
                )
            ),
            InlineKeyboardButton(
                Buttons.right,
                callback_data=query_action(
                    CallbackQueryActions.show_list_part,
                    offset=right_offset, category=list_category
                )
            )
        ]

        if not items:  # still need update button. Full row is used for consistency
            return InlineKeyboardMarkup([navigation_row])
        buttons = [
            InlineKeyboardButton(
                str(index + 1),
                callback_data=item_query_action(
                    CallbackQueryActions.show_item,
                    item, build_list_location(current_offset, list_category)
                )
            ) for index, item in enumerate(items)
        ]
        if len(items) <= 6:
            rows = [buttons]
        else:  # too many buttons for a nice single row
            # if odd, extra button goes to the first row
            mid_point = len(items) - len(items) // 2
            rows = [buttons[:mid_point], buttons[mid_point:]]
        rows.append(navigation_row)
        return InlineKeyboardMarkup(rows)


class ItemActionsKeyboard:
    def __init__(self, item_id, list_location):
        self.item_id = item_id
        self.list_location = list_location

    def _action(self, action_name):
        return item_query_action(action_name, self.item_id, self.list_location)


class TorrentControlKeyboard(ItemActionsKeyboard):
    def build(self, is_active, is_owned, is_shared, need_ftp_control):
        toggle_btn = InlineKeyboardButton(
            Buttons.stop_torrent if is_active else Buttons.start_torrent,
            callback_data=self._action(
                CallbackQueryActions.stop_torrent if is_active
                else CallbackQueryActions.start_torrent
            )
        )
        # TODO don't create unused buttons? check perf impact
        ftp_btn = InlineKeyboardButton(
            Buttons.ftp_settings,
            callback_data=self._action(CallbackQueryActions.show_ftp)
        )
        toggle_share_btn = InlineKeyboardButton(
            Buttons.unshare_torrent if is_shared else Buttons.share_torrent,
            callback_data=self._action(
                CallbackQueryActions.unshare_torrent if is_shared
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
        back_btn = InlineKeyboardButton(
            Buttons.back,
            callback_data=query_action(
                CallbackQueryActions.show_list_part, list_location=self.list_location  # use split?
            )
        )
        refresh_btn = InlineKeyboardButton(
            Buttons.refresh,
            callback_data=self._action(CallbackQueryActions.show_item)
        )

        rows = [
            [toggle_btn]
        ]
        if need_ftp_control:
            rows.append([ftp_btn])
        if is_owned:
            rows += [
                [toggle_share_btn],
                [move_btn],
                [delete_btn]
            ]
        rows += [back_btn, refresh_btn]
        return InlineKeyboardMarkup(rows)


class FTPControlKeyboard(ItemActionsKeyboard):
    def build(self, is_shared):
        start_btn = InlineKeyboardButton(
            Buttons.ftp_share if not is_shared else Buttons.ftp_renew,
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
        return InlineKeyboardMarkup([[start_btn], [stop_btn], [back_btn]])


class DeletionConfirmationKeyboard(ItemActionsKeyboard):
    def build(self):
        cancel_btn = InlineKeyboardButton(
            Buttons.cancel,
            callback_data=self._action(CallbackQueryActions.show_item)
        )
        confirmation_btn = InlineKeyboardButton(
            Buttons.delete,
            callback_data=self._action(CallbackQueryActions.confirm_deletion)
        )
        return InlineKeyboardMarkup([[cancel_btn, confirmation_btn]])


class ReturnToListKeyboard:
    def __init__(self, list_location):
        self.list_location = list_location

    def build(self):
        back_btn = InlineKeyboardButton(
            Buttons.back,
            callback_data=query_action(
                CallbackQueryActions.show_list_part,
                list_location=self.list_location
            )
        )
        return InlineKeyboardMarkup([[back_btn]])
