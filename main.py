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
    cfg_path = Path(args.config)
    data_dir = Path(args.data) if args.data else cfg_path.parent.joinpath('data').absolute()
    bot = TBot(cfg_path, data_dir)
    bot.run()


if __name__ == '__main__':
    main()
