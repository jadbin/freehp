# coding=utf-8


class UsageError(Exception):
    """
    CLI usage error.
    """

    def __init__(self, *args, **kwargs):
        self.print_help = kwargs.pop('print_help', True)
        super().__init__(*args, **kwargs)


class NoProxyAvailable(Exception):
    """
    No proxy available.
    """


class DownloadingError(Exception):
    """
    Unable to download.
    """
