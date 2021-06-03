#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from .db import EmulatorMemoryDB, EmulatorAccountDB

from eth import Chain, constants
from eth.chains.mainnet import (
    MAINNET_GENESIS_HEADER,
    HOMESTEAD_MAINNET_BLOCK,
    TANGERINE_WHISTLE_MAINNET_BLOCK,
    SPURIOUS_DRAGON_MAINNET_BLOCK,
    BYZANTIUM_MAINNET_BLOCK,
    PETERSBURG_MAINNET_BLOCK,
    ISTANBUL_MAINNET_BLOCK,
    MUIR_GLACIER_MAINNET_BLOCK,
)
from eth.chains.mainnet import MainnetHomesteadVM
from eth.vm.forks import (
    FrontierVM,
    TangerineWhistleVM,
    SpuriousDragonVM,
    ByzantiumVM,
    PetersburgVM,
    IstanbulVM,
    MuirGlacierVM
)
from eth.vm.forks.frontier import FrontierState
from eth.vm.forks.homestead import HomesteadState
from eth.vm.forks.tangerine_whistle import TangerineWhistleState
from eth.vm.forks.spurious_dragon import SpuriousDragonState
from eth.vm.forks.byzantium import ByzantiumState
from eth.vm.forks.petersburg import PetersburgState
from eth.vm.forks.istanbul import IstanbulState
from eth.vm.forks.muir_glacier import MuirGlacierState

from eth.vm.forks.frontier.computation import FrontierComputation
from eth.vm.forks.homestead.computation import HomesteadComputation
from eth.vm.forks.tangerine_whistle.computation import TangerineWhistleComputation
from eth.vm.forks.spurious_dragon.computation import SpuriousDragonComputation
from eth.vm.forks.byzantium.computation import ByzantiumComputation
from eth.vm.forks.petersburg.computation import PetersburgComputation
from eth.vm.forks.istanbul.computation import IstanbulComputation
from eth.vm.forks.muir_glacier.computation import MuirGlacierComputation

from eth.constants import ZERO_ADDRESS, CREATE_CONTRACT_ADDRESS
from eth.db.atomic import AtomicDB
from eth.rlp.accounts import Account
from eth.rlp.headers import BlockHeader
from eth.validation import validate_uint256
from eth.vm.spoof import SpoofTransaction
from eth_utils import to_canonical_address, decode_hex, encode_hex

global GLOBAL_STEP
GLOBAL_STEP = 0

global DEBUG
DEBUG = False

