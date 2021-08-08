import re

class Driver:
    valid_dirname = re.compile(r'^[\w. -]+$')

    def __init__(self, *, data_dir, reserved_space, client_cfg, ftp_cfg, job_queue):
        self.ftp_enabled = ...

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
