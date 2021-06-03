#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import numpy
import pymongo
import requests
import multiprocessing

from web3 import Web3
from http import client

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from utils.settings import *
from utils.utils import colors, request_debug_trace

def intersection(list_1, list_2):
    return [value for value in list_1 if value in set(list_2)]

def analyze_block(args):
    memoized_blocks, block_number = args[0], args[1]
    print("Analyzing block number: "+str(block_number))

    status = mongo_connection["front_running"]["suppression_status"].find_one({"block_number": block_number})
    if status:
        print("Block "+str(block_number)+" already analyzed!")
        return status["execution_time"]

    start = time.time()
    result_1 = _analyze_block(memoized_blocks, block_number)
    if result_1:
        result_2 = _analyze_block(memoized_blocks, block_number - 1)
        result_3 = _analyze_block(memoized_blocks, block_number + 1)

        intersection_1 = intersection(result_1.keys(), result_2.keys())
        intersection_2 = intersection(result_1.keys(), result_3.keys())

        if intersection_1 or intersection_2:
            genuine = False
            suppression_type = ""
            result_1_txs = []
            if   intersection_1:
                result_1_txs = result_1[intersection_1[0]]
            elif intersection_2:
                result_1_txs = result_1[intersection_2[0]]
            connection = client.HTTPConnection(WEB3_HTTP_RPC_HOST, WEB3_HTTP_RPC_PORT)

            # Check if we call exactly one external contract
            external_contracts_called = set()
            response = request_debug_trace(connection, result_1_txs[0]["hash"].hex())
            if not response:
                print(colors.FAIL+"Error: Could not retrieve execution trace for transaction "+str(result_1_txs[0]["hash"].hex())+" (block: "+str(block_number)+")"+colors.END)
                return time.time()-start
            if not "result" in response and "error" in response:
                print(colors.FAIL+"Error while retrieving execution trace for transaction "+str(result_1_txs[0]["hash"].hex())+" (block: "+str(block_number)+"): "+response["error"]["message"]+colors.END)
                return time.time()-start
            for call in response["result"]:
                external_contracts_called.add(call["to"])
            if len(external_contracts_called) == 1:
                # Detect if transaction was reverted and remember how often instructions (except stack instruction: PUSH, POP, DUP and SWAP) were executed
                response = request_debug_trace(connection, result_1_txs[0]["hash"].hex(), custom_tracer=False)
                if not response:
                    print(colors.FAIL+"Error: Could not retrieve execution trace for transaction "+str(result_1_txs[0]["hash"].hex())+" (block: "+str(block_number)+")"+colors.END)
                    return time.time()-start
                if not "result" in response and "error" in response:
                    print(colors.FAIL+"Error while retrieving execution trace for transaction "+str(result_1_txs[0]["hash"].hex())+" (block: "+str(block_number)+"): "+response["error"]["message"]+colors.END)
                    return time.time()-start
                reverted = False
                occurrences = {}
                last_executed_instruction = None
                for executed_instruction in response["result"]["structLogs"]:
                    last_executed_instruction = executed_instruction
                    if "error" in executed_instruction:
                        break
                    if executed_instruction["op"] == "REVERT":
                        reverted = True
                        break
                    if (executed_instruction["op"].startswith("PUSH") or
                        executed_instruction["op"].startswith("POP") or
                        executed_instruction["op"].startswith("DUP") or
                        executed_instruction["op"].startswith("SWAP")):
                        continue
                    if executed_instruction["pc"] not in occurrences:
                        occurrences[executed_instruction["pc"]] = {"count": 0, "op": executed_instruction["op"]}
                    occurrences[executed_instruction["pc"]]["count"] += 1
                # Check if the execution failed due to an assert or out of gas
                receipt = w3.eth.getTransactionReceipt(result_1_txs[0]["hash"])
                if "status" in receipt:
                    if receipt["status"] == 0:
                        if not reverted and last_executed_instruction:
                            # ASSERT
                            if last_executed_instruction["op"] == "opcode 0xfe not defined":
                                basic_block_opcode_sequences = []
                                opcode_sequence = ""
                                for pc in occurrences:
                                    if occurrences[pc]["op"] == "JUMPDEST" and opcode_sequence:
                                        basic_block_opcode_sequences.append(opcode_sequence)
                                        opcode_sequence = ""
                                    elif occurrences[pc]["op"] == "JUMP" or occurrences[pc]["op"] == "JUMPI" or occurrences[pc]["op"] == "STOP" or occurrences[pc]["op"] == "RETURN" or occurrences[pc]["op"] == "REVERT":
                                        if (occurrences[pc]["op"] == "MSTORE" or
                                            occurrences[pc]["op"] == "RETURN" or
                                            occurrences[pc]["op"] == "MLOAD" or
                                            occurrences[pc]["op"] == "JUMPI" or
                                            occurrences[pc]["op"] == "EQ"):
                                            opcode_sequence += occurrences[pc]["op"]
                                        basic_block_opcode_sequences.append(opcode_sequence)
                                        opcode_sequence = ""
                                        continue
                                    if (occurrences[pc]["op"] == "MSTORE" or
                                        occurrences[pc]["op"] == "RETURN" or
                                        occurrences[pc]["op"] == "MLOAD" or
                                        occurrences[pc]["op"] == "JUMPI" or
                                        occurrences[pc]["op"] == "EQ"):
                                        opcode_sequence += occurrences[pc]["op"]
                                write_14_times_to_memory_and_return = False
                                for opcode_sequence in basic_block_opcode_sequences:
                                    if "MSTOREMSTOREMSTOREMSTOREMSTOREMSTOREMSTOREMSTOREMSTOREMSTOREMSTOREMSTOREMSTOREMLOADRETURN" in opcode_sequence:
                                        write_14_times_to_memory_and_return = True
                                    elif write_14_times_to_memory_and_return and "MLOADEQJUMPI" in opcode_sequence:
                                        suppression_type = "assert"
                                        genuine = True
                                        break
                            # OUT OF GAS
                            elif last_executed_instruction["gas"] - last_executed_instruction["gasCost"] < 0:
                                basic_block_opcode_sequences = []
                                opcode_sequence = ""
                                for pc in occurrences:
                                    if occurrences[pc]["count"] > 10:
                                        if occurrences[pc]["op"] == "JUMPDEST" and opcode_sequence:
                                            basic_block_opcode_sequences.append(opcode_sequence)
                                            opcode_sequence = ""
                                        elif occurrences[pc]["op"] == "JUMP" or occurrences[pc]["op"] == "JUMPI" or occurrences[pc]["op"] == "STOP" or occurrences[pc]["op"] == "RETURN" or occurrences[pc]["op"] == "REVERT":
                                            opcode_sequence += occurrences[pc]["op"]
                                            basic_block_opcode_sequences.append(opcode_sequence)
                                            opcode_sequence = ""
                                            continue
                                        opcode_sequence += occurrences[pc]["op"]
                                for opcode_sequence in basic_block_opcode_sequences:
                                    if "SLOADTIMESTAMPADDSSTORE" in opcode_sequence:
                                        suppression_type = "out_of_gas_loop"
                                        genuine = True
                                        break
                    # Check if the executed code contains a loop that checks how much gas is left
                    else:
                        opcode_sequence = ""
                        for pc in occurrences:
                            if occurrences[pc]["count"] > 10:
                                opcode_sequence += occurrences[pc]["op"]
                        if "GASGTISZEROJUMPI" in opcode_sequence:
                            suppression_type = "controlled_gas_loop"
                            genuine = True
                else:
                    print(colors.FAIL+"Error: Receipt does not contain status for transaction "+str(result_1_txs[0]["hash"].hex())+" (block: "+str(block_number)+")"+colors.END)

                if genuine:
                    block = w3.eth.getBlock(block_number, False)
                    suppressed_contract_address = Web3.toChecksumAddress(list(external_contracts_called)[0])

                    suppressed_contract_name = None
                    if not suppressed_contract_name:
                        try:
                            response = requests.get("https://api.etherscan.io/api?module=contract&action=getsourcecode&address="+suppressed_contract_address+"&apikey="+ETHERSCAN_API_KEY).json()
                            if response["status"] == '1' and response["message"] == "OK" and "result" in response:
                                suppressed_contract_name = response["result"][0]["ContractName"]
                        except:
                            pass
                    if not suppressed_contract_name:
                        try:
                            suppressed_contract = w3.eth.contract(address=suppressed_contract_address, abi=[{"constant":True,"inputs":[],"name":"name","outputs":[{"internalType":"string","name":"","type":"string"}],"payable":False,"stateMutability":"view","type":"function"}])
                            suppressed_contract_name = suppressed_contract.functions.name().call()
                        except:
                            pass
                    if not suppressed_contract_name:
                        suppressed_contract_name = suppressed_contract_address

                    transactions = []
                    for tx in result_1_txs:
                        tx = dict(tx)
                        del tx["blockNumber"]
                        del tx["blockHash"]
                        del tx["r"]
                        del tx["s"]
                        del tx["v"]
                        tx["hash"] = tx["hash"].hex()

                        receipt = w3.eth.getTransactionReceipt(tx["hash"])
                        receipt = dict(receipt)
                        del receipt["blockNumber"]
                        del receipt["blockHash"]
                        del receipt["contractAddress"]
                        del receipt["logs"]
                        del receipt["logsBloom"]
                        del receipt["transactionHash"]
                        tx.update(receipt)

                        transactions.append(tx)
                        print(str(tx["transactionIndex"])+"\t"+str(block_number)+" "+tx["hash"]+" "+tx["from"]+" "+tx["to"]+" "+suppressed_contract_address+" ("+suppressed_contract_name+")")

                    finding = {
                        "block_number": block_number,
                        "block_timestamp": block["timestamp"],
                        "transactions": transactions,
                        "suppressed_contract_address": suppressed_contract_address,
                        "suppressed_contract_name": suppressed_contract_name,
                        "suppression_type": suppression_type,
                        "bot_address": result_1_txs[0]["to"]
                    }
                    collection = mongo_connection["front_running"]["suppression_results"]
                    collection.insert_one(finding)

                    # Indexing...
                    if 'block_number' not in collection.index_information():
                        collection.create_index('block_number')
                        collection.create_index('block_timestamp')
                        collection.create_index('suppressed_contract_address')
                        collection.create_index('suppressed_contract_name')
                        collection.create_index('suppression_type')
                        collection.create_index('bot_address')
            connection.close()
    end = time.time()
    collection = mongo_connection["front_running"]["suppression_status"]
    collection.insert_one({"block_number": block_number, "execution_time": end-start})
    # Indexing...
    if 'block_number' not in collection.index_information():
        collection.create_index('block_number')

    return end-start