class EVM:
    def __init__(self, debug=False) -> None:
        global DEBUG

        DEBUG = debug
        chain = Chain.configure(
            __name__='EmulatorChain',
            vm_configuration=(
                (constants.GENESIS_BLOCK_NUMBER, MyFrontierVM),
                (HOMESTEAD_MAINNET_BLOCK, MyHomesteadVM),
                (TANGERINE_WHISTLE_MAINNET_BLOCK, MyTangerineWhistleVM),
                (SPURIOUS_DRAGON_MAINNET_BLOCK, MySpuriousDragonVM),
                (BYZANTIUM_MAINNET_BLOCK, MyByzantiumVM),
                (PETERSBURG_MAINNET_BLOCK, MyPetersburgVM),
                (ISTANBUL_MAINNET_BLOCK, MyIstanbulVM),
                (MUIR_GLACIER_MAINNET_BLOCK, MyMuirGlacierVM)
            ),
        )
        self._memory_db = EmulatorMemoryDB()
        self._chain = chain.from_genesis_header(AtomicDB(self._memory_db), MAINNET_GENESIS_HEADER)
        self._vm = None

    @property
    def storage(self):
        return self._vm.state._account_db

    def set_vm(self, host, port, block):
        block_header = BlockHeader(difficulty=block.difficulty,
                                   block_number=block.number,
                                   gas_limit=block.gasLimit,
                                   timestamp=block.timestamp,
                                   #coinbase=ZERO_ADDRESS,  # default value
                                   coinbase=decode_hex(block.miner),
                                   parent_hash=block.parentHash,
                                   uncles_hash=block.uncles,
                                   state_root=block.stateRoot,
                                   transaction_root=block.transactionsRoot,
                                   receipt_root=block.receiptsRoot,
                                   bloom=0,  # default value
                                   gas_used=block.gasUsed,
                                   extra_data=block.extraData,
                                   mix_hash=block.mixHash,
                                   nonce=block.nonce)
        self._vm = self._chain.get_vm(block_header)
        self.storage.set_http_provider(host, port)
        self.storage.set_fork_block_numer(block.number)

    def execute(self, tx):
        return self._vm.state.apply_transaction(tx)

    def reset(self):
        self.storage._raw_store_db.wrapped_db.reset()

    def has_account(self, address):
        address = to_canonical_address(address)
        return self._vm.state._account_db._has_account(address)

    def deploy_transaction(self, transaction):
        global GLOBAL_STEP

        GLOBAL_STEP = 0
        tx = self._vm.create_unsigned_transaction(
            nonce=self._vm.state.get_nonce(to_canonical_address(transaction["from"])),
            gas_price=transaction["gasPrice"],
            gas=transaction["gas"],
            to=to_canonical_address(transaction["to"]),
            value=transaction["value"],
            data=decode_hex(transaction["input"])
        )
        tx = SpoofTransaction(tx, from_=to_canonical_address(transaction["from"]))
        return self.execute(tx), GLOBAL_STEP

    def get_balance(self, address):
        return self.storage.get_balance(address)

    def get_adversary_balance(self):
        return self.storage.get_balance(self._adversary)

    def get_code(self, address):
        return self.storage.get_code(address)

    def set_code(self, address, code):
        return self.storage.set_code(address, code)

    def create_snapshot(self):
        self.snapshot = self.storage.record()

    def restore_from_snapshot(self):
        self.storage.discard(self.snapshot)

    def get_accounts(self):
        return [encode_hex(x) for x in
                self.storage._cache_store_db.wrapped_db["account"].keys()]

    def restore(self):
        self.storage.restore()

    def snapshot(self):
        self.storage.snapshot()

from eth.abc import (
    MessageAPI,
    ComputationAPI,
    StateAPI,
    TransactionContextAPI,
)

@classmethod
def my_apply_computation(cls, state: StateAPI, message: MessageAPI, transaction_context: TransactionContextAPI) -> ComputationAPI:
    global GLOBAL_STEP
    global DEBUG

    with cls(state, message, transaction_context) as computation:
        # Early exit on pre-compiles
        from eth.vm.computation import NO_RESULT
        precompile = computation.precompiles.get(message.code_address, NO_RESULT)
        if precompile is not NO_RESULT:
            precompile(computation)
            return computation

        opcode_lookup = computation.opcodes
        local_step = 0
        for opcode in computation.code:
            GLOBAL_STEP += 1
            local_step += 1
            try:
                opcode_fn = opcode_lookup[opcode]
            except KeyError:
                from eth.vm.logic.invalid import InvalidOpcode
                opcode_fn = InvalidOpcode(opcode)

            if DEBUG:
                print(str(GLOBAL_STEP)+"  \t "+str(local_step)+"  \t PC: "+str(max(0, computation.code.program_counter - 1))+"  \t OPCODE: "+hex(opcode)+" ("+opcode_fn.mnemonic+") "+str(list(computation._stack.values)))

            from eth.exceptions import Halt
            try:
                opcode_fn(computation=computation)
            except Halt:
                break
    return computation

# VMs
# FRONTIER
MyFrontierComputation = FrontierComputation.configure(
    __name__='MyFrontierComputation',
    apply_computation=my_apply_computation,
)
MyFrontierState = FrontierState.configure(
    __name__='MyFrontierState',
    computation_class=MyFrontierComputation,
    account_db_class=EmulatorAccountDB,
)
MyFrontierVM = FrontierVM.configure(
    __name__='MyFrontierVM',
    _state_class=MyFrontierState,
)

