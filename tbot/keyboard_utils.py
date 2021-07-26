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
    show_list_part = 'list'
    show_torrent_info = 'item'
    start_torrent = 'run'
    stop_torrent = 'stop'
    show_ftp = 'ftp'
    share_ftp = '+ftp'
    unshare_ftp = '-ftp'
    delete_torrent = 'del'
    conform_deletion = 'del2'


class CallbackQueryPatterns:
    # "offset" and "hash" actions were used in previous versions
    show_list_part = QueryPattern(
        [CallbackQueryActions.show_list_part, 'offset'],
        offset=r'\w+', category=r'\w+'
    )
    show_torrent_info = QueryPattern.item_query([CallbackQueryActions.show_torrent_info, 'hash'])
    toggle_torrent_status = QueryPattern.item_query([
        CallbackQueryActions.start_torrent,
        CallbackQueryActions.stop_torrent
    ])
    ftp_control = QueryPattern.item_query([
        CallbackQueryActions.show_ftp,
        CallbackQueryActions.share_ftp,
        CallbackQueryActions.unshare_ftp
    ])
    delete_torrent = QueryPattern.item_query([
        CallbackQueryActions.delete_torrent,
        CallbackQueryActions.conform_deletion
    ])
