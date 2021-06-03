#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from copy import deepcopy

from eth_hash.auto import keccak
from eth_typing import Address, Hash32

from eth.constants import BLANK_ROOT_HASH, EMPTY_SHA3
from eth.db.atomic import AtomicDB
from eth.db.backends.memory import MemoryDB
from eth.db.account import AccountDatabaseAPI
from eth.db.journal import JournalDBCheckpoint
from eth.rlp.accounts import Account
from eth.tools._utils.normalization import to_int
from eth.validation import validate_uint256, validate_canonical_address, validate_is_bytes

from web3 import Web3, HTTPProvider

class EmulatorMemoryDB(MemoryDB):
    def __init__(self) -> None:
        self.kv_store = {'storage': dict(), 'account': dict(), 'code': dict()}

    def reset(self) -> None:
        self.kv_store = {'storage': dict(), 'account': dict(), 'code': dict()}

class EmulatorAccountDB(AccountDatabaseAPI):
    def __init__(self, db: AtomicDB, state_root: Hash32 = BLANK_ROOT_HASH) -> None:
        self.state_root = BLANK_ROOT_HASH
        self._raw_store_db = db
        self._cache_store_db = deepcopy(self._raw_store_db)

    def set_http_provider(self, host, port) -> None:
        self._w3 = Web3(HTTPProvider('http://'+host+':'+str(port)))
        self._fallback = self._w3.eth

    def set_fork_block_numer(self, block_number) -> None:
        self._fork_block_number = block_number
        if not self._fork_block_number:
            self._fork_block_number = self._fallback.blockNumber

    @property
    def state_root(self) -> Hash32:
        return self._state_root

    @state_root.setter
    def state_root(self, value: Hash32) -> None:
        self._state_root = value

    @property
    def _storage(self):
        return self._raw_store_db["storage"]

    @property
    def _cache_storage(self):
        return self._cache_store_db["storage"]

    @property
    def _account(self):
        return self._raw_store_db["account"]

    @property
    def _cache_account(self):
        return self._cache_store_db["account"]

    @property
    def _code(self):
        return self._raw_store_db["code"]

    @property
    def _cache_code(self):
        return self._cache_store_db["code"]

    def _get_storage(self, address: Address, slot: int, from_journal: bool = True) -> int:
        if address not in self._cache_account:
            self._get_account(address)
        if slot not in self._cache_storage[address]:
            result = self._fallback.getStorageAt(address, slot, self._fork_block_number)
            result = to_int(result.hex())
            self._storage[address][slot] = result
            self._cache_storage[address][slot] = result
        return self._cache_storage[address][slot]

    def get_storage(self, address: Address, slot: int, from_journal: bool = True) -> int:
        validate_canonical_address(address, title="Storage Address")
        validate_uint256(slot, title="Storage Slot")
        return self._get_storage(address, slot)

    def set_storage(self, address: Address, slot: int, value: int) -> None:
        validate_uint256(value, title="Storage Value")
        validate_uint256(slot, title="Storage Slot")
        validate_canonical_address(address, title="Storage Address")
        if address not in self._cache_storage:
            self._cache_storage[address] = dict()
        self._cache_storage[address][slot] = value

    def delete_storage(self, address: Address) -> None:
        validate_canonical_address(address, title="Storage Address")
        if address in self._cache_storage:
            del self._cache_storage[address]

    def _get_account(self, address: Address) -> Account:
        if address not in self._cache_account:
            code = self._fallback.getCode(address, self._fork_block_number)
            if code:
                code_hash = keccak(code)
                self._code[code_hash] = code
                self._cache_code[code_hash] = code
            else:
                code_hash = EMPTY_SHA3
            account = Account(
                int(self._fallback.getTransactionCount(address, self._fork_block_number)),
                self._fallback.getBalance(address, self._fork_block_number),
                BLANK_ROOT_HASH,
                code_hash
            )
            self._cache_account[address] = account.copy()
            self._account[address] = account.copy()
            self._cache_storage[address] = dict()
            self._storage[address] = dict()
        return self._cache_account[address]

    def _has_account(self, address: Address) -> bool:
        return address in self._cache_account

    def _set_account(self, address: Address, account: Account) -> None:
        self._cache_account[address] = account

    def _set_adversary_account(self, address: Address,
                               account: Account) -> None:
        self._cache_account[address] = account
        self._account[address] = account

    def get_nonce(self, address: Address) -> int:
        validate_canonical_address(address, title="Storage Address")
        a = self._get_account(address)
        return a.nonce

    def set_nonce(self, address: Address, nonce: int) -> None:
        validate_canonical_address(address, title="Storage Address")
        validate_uint256(nonce, title="Nonce")
        account = self._get_account(address)
        self._set_account(address, account.copy(nonce=nonce))

    def increment_nonce(self, address: Address):
        current_nonce = self.get_nonce(address)
        self.set_nonce(address, current_nonce + 1)

    def get_balance(self, address: Address) -> int:
        validate_canonical_address(address, title="Storage Address")
        return self._get_account(address).balance

    def set_balance(self, address: Address, balance: int) -> None:
        validate_canonical_address(address, title="Storage Address")
        validate_uint256(balance, title="Account Balance")
        account = self._get_account(address)
        self._set_account(address, account.copy(balance=balance))

    def set_code(self, address: Address, code: bytes) -> None:
        validate_canonical_address(address, title="Storage Address")
        validate_is_bytes(code, title="Code")
        account = self._get_account(address)
        code_hash = keccak(code)
        self._cache_code[code_hash] = code
        self._set_account(address, account.copy(code_hash=code_hash))

    def get_code(self, address: Address) -> bytes:
        validate_canonical_address(address, title="Storage Address")
        code_hash = self.get_code_hash(address)
        if code_hash == EMPTY_SHA3:
            return b''
        elif code_hash in self._cache_code:
            return self._cache_code[code_hash]
        else:
            raise KeyError

    def get_code_hash(self, address: Address) -> Hash32:
        validate_canonical_address(address, title="Storage Address")
        account = self._get_account(address)
        return account.code_hash

    def delete_code(self, address: Address) -> None:
        validate_canonical_address(address, title="Storage Address")
        account = self._get_account(address)
        code_hash = account.code_hash
        self._set_account(address, account.copy(code_hash=EMPTY_SHA3))
        if code_hash in self._code:
            del self._code[code_hash]

    def account_is_empty(self, address: Address) -> bool:
        return not self.account_has_code_or_nonce(address) and \
            self.get_balance(address) == 0

    def account_has_code_or_nonce(self, address):
        return self.get_nonce(address) != 0 or \
            self.get_code_hash(address) != EMPTY_SHA3

    def account_exists(self, address: Address) -> bool:
        validate_canonical_address(address, title="Storage Address")
        return address in self._cache_account

    def touch_account(self, address: Address) -> None:
        validate_canonical_address(address, title="Storage Address")
        account = self._get_account(address)
        self._set_account(address, account)

    def delete_account(self, address: Address) -> None:
        validate_canonical_address(address, title="Storage Address")
        self.delete_code(address)
        if address in self._cache_storage:
            del self._cache_storage[address]
        if address in self._cache_account:
            del self._cache_account[address]

    def record(self) -> AtomicDB:
        checkpoint = deepcopy(self._cache_store_db)
        return checkpoint

    def discard(self, checkpoint: AtomicDB) -> None:
        self._cache_store_db = deepcopy(checkpoint)

    def commit(self, checkpoint: JournalDBCheckpoint) -> None:
        pass

    def make_state_root(self) -> Hash32:
        return None

    def persist(self) -> None:
        pass

    def has_root(self, state_root: bytes) -> bool:
        return False

    def restore(self) -> None:
        self._cache_store_db = deepcopy(self._raw_store_db)

    def snapshot(self) -> None:
        self._raw_store_db = deepcopy(self._cache_store_db)
