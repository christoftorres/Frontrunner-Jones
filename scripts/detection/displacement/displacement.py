#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import math
import time
import mmh3
import numpy
import pymongo
import decimal
import hashlib
import multiprocessing

from web3 import Web3
from http import client
from bitarray import bitarray
from itertools import groupby
from operator import itemgetter
from difflib import SequenceMatcher

from emulator import Emulator

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from utils.settings import *
from utils.utils import colors, get_prices, get_one_eth_to_usd, request_debug_trace

WINDOW_SIZE = 100
WINDOW_OFFSET = 20

class BloomFilter(object):
    '''
    Class for Bloom filter, using murmur3 hash function
    '''
    def __init__(self, items_count, fp_prob):
        '''
        items_count : int
            Number of items expected to be stored in bloom filter
        fp_prob : float
            False Positive probability in decimal
        '''
        # False posible probability in decimal
        self.fp_prob = fp_prob
        # Size of bit array to use
        self.size = self.get_size(items_count, fp_prob)
        # number of hash functions to use
        self.hash_count = self.get_hash_count(self.size, items_count)
        # Bit array of given size
        self.bit_array = bitarray(self.size)
        # initialize all bits as 0
        self.bit_array.setall(0)

    def add(self, item):
        '''
        Add an item in the filter
        '''
        for i in range(self.hash_count):
            # create digest for given item.
            # i work as seed to mmh3.hash() function
            # With different seed, digest created is different
            digest = mmh3.hash(item, i) % self.size
            # set the bit True in bit_array
            self.bit_array[digest] = True

    def check(self, item):
        '''
        Check for existence of an item in filter
        '''
        for i in range(self.hash_count):
            digest = mmh3.hash(item, i) % self.size
            if self.bit_array[digest] == False:
                return False
        return True

    @classmethod
    def get_size(self, n, p):
        '''
        Return the size of bit array(m) to used using
        following formula
        m = -(n * lg(p)) / (lg(2)^2)
        n : int
            number of items expected to be stored in filter
        p : float
            False Positive probability in decimal
        '''
        m = -(n * math.log(p))/(math.log(2)**2)
        return int(m)

    @classmethod
    def get_hash_count(self, m, n):
        '''
        Return the hash function(k) to be used using
        following formula
        k = (m/n) * lg(2)

        m : int
            size of bit array
        n : int
            number of items expected to be stored in filter
        '''
        k = (m/n) * math.log(2)
        return int(k)

def longest_true_run(lst):
    """Finds the longest true run in a list of boolean"""
    # find False runs only
    groups = [[i for i, _ in group] for key, group in groupby(enumerate(lst), key=itemgetter(1)) if key]
    # get the one of maximum length
    group = max(groups, key=len, default=[0, 0])
    start, end = group[0], group[-1]
    return end - start

