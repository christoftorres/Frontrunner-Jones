#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import json
import requests

class colors:
    INFO = '\033[94m'
    OK = '\033[92m'
    FAIL = '\033[91m'
    END = '\033[0m'

def get_prices():
    return requests.get("https://api.coingecko.com/api/v3/coins/ethereum/market_chart/range?vs_currency=usd&from=1392577232&to="+str(int(time.time()))).json()["prices"]

def get_one_eth_to_usd(timestamp, prices):
    timestamp *= 1000
    one_eth_to_usd = prices[-1][1]
    for index, _ in enumerate(prices):
        if index < len(prices)-1:
            if prices[index][0] <= timestamp and timestamp <= prices[index+1][0]:
                return prices[index][1]
    print("Could not find timestamp. Returning latest price instead.")
    return one_eth_to_usd

def request_debug_trace(connection, transaction_hash, custom_tracer=True, request_timeout=100, disable_stack=True, disable_memory=True, disable_storage=True):
    data, tracer = None, None
    if custom_tracer:
        with open(os.path.join(os.path.dirname(__file__), 'call_tracer.js'), 'r') as file:
            tracer = file.read().replace('\n', '')
    if tracer:
        data = json.dumps({"id": 1, "method": "debug_traceTransaction", "params": [transaction_hash, {"tracer": tracer, "timeout": str(request_timeout)+"s"}]})
    else:
        data = json.dumps({"id": 1, "method": "debug_traceTransaction", "params": [transaction_hash, {"disableStack": disable_stack, "disableMemory": disable_memory, "disableStorage": disable_storage}]})
    headers = {"Content-Type": "application/json"}
    connection.request('GET', '/', data, headers)
    response = connection.getresponse()
    if response.status == 200 and response.reason == "OK":
        return json.loads(response.read())
    return {"error": {"status": response.status, "reason": response.reason, "data": response.read().decode()}}
