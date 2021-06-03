#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from .evm import EVM

class Emulator:
    def __init__(self, host, port, block, debug=False):
        self._evm = EVM(debug)
        self._evm.set_vm(host, port, block)

    def take_snapshot(self):
        self._evm.snapshot()

    def restore_from_snapshot(self):
        self._evm.restore()

    def send_transaction(self, transaction):
        return self._evm.deploy_transaction(transaction)