def analyze_block_range(block_range):
    bloom_filter = BloomFilter(1000000, 0.01)
    memoized_inputs = dict()
    execution_times = []

    for block_number in block_range:
        start = time.time()
        print("Analyzing block number: "+str(block_number))

        status = mongo_connection["front_running"]["displacement_status"].find_one({"block_number": block_number})
        if status:
            print("Block "+str(block_number)+" already analyzed!")
            execution_times.append(status["execution_time"])
            continue

        block = w3.eth.getBlock(block_number, True)
        for i in range(len(block["transactions"])):
            tx = block["transactions"][i]
            input = tx["input"].replace("0x", "")
            if input and tx["to"] and int(input, 16) != 0 and (block_number not in memoized_inputs or input not in memoized_inputs[block_number]):
                pieces = [input[k:k+8] for k in range(len(input))]
                p = longest_true_run([bloom_filter.check(piece) for piece in pieces]) / len(pieces)
                # Do probabilistic search using bloom filter
                if p >= 0.99:
                    try:
                        # Search up to WINDOW_OFFSET blocks in the past
                        for j in range(block_number - WINDOW_OFFSET + 1, block_number + 1):
                            if j in memoized_inputs:
                                for memoized_input in memoized_inputs[j]:
                                    if input != memoized_input and input in memoized_input:
                                        victim, front_runner = tx, memoized_inputs[j][memoized_input]
                                        if front_runner["from"] != victim["from"] and front_runner["to"] != victim["to"] and victim["gasPrice"] < front_runner["gasPrice"]:
                                            # Compute porportion
                                            memoized_input_4_bytes = len([memoized_input[k:k+8] for k in range(0, len(memoized_input), 8)])
                                            input_4_bytes = len([input[k:k+8] for k in range(0, len(input), 8)])
                                            proportion = input_4_bytes / memoized_input_4_bytes
                                            if proportion > 0.25:
                                                emu = Emulator(WEB3_HTTP_RPC_HOST, WEB3_HTTP_RPC_PORT, w3.eth.getBlock(front_runner["blockNumber"]-1, False))

                                                emu.take_snapshot()
                                                result_1, executed_steps_1 = emu.send_transaction(front_runner)
                                                result_2, executed_steps_2 = emu.send_transaction(victim)

                                                emu.restore_from_snapshot()
                                                result3, executed_steps_3 = emu.send_transaction(victim)
                                                result_4, executed_steps_4 = emu.send_transaction(front_runner)

                                                if executed_steps_1 != executed_steps_4 and executed_steps_2 != executed_steps_3:
                                                    hash_input = front_runner["hash"].hex()+victim["hash"].hex()
                                                    sha256_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
                                                    result = mongo_connection["front_running"]["displacement_results"].find_one({"sha256_hash": sha256_hash})
                                                    if result:
                                                        continue

                                                    print(colors.INFO+"Attacker: \t "+str(front_runner["blockNumber"])+" \t "+str(front_runner["transactionIndex"])+" \t "+front_runner["hash"].hex()+" \t "+front_runner["from"]+" \t "+front_runner["to"]+" \t "+str(front_runner["gasPrice"])+colors.END)
                                                    print(" Input: \t "+str(memoized_input))
                                                    print(colors.INFO+"Victim: \t "+str(victim["blockNumber"])+" \t "+str(victim["transactionIndex"])+" \t "+victim["hash"].hex()+" \t "+victim["from"]+" \t "+victim["to"]+" \t "+str(victim["gasPrice"])+colors.END)
                                                    print(" Input: \t "+str(input))
                                                    match = SequenceMatcher(None, memoized_input, input).find_longest_match(0, len(memoized_input), 0, len(input))
                                                    print(colors.INFO+"Longest Common Input: \t "+str(input[match.b:match.b+match.size])+colors.END)

                                                    one_eth_to_usd_price = decimal.Decimal(float(get_one_eth_to_usd(w3.eth.getBlock(front_runner["blockNumber"])["timestamp"], prices)))

                                                    receipt = w3.eth.getTransactionReceipt(front_runner["hash"])
                                                    total_cost = receipt["gasUsed"]*front_runner["gasPrice"]

                                                    gain = 0
                                                    connection = client.HTTPConnection(WEB3_HTTP_RPC_HOST, WEB3_HTTP_RPC_PORT)
                                                    response = request_debug_trace(connection, front_runner["hash"].hex())
                                                    if response and "result" in response:
                                                        for call in response["result"]:
                                                            if call["value"] > gain:
                                                                gain = call["value"]
                                                    connection.close()

                                                    profit = gain - total_cost
                                                    if profit >= 0:
                                                        profit_usd = Web3.fromWei(profit, 'ether') * one_eth_to_usd_price
                                                        print(colors.OK+"Profit: "+str(Web3.fromWei(profit, 'ether'))+" ETH ("+str(profit_usd)+" USD)"+colors.END)
                                                    else:
                                                        profit_usd = -Web3.fromWei(abs(profit), 'ether') * one_eth_to_usd_price
                                                        print(colors.FAIL+"Profit: -"+str(Web3.fromWei(abs(profit), 'ether'))+" ETH ("+str(profit_usd)+" USD)"+colors.END)

                                                    front_runner = dict(front_runner)
                                                    del front_runner["blockHash"]
                                                    del front_runner["r"]
                                                    del front_runner["s"]
                                                    del front_runner["v"]
                                                    front_runner["value"] = str(front_runner["value"])
                                                    front_runner["hash"] = front_runner["hash"].hex()

                                                    victim = dict(victim)
                                                    del victim["blockHash"]
                                                    del victim["r"]
                                                    del victim["s"]
                                                    del victim["v"]
                                                    victim["value"] = str(victim["value"])
                                                    victim["hash"] = victim["hash"].hex()

                                                    finding = {
                                                        "sha256_hash": sha256_hash,
                                                        "attacker_transaction": front_runner,
                                                        "victim_transaction": victim,
                                                        "longest_common_input:": input[match.b:match.b+match.size],
                                                        "eth_usd_price": float(one_eth_to_usd_price),
                                                        "cost_eth": float(Web3.fromWei(total_cost, 'ether')),
                                                        "cost_usd": float(Web3.fromWei(total_cost, 'ether') * one_eth_to_usd_price),
                                                        "gain_eth": float(Web3.fromWei(gain, 'ether')),
                                                        "gain_usd": float(Web3.fromWei(gain, 'ether') * one_eth_to_usd_price),
                                                        "profit_eth": float(Web3.fromWei(profit, 'ether')),
                                                        "profit_usd": float(profit_usd)
                                                    }
                                                    collection = mongo_connection["front_running"]["displacement_results"]
                                                    collection.insert_one(finding)
                                                    # Indexing...
                                                    if 'sha256_hash' not in collection.index_information():
                                                        collection.create_index('sha256_hash')
                                                        collection.create_index('attacker_transaction.blockNumber')
                                                        collection.create_index('attacker_transaction.from')
                                                        collection.create_index('attacker_transaction.gas')
                                                        collection.create_index('attacker_transaction.gasPrice')
                                                        collection.create_index('attacker_transaction.hash')
                                                        collection.create_index('attacker_transaction.nonce')
                                                        collection.create_index('attacker_transaction.to')
                                                        collection.create_index('attacker_transaction.transactionIndex')
                                                        collection.create_index('attacker_transaction.value')
                                                        collection.create_index('victim_transaction.blockNumber')
                                                        collection.create_index('victim_transaction.from')
                                                        collection.create_index('victim_transaction.gas')
                                                        collection.create_index('victim_transaction.gasPrice')
                                                        collection.create_index('victim_transaction.hash')
                                                        collection.create_index('victim_transaction.nonce')
                                                        collection.create_index('victim_transaction.to')
                                                        collection.create_index('victim_transaction.transactionIndex')
                                                        collection.create_index('victim_transaction.value')
                                                        collection.create_index('eth_usd_price')
                                                        collection.create_index('cost_eth')
                                                        collection.create_index('cost_usd')
                                                        collection.create_index('gain_eth')
                                                        collection.create_index('gain_usd')
                                                        collection.create_index('profit_eth')
                                                        collection.create_index('profit_usd')
                    except Exception as e:
                        print("Error: "+str(e))

                if not block_number in memoized_inputs:
                    memoized_inputs[block_number] = dict()
                if not input in memoized_inputs[block_number]:
                    for piece in pieces:
                        bloom_filter.add(piece)
                    memoized_inputs[block_number][input] = tx

        end = time.time()
        execution_times.append(end-start)
        status = mongo_connection["front_running"]["displacement_status"].find_one({"block_number": block_number})
        if not status:
            collection = mongo_connection["front_running"]["displacement_status"]
            collection.insert_one({"block_number": block_number, "execution_time": end-start})
            # Indexing...
            if 'block_number' not in collection.index_information():
                collection.create_index('block_number')

    #print("Execution time: "+str(np.mean(execution_times)))
    #print("Bloom filter size: "+str(bloom_filter.size))
    #print("Number of bloom filter hash functions: "+str(bloom_filter.hash_count))
    #print("Bits set to true in bloom filter: "+str(bloom_filter.bit_array.count(True))+" ("+str(bloom_filter.bit_array.count(True)/bloom_filter.size*100)+"%)")
    #print()

    return execution_times

def init_process(_prices):
    global w3
    global prices
    global mongo_connection

    w3 = Web3(Web3.WebsocketProvider(WEB3_WS_PROVIDER))
    if w3.isConnected():
        print("Connected worker to "+w3.clientVersion)
    else:
        print(colors.FAIL+"Error: Could not connect to "+WEB3_WS_PROVIDER+colors.END)
    prices = _prices
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
    prices = get_prices()
    multiprocessing.set_start_method('fork')
    print("Running detection of insertion frontrunning attacks with "+str(multiprocessing.cpu_count())+" CPUs")
    print("Initializing workers...")
    with multiprocessing.Pool(processes=multiprocessing.cpu_count(), initializer=init_process, initargs=(prices,)) as pool:
        start_total = time.time()
        blocks = range(block_range_start, block_range_end+1)
        if block_range_end - block_range_start < WINDOW_SIZE:
            block_ranges = [[block for block in blocks]]
        else:
            block_ranges = [blocks[i * WINDOW_OFFSET:i * WINDOW_OFFSET + WINDOW_SIZE] for i in range((len(blocks) + WINDOW_OFFSET - WINDOW_SIZE) // WINDOW_OFFSET)]
        execution_times += pool.map(analyze_block_range, block_ranges)
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
