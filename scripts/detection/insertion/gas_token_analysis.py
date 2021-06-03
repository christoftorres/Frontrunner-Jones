#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import pymongo
import multiprocessing

from http import client

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from utils.settings import *
from utils.utils import request_debug_trace

def analyze_trace(trace):
    gas_token_address = None
    gas_token_name = ""
    token_amount = 0
    for i in range(len(trace["result"])):
        if i < len(trace["result"]) - 1:
            call1 = trace["result"][i]
            call2 = trace["result"][i+1]
            if call1["call_type"] in ["SUICIDE", "SELFDESTRUCT"] and call2["from"] == call1["to"] and call2["to"] == call1["from"] and call2["input"] == "0x":
                gas_token_address = call1["to"]
                if   gas_token_address.lower() == "0x0000000000b3f879cb30fe243b4dfee438691c04":
                    gas_token_name = "Gastoken.io (GST2)"
                elif gas_token_address.lower() == "0x0000000000004946c0e9f43f4dee607b0ef1fa1c":
                    gas_token_name = "Chi Gastoken by 1inch (CHI)"
                else:
                    gas_token_name = "Custom Token"
                token_amount += 1
    return gas_token_address, gas_token_name, token_amount

def analyze_transactions(transactions):
    connection = client.HTTPConnection(WEB3_HTTP_RPC_HOST, WEB3_HTTP_RPC_PORT)

    findings = dict()

    trace = request_debug_trace(connection, transactions[0])
    gas_token_address, gas_token_name, token_amount = analyze_trace(trace)

    if gas_token_address:
        print(transactions[0]+" \t "+gas_token_address+" \t "+gas_token_name+" \t "+str(token_amount))

    findings["first_transaction"] = dict()
    findings["first_transaction"]["hash"] = transactions[0]
    findings["first_transaction"]["gas_token_address"] = gas_token_address
    findings["first_transaction"]["gas_token_name"] = gas_token_name
    findings["first_transaction"]["token_amount"] = token_amount

    trace = request_debug_trace(connection, transactions[1])
    gas_token_address, gas_token_name, token_amount = analyze_trace(trace)

    if gas_token_address:
        print(transactions[1]+" \t "+gas_token_address+" \t "+gas_token_name+" \t "+str(token_amount))

    findings["second_transaction"] = dict()
    findings["second_transaction"]["hash"] = transactions[1]
    findings["second_transaction"]["gas_token_address"] = gas_token_address
    findings["second_transaction"]["gas_token_name"] = gas_token_name
    findings["second_transaction"]["token_amount"] = token_amount

    collection = mongo_connection["front_running"]["insertion_gas_tokens"]
    collection.insert_one(findings)

    # Indexing...
    if 'first_transaction.hash' not in collection.index_information():
        collection.create_index('first_transaction.hash')
        collection.create_index('first_transaction.gas_token_address')
        collection.create_index('first_transaction.gas_token_name')
        collection.create_index('first_transaction.token_amount')

        collection.create_index('second_transaction.hash')
        collection.create_index('second_transaction.gas_token_address')
        collection.create_index('second_transaction.gas_token_name')
        collection.create_index('second_transaction.token_amount')

    connection.close()

def init_process():
    global mongo_connection
    mongo_connection = pymongo.MongoClient("mongodb://"+MONGO_HOST+":"+str(MONGO_PORT), maxPoolSize=None)

def main():
    print("Getting results...")
    cursor = pymongo.MongoClient("mongodb://"+MONGO_HOST+":"+str(MONGO_PORT)["front_running"]["insertion_results"].find({})
    transactions = []
    for document in cursor:
        transactions.append((document["first_transaction"]["hash"], document["second_transaction"]["hash"]))
    print("Found "+str(len(transactions))+" transactions to analyze...")

    multiprocessing.set_start_method('fork')
    print("Running detection of gas token usage with "+str(multiprocessing.cpu_count())+" CPUs")
    print("Initializing workers...")
    with multiprocessing.Pool(processes=multiprocessing.cpu_count(), initializer=init_child) as pool:
        pool.map(analyze_transactions, transactions)

if __name__ == "__main__":
    main()