def _analyze_block(memoized_blocks, block_number):
    if block_number in memoized_blocks:
        return memoized_blocks[block_number]

    block = w3.eth.getBlock(block_number, True)
    clusters = {}
    for tx in block["transactions"]:
        if tx["value"] == 0 and tx["to"] != None:
            if tx["to"] not in clusters:
                clusters[tx["to"]] = []
            clusters[tx["to"]].append(tx)

    results = {}
    for cluster in list(clusters):
        if len(clusters[cluster]) == 1:
            del clusters[cluster]
        else:
            for tx in clusters[cluster]:
                receipt = w3.eth.getTransactionReceipt(tx["hash"])
                if receipt["gasUsed"] > 21000 and receipt["gasUsed"] / tx["gas"] > 0.99:
                    if tx["to"] not in results:
                        results[tx["to"]] = []
                    results[tx["to"]].append(tx)
                else:
                    break

    for result in list(results):
        if len(results[result]) == 1:
            del results[result]

    memoized_blocks[block_number] = results
    # Free memory by deleting results that are older than 1000 blocks
    if block_number-1000 in memoized_blocks:
        del memoized_blocks[block_number-1000]

    return results

def init_process():
    global w3
    global mongo_connection

    w3 = Web3(Web3.WebsocketProvider(WEB3_WS_PROVIDER))
    if w3.isConnected():
        print("Connected worker to "+w3.clientVersion)
    else:
        print(colors.FAIL+"Error: Could not connect to "+WEB3_WS_PROVIDER+colors.END)
    mongo_connection = pymongo.MongoClient("mongodb://"+MONGO_HOST+":"+str(MONGO_PORT), maxPoolSize=None)

