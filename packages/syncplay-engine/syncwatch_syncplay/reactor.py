"""Explicitly select the same upstream reactor on each supported target."""

import sys


def install():
    from twisted.internet.selectreactor import SelectReactor, install as install_select
    if "twisted.internet.reactor" not in sys.modules:
        install_select()
    from twisted.internet import reactor
    if not isinstance(reactor, SelectReactor):
        raise RuntimeError("The headless runtime requires the selected upstream select reactor")
    return reactor