# HOMESTEAD
MyHomesteadComputation = HomesteadComputation.configure(
    __name__='MyHomesteadComputation',
    apply_computation=my_apply_computation,
)
MyHomesteadState = HomesteadState.configure(
    __name__='MyHomesteadState',
    computation_class=MyHomesteadComputation,
    account_db_class=EmulatorAccountDB,
)
MyHomesteadVM = MainnetHomesteadVM.configure(
    __name__='MyHomesteadVM',
    _state_class=MyHomesteadState,
)

# TANGERINE WHISTLE
MyTangerineWhistleComputation = TangerineWhistleComputation.configure(
    __name__='MyTangerineWhistleComputation',
    apply_computation=my_apply_computation,
)
MyTangerineWhistleState = TangerineWhistleState.configure(
    __name__='MyTangerineWhistleState',
    computation_class=MyTangerineWhistleComputation,
    account_db_class=EmulatorAccountDB,
)
MyTangerineWhistleVM = TangerineWhistleVM.configure(
    __name__='MyTangerineWhistleVM',
    _state_class=MyTangerineWhistleState,
)

# SPURIOUS DRAGON
MySpuriousDragonComputation = SpuriousDragonComputation.configure(
    __name__='MySpuriousDragonComputation',
    apply_computation=my_apply_computation,
)
MySpuriousDragonState = SpuriousDragonState.configure(
    __name__='MySpuriousDragonState',
    computation_class=MySpuriousDragonComputation,
    account_db_class=EmulatorAccountDB,
)
MySpuriousDragonVM = SpuriousDragonVM.configure(
    __name__='MySpuriousDragonVM',
    _state_class=MySpuriousDragonState,
)

# BYZANTIUM
MyByzantiumComputation = ByzantiumComputation.configure(
    __name__='MyByzantiumComputation',
    apply_computation=my_apply_computation,
)
MyByzantiumState = ByzantiumState.configure(
    __name__='MyByzantiumState',
    computation_class=MyByzantiumComputation,
    account_db_class=EmulatorAccountDB,
)
MyByzantiumVM = ByzantiumVM.configure(
    __name__='MyByzantiumVM',
    _state_class=MyByzantiumState,
)

# PETERSBURG
MyPetersburgComputation = PetersburgComputation.configure(
    __name__='MyPetersburgComputation',
    apply_computation=my_apply_computation,
)
MyPetersburgState = PetersburgState.configure(
    __name__='MyPetersburgState',
    computation_class=MyPetersburgComputation,
    account_db_class=EmulatorAccountDB,
)
MyPetersburgVM = PetersburgVM.configure(
    __name__='MyPetersburgVM',
    _state_class=MyPetersburgState,
)

# ISTANBUL
MyIstanbulComputation = IstanbulComputation.configure(
    __name__='MyIstanbulComputation',
    apply_computation=my_apply_computation,
)
MyIstanbulState = IstanbulState.configure(
    __name__='MyIstanbulState',
    computation_class=MyIstanbulComputation,
    account_db_class=EmulatorAccountDB,
)
MyIstanbulVM = IstanbulVM.configure(
    __name__='MyIstanbulVM',
    _state_class=MyIstanbulState
)

# MUIR_GLACIER
MyMuirGlacierComputation = MuirGlacierComputation.configure(
    __name__='MyMuirGlacierComputation',
    apply_computation=my_apply_computation,
)
MyMuirGlacierState = MuirGlacierState.configure(
    __name__='MyMuirGlacierState',
    computation_class=MyMuirGlacierComputation,
    account_db_class=EmulatorAccountDB,
)
MyMuirGlacierVM = MuirGlacierVM.configure(
    __name__='MyMuirGlacierVM',
    _state_class=MyMuirGlacierState
)