def main():
    if len(sys.argv) != 2:
        print(colors.FAIL+"Error: Please provide a block range to be analyzed: 'python3 "+sys.argv[0]+" <BLOCK_RANGE_START>:<BLOCK_RANGE_END>'"+colors.END)
        sys.exit(-1)
    if not ":" in sys.argv[1]:
        print(colors.FAIL+"Error: Please provide a valid block range: 'python3 "+sys.argv[0]+" <BLOCK_RANGE_START>:<BLOCK_RANGE_END>'"+colors.END)
        sys.exit(-2)
    block_range_start, block_range_end = sys.argv[1].split(":")[0], sys.argv[1].split(":")[1]
    if not block_range_start.isnumeric() or not block_range_end.isnumeric():
        print(colors.FAIL+"Error: Please provide integers as block range: 'python3 "+sys.argv[0]+" <BLOCK_RANGE_START>:<BLOCK_RANGE_END>'"+colors.END)
        sys.exit(-3)
    block_range_start, block_range_end = int(block_range_start), int(block_range_end)

    execution_times = []
    multiprocessing.set_start_method('fork')
    print("Running detection of insertion frontrunning attacks with "+str(multiprocessing.cpu_count())+" CPUs")
    print("Initializing workers...")
    with multiprocessing.Pool(processes=multiprocessing.cpu_count(), initializer=init_process) as pool:
        start_total = time.time()
        manager = multiprocessing.Manager()
        memoized_blocks = manager.dict()
        execution_times += pool.map(analyze_block, [(memoized_blocks, block_number) for block_number in range(block_range_start, block_range_end+1)])
        end_total = time.time()
        print("Total execution time: "+str(end_total - start_total))
        print()
        if execution_times:
            print("Max execution time: "+str(numpy.max(execution_times)))
            print("Mean execution time: "+str(numpy.mean(execution_times)))
            print("Median execution time: "+str(numpy.median(execution_times)))
            print("Min execution time: "+str(numpy.min(execution_times)))

if __name__ == "__main__":
    main()
