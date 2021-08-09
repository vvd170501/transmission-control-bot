import re
import sqlite3
from enum import Flag
from pathlib import Path

from . import strings


class FlagPreferences(Flag):
    default_share = (1, False)
    private_notifications = (2, True)
    shared_notifications = (4, False)

    def __new__(cls, value, default_value):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.default_value = default_value
        return obj

    def description(self):
        if self.name is None:
            raise NotImplementedError()  # multiple or zero values
        return getattr(strings.Preferences, self.name)['description']

    def status_description(self, value):
        if self.name is None:
            raise NotImplementedError()
        return getattr(strings.Preferences, self.name)['values'][value]['status']

    def choice_description(self, value):
        if self.name is None:
            raise NotImplementedError()
        return getattr(strings.Preferences, self.name)['values'][value]['choice']


class Driver:
    valid_dirname = re.compile(r'^[\w. -]+$')

    def __init__(self, *, data_dir: Path, reserved_space: int, client_cfg, ftp_cfg, job_queue):
        self._db = sqlite3.Connection(data_dir / 'data.db')
        ...
        self._init_db()

    @property
    def ftp_enabled(self):
        return ...

    def get_whitelist(self):
        ...

    def whitelist_user(self, user):
        ...

    def get_speed_limits(self):
        ...

    def get_disk_usage(self):
        ...

    def share_root_ftp(self):
        ...

    def unshare_root_ftp(self):
        ...

    def is_valid_dirname(self, dirname):
        return self.valid_dirname.match(dirname) and dirname not in ['.', '..']

    def _init_db(self):
        pass
