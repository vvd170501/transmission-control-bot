#!/usr/bin/env python3
import argparse
import logging
import sys
from pathlib import Path

from tbot import TBot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', metavar='FILE', help='Config file', required=True)
    parser.add_argument('--data', metavar='PATH',
                        help='Path to data files (default: "%%config_directory%%/data")')
    parser.add_argument('--log', metavar='FILE', help='Log file (default: write to stderr)')
    parser.add_argument('-v', '--verbose', action='count', default=0)
    args = parser.parse_args()

    loglevel = {
        0: logging.WARNING,
        1: logging.INFO,
        2: logging.DEBUG
    }.get(args.verbose, logging.DEBUG)  # max verbosity level = 2

    logging_cfg = {
        'style': '{',
        'format': '[{asctime}] {threadName}:{levelname} - {message}',
        'datefmt': '%Y-%m-%d %H:%M:%S',
        'level': loglevel
    }
    if args.log:
        logging_cfg['filename'] = args.log
    else:
        logging_cfg['stream'] = sys.stderr
    logging.basicConfig(**logging_cfg)
    cfg_path = Path(args.config)
    data_dir = Path(args.data) if args.data else cfg_path.parent.joinpath('data').absolute()
    bot = TBot(cfg_path, data_dir)
    bot.run()


if __name__ == '__main__':
    main()
