import re


class QPMeta(type):
    def __call__(cls, action_names, **part_patterns):
        # additional regex optimization is not worth it
        action_name = '|'.join(map(re.escape, action_names))
        part_groups = ','.join(
            f'(?P<{part_name}>{pattern})' for part_name, pattern in part_patterns.items()
        )
        return re.compile(
            f'^(?P<action>{action_name})={part_groups}$'
        )


class QueryPattern(metaclass=QPMeta):
    @classmethod
    def item_query(cls, action_names):
        return cls(action_names, item=r'\w+', list_location=r'\d+,\w+')


class CallbackQueryActions:
    default_share_status = 'shr'
    show_list_part = 'list'
    show_torrent_info = 'item'
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


class CallbackQueryPatterns:
    # "offset" and "hash" actions were used in previous versions
    default_share_status = QueryPattern(
        [CallbackQueryActions.default_share_status],
        value=r'[01]'
    )

    show_list_part = QueryPattern(
        [CallbackQueryActions.show_list_part, 'offset'],
        offset=r'\w+', category=r'\w+'
    )
    show_torrent_info = QueryPattern.item_query([
        CallbackQueryActions.show_torrent_info, 'hash'
    ])
    toggle_torrent_status = QueryPattern.item_query([
        CallbackQueryActions.start_torrent,
        CallbackQueryActions.stop_torrent
    ])
    ftp_control = QueryPattern.item_query([
        CallbackQueryActions.show_ftp,
        CallbackQueryActions.share_ftp,
        CallbackQueryActions.unshare_ftp
    ])
    edit_share_status = QueryPattern.item_query([
        CallbackQueryActions.share_torrent,
        CallbackQueryActions.unshare_torrent
    ])
    move_torrent = QueryPattern.item_query([
        CallbackQueryActions.move_torrent
    ])
    delete_torrent = QueryPattern.item_query([
        CallbackQueryActions.delete_torrent,
        CallbackQueryActions.confirm_deletion
    ])
