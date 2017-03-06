# coding=utf-8

import yaml


def load_config_file(file):
    with open(file, "r", encoding="utf-8") as f:
        d = yaml.load(f)
        return d


def dump_config_file(file, config):
    with open(file, "w", encoding="utf-8") as f:
        yaml.dump(config, f)
