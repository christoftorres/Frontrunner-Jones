#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import numpy
import decimal
import pymongo
import requests
import multiprocessing

from web3 import Web3

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from utils.settings import *
from utils.utils import colors, get_prices, get_one_eth_to_usd

TOKEN_AMOUNT_DELTA = 0.01 # Maximum different between buying and selling amount of tokens. Default value is 1%.

TRANSFER       = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef" # ERC20 "Transfer"
TOKEN_PURCHASE = "0xcd60aa75dea3072fbc07ae6d7d856b5dc5f4eee88854f5b4abf7b680ef8bc50f" # Uniswap V1 "TokenPurchase"
ETH_PURCHASE   = "0x7f4091b46c33e918a0f3aa42307641d17bb67029427a5369e54b353984238705" # Uniswap V1 "ETHPurchase"

def analyze_block(block_number):
    start = time.time()
    print("Analyzing block number: "+str(block_number))

    status = mongo_connection["front_running"]["insertion_status"].find_one({"block_number": block_number})
    if status:
        print("Block "+str(block_number)+" already analyzed!")
        return status["execution_time"]

    events = []
    try:
        events += w3.eth.filter({"fromBlock": block_number, "toBlock": block_number, "topics": [TRANSFER]}).get_all_entries()
    except Exception as e:
        print(colors.FAIL+"Error: "+str(e)+", block number: "+str(block_number)+colors.END)
        return time.time() - start

    whales = set()
    attackers = set()

    transfer_to = {}
    asset_transfers = {}

    for event in events:
        # Ignore Wrapped ETH and Bancor ETH token transfers
        if (event["address"].lower() != "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2" and
            event["address"].lower() != "0xc0829421c1d260bd3cb3e0f06cfe2d52db2ce315"):

            if event["data"].replace("0x", "") and len(event["topics"]) == 3:
                _from  = Web3.toChecksumAddress("0x"+event["topics"][1].hex().replace("0x", "")[24:64])
                _to    = Web3.toChecksumAddress("0x"+event["topics"][2].hex().replace("0x", "")[24:64])
                _value = int(event["data"].replace("0x", "")[0:64], 16)

                if _value > 0 and _from != _to:
                    if (event["address"]+_from in transfer_to and
                        transfer_to[event["address"]+_from]["transactionIndex"] + 1 < event["transactionIndex"]):

                        event_a1 = transfer_to[event["address"]+_from]
                        event_a2 = event

                        _from_a1  = Web3.toChecksumAddress("0x"+event_a1["topics"][1].hex().replace("0x", "")[24:64])
                        _to_a1    = Web3.toChecksumAddress("0x"+event_a1["topics"][2].hex().replace("0x", "")[24:64])
                        _value_a1 = int(event_a1["data"].replace("0x", "")[0:64], 16)

                        _from_a2  = Web3.toChecksumAddress("0x"+event_a2["topics"][1].hex().replace("0x", "")[24:64])
                        _to_a2    = Web3.toChecksumAddress("0x"+event_a2["topics"][2].hex().replace("0x", "")[24:64])
                        _value_a2 = int(event_a2["data"].replace("0x", "")[0:64], 16)

                        delta = abs(_value_a2 - _value_a1)/max(_value_a2, _value_a1)
                        if delta <= TOKEN_AMOUNT_DELTA:

                            # Search for whale
                            event_w = None
                            for asset_transfer in asset_transfers[event["address"]]:
                                if (transfer_to[event["address"]+_from]["transactionIndex"] < asset_transfer["transactionIndex"] and
                                                                  event["transactionIndex"] > asset_transfer["transactionIndex"] and
                                    asset_transfer["transactionHash"].hex() not in attackers):

                                    _from_w  = Web3.toChecksumAddress("0x"+asset_transfer["topics"][1].hex().replace("0x", "")[24:64])
                                    _to_w    = Web3.toChecksumAddress("0x"+asset_transfer["topics"][2].hex().replace("0x", "")[24:64])
                                    _value_w = int(asset_transfer["data"].replace("0x", "")[0:64], 16)

                                    if _from_a1 == _from_w and _from_w == _to_a2 and _value_w > 0:
                                        event_w = asset_transfer

                            if event_w:
                                whales.add(event_w["transactionHash"].hex())

                                if event_a1["transactionHash"].hex() not in whales and event_a2["transactionHash"].hex() not in whales:
                                    _from_w  = Web3.toChecksumAddress("0x"+event_w["topics"][1].hex().replace("0x", "")[24:64])
                                    _to_w    = Web3.toChecksumAddress("0x"+event_w["topics"][2].hex().replace("0x", "")[24:64])
                                    _value_w = int(event_w["data"].replace("0x", "")[0:64], 16)

                                    tx1      = w3.eth.getTransaction(event_a1["transactionHash"])
                                    whale_tx = w3.eth.getTransaction(event_w["transactionHash"])
                                    tx2      = w3.eth.getTransaction(event_a2["transactionHash"])

                                    if (tx1["from"]     != whale_tx["from"]     and tx2["from"]     != whale_tx["from"] and
                                        tx1["gasPrice"]  > whale_tx["gasPrice"] and tx2["gasPrice"] <= whale_tx["gasPrice"]):

                                        if tx1["to"] == whale_tx["to"] == tx2["to"] and tx1["from"] != tx2["from"]:
                                            continue

                                        # Get token address and name
                                        token_address = event_w["address"]
                                        try:
                                            token_contract = w3.eth.contract(address=token_address, abi=[{"constant":True,"inputs":[],"name":"name","outputs":[{"internalType":"string","name":"","type":"string"}],"payable":False,"stateMutability":"view","type":"function"}])
                                            token_name = token_contract.functions.name().call()
                                        except:
                                            try:
                                                token_contract = w3.eth.contract(address=token_address, abi=[{"name": "name", "outputs": [{"type": "bytes32", "name": "out"}], "inputs": [], "constant": True, "payable": False, "type": "function", "gas": 1623}])
                                                token_name = token_contract.functions.name().call().decode("utf-8").replace(u"\u0000", "")
                                            except:
                                                token_name = token_address

                                        # Get exchange address and name
                                        exchange_address = Web3.toChecksumAddress("0x"+event_w["topics"][1].hex().replace("0x", "")[24:64])
                                        exchange_name = None
                                        # Uniswap V2 and SushiSwap
                                        if not exchange_name:
                                            try:
                                                exchange_contract = w3.eth.contract(address=exchange_address, abi=[{"constant":True,"inputs":[],"name":"name","outputs":[{"internalType":"string","name":"","type":"string"}],"payable":False,"stateMutability":"view","type":"function"}])
                                                exchange_name = exchange_contract.functions.name().call()
                                                if exchange_name.startswith("SushiSwap"):
                                                    exchange_name = "SushiSwap"
                                            except:
                                                pass
                                        # Uniswap V1
                                        if not exchange_name:
                                            try:
                                                exchange_contract = w3.eth.contract(address=exchange_address, abi=[{"name": "name", "outputs": [{"type": "bytes32", "name": "out"}], "inputs": [], "constant": True, "payable": False, "type": "function", "gas": 1623}])
                                                exchange_name = exchange_contract.functions.name().call().decode("utf-8").replace(u"\u0000", "")
                                            except:
                                                pass
                                        # Bancor
                                        if not exchange_name:
                                            try:
                                                exchange_contract = w3.eth.contract(address=exchange_address, abi=[{"constant": True, "inputs": [], "name": "converterType", "outputs": [{"name": "", "type": "string"}], "payable": False, "stateMutability": "view", "type": "function"}])
                                                exchange_name = exchange_contract.functions.converterType().call().capitalize()
                                                if exchange_name.startswith("Bancor"):
                                                    exchange_name = "Bancor"
                                            except:
                                                pass
                                        # Etherscan
                                        if not exchange_name:
                                            try:
                                                response = requests.get("https://api.etherscan.io/api?module=contract&action=getsourcecode&address="+exchange_address+"&apikey="+ETHERSCAN_API_KEY).json()
                                                exchange_name = response["result"][0]["ContractName"]
                                                if exchange_name.startswith("Bancor"):
                                                    exchange_name = "Bancor"
                                            except:
                                                pass
                                        if not exchange_name:
                                            exchange_name = exchange_address

                                        receipt1 = w3.eth.getTransactionReceipt(tx1["hash"])
                                        cost1 = receipt1["gasUsed"]*tx1["gasPrice"]
                                        receipt2 = w3.eth.getTransactionReceipt(tx2["hash"])
                                        cost2 = receipt2["gasUsed"]*tx2["gasPrice"]
                                        total_cost = cost1+cost2

                                        gain = None
                                        eth_spent, eth_received, eth_whale = 0, 0, 0
                                        tx1_event, tx2_event, whale_event = None, None, None
                                        for transfer_event in events:
                                            if   (not tx1_event and transfer_event["transactionHash"] == tx1["hash"] and transfer_event["address"] == "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2" or # Wrapped ETH
                                                  not tx1_event and transfer_event["transactionHash"] == tx1["hash"] and transfer_event["address"] == "0xc0829421C1d260BD3cB3E0F06cfE2D52db2cE315"):  # Bancor ETH Token
                                                tx1_event = transfer_event
                                            elif (not tx2_event and transfer_event["transactionHash"] == tx2["hash"] and transfer_event["address"] == "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2" or # Wrapped ETH
                                                  not tx2_event and transfer_event["transactionHash"] == tx2["hash"] and transfer_event["address"] == "0xc0829421C1d260BD3cB3E0F06cfE2D52db2cE315"):  # Bancor ETH Token
                                                tx2_event = transfer_event
                                            elif (not whale_event and transfer_event["transactionHash"] == whale_tx["hash"] and transfer_event["address"] == "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2" or # Wrapped ETH
                                                  not whale_event and transfer_event["transactionHash"] == whale_tx["hash"] and transfer_event["address"] == "0xc0829421C1d260BD3cB3E0F06cfE2D52db2cE315"):  # Bancor ETH Token
                                                whale_event = transfer_event
                                            if tx1_event and tx2_event and whale_event:
                                                break
                                        if tx1_event and tx2_event and whale_event:
                                            eth_spent = int(tx1_event["data"].replace("0x", "")[0:64], 16)
                                            eth_received = int(tx2_event["data"].replace("0x", "")[0:64], 16)
                                            eth_whale = int(whale_event["data"].replace("0x", "")[0:64], 16)
                                            gain = eth_received - eth_spent
                                        else:
                                            exchange_events = []
                                            exchange_events += w3.eth.filter({"fromBlock": block_number, "toBlock": block_number, "topics": [TOKEN_PURCHASE]}).get_all_entries()
                                            exchange_events += w3.eth.filter({"fromBlock": block_number, "toBlock": block_number, "topics": [ETH_PURCHASE]}).get_all_entries()
                                            for exchange_event in exchange_events:
                                                if   exchange_event["transactionHash"] == tx1["hash"]:
                                                    tx1_event = exchange_event
                                                elif exchange_event["transactionHash"] == tx2["hash"]:
                                                    tx2_event = exchange_event
                                                elif exchange_event["transactionHash"] == whale_tx["hash"]:
                                                    whale_event = exchange_event
                                                if tx1_event and tx2_event and whale_event:
                                                    break
                                            if tx1_event and tx2_event and tx1_event["address"] == tx2_event["address"] and tx1_event["topics"][0].hex() == TOKEN_PURCHASE and tx2_event["topics"][0].hex() == ETH_PURCHASE:
                                                eth_spent = int(tx1_event["topics"][2].hex(), 16)
                                                eth_received = int(tx2_event["topics"][3].hex(), 16)
                                                eth_whale = int(tx1_event["topics"][2].hex(), 16)
                                                gain = eth_received - eth_spent

                                        if gain != None:
                                            attackers.add(event_a1["transactionHash"].hex())
                                            attackers.add(event_a2["transactionHash"].hex())

                                            print("   Index Block Number \t Transaction Hash \t\t\t\t\t\t\t From \t\t\t\t\t\t To \t\t\t\t\t\t Gas Price \t Exchange (Token)")
                                            print("1. "+str(tx1["transactionIndex"])+" \t "+str(tx1["blockNumber"])+" \t "+tx1["hash"].hex()+" \t "+tx1["from"]+" \t "+tx1["to"]+" \t "+str(tx1["gasPrice"]))
                                            print(colors.INFO+"W: "+str(whale_tx["transactionIndex"])+" \t "+str(whale_tx["blockNumber"])+" \t "+whale_tx["hash"].hex()+" \t "+whale_tx["from"]+" \t "+whale_tx["to"]+" \t "+str(whale_tx["gasPrice"])+" \t "+exchange_name+" ("+token_name+")"+colors.END)
                                            print("2. "+str(tx2["transactionIndex"])+" \t "+str(tx2["blockNumber"])+" \t "+tx2["hash"].hex()+" \t "+tx2["from"]+" \t "+tx2["to"]+" \t "+str(tx2["gasPrice"]))

                                            print("Cost: "+str(Web3.fromWei(total_cost, 'ether'))+" ETH")

                                            if gain > 0:
                                                print("Gain: "+str(Web3.fromWei(gain, 'ether'))+" ETH")
                                            else:
                                                print("Gain: -"+str(Web3.fromWei(abs(gain), 'ether'))+" ETH")

                                            profit = gain - total_cost
                                            block = w3.eth.getBlock(block_number)
                                            one_eth_to_usd_price = decimal.Decimal(float(get_one_eth_to_usd(block["timestamp"], prices)))
                                            if profit >= 0:
                                                profit_usd = Web3.fromWei(profit, 'ether') * one_eth_to_usd_price
                                                print(colors.OK+"Profit: "+str(Web3.fromWei(profit, 'ether'))+" ETH ("+str(profit_usd)+" USD)"+colors.END)
                                            else:
                                                profit_usd = -Web3.fromWei(abs(profit), 'ether') * one_eth_to_usd_price
                                                print(colors.FAIL+"Profit: -"+str(Web3.fromWei(abs(profit), 'ether'))+" ETH ("+str(profit_usd)+" USD)"+colors.END)

                                            # Save finding to results
                                            tx1 = dict(tx1)
                                            del tx1["blockNumber"]
                                            del tx1["blockHash"]
                                            del tx1["r"]
                                            del tx1["s"]
                                            del tx1["v"]
                                            tx1["value"] = str(tx1["value"])
                                            tx1["hash"] = tx1["hash"].hex()

                                            whale_tx = dict(whale_tx)
                                            del whale_tx["blockNumber"]
                                            del whale_tx["blockHash"]
                                            del whale_tx["r"]
                                            del whale_tx["s"]
                                            del whale_tx["v"]
                                            whale_tx["value"] = str(whale_tx["value"])
                                            whale_tx["hash"] = whale_tx["hash"].hex()

                                            tx2 = dict(tx2)
                                            del tx2["blockNumber"]
                                            del tx2["blockHash"]
                                            del tx2["r"]
                                            del tx2["s"]
                                            del tx2["v"]
                                            tx2["value"] = str(tx2["value"])
                                            tx2["hash"] = tx2["hash"].hex()

                                            if gain >= 0:
                                                gain = Web3.fromWei(gain, 'ether')
                                            else:
                                                gain = -Web3.fromWei(abs(gain), 'ether')

                                            if profit >= 0:
                                                profit = Web3.fromWei(profit, 'ether')
                                            else:
                                                profit = -Web3.fromWei(abs(profit), 'ether')

                                            interface = "bot"
                                            if (tx1["to"] == whale_tx["to"] == tx2["to"] or
                                                _to_a1 == tx1["from"] and _from_a2 == tx2["from"]):
                                                interface = "exchange"

                                            bot_address = None
                                            if interface == "bot" and _from_a2 == _to_a1:
                                                bot_address = _to_a1

                                            same_sender = False
                                            if tx1["from"] == tx2["from"]:
                                                same_sender = True

                                            same_receiver = False
                                            if tx1["to"] == tx2["to"]:
                                                same_receiver = True

                                            same_token_amount = False
                                            if _value_a1 == _value_a2:
                                                same_token_amount = True

                                            finding = {
                                                "block_number": block_number,
                                                "block_timestamp": block["timestamp"],
                                                "first_transaction": tx1,
                                                "whale_transaction": whale_tx,
                                                "second_transaction": tx2,
                                                "eth_usd_price": float(one_eth_to_usd_price),
                                                "cost_eth": float(Web3.fromWei(total_cost, 'ether')),
                                                "cost_usd": float(Web3.fromWei(total_cost, 'ether') * one_eth_to_usd_price),
                                                "gain_eth": float(gain),
                                                "gain_usd": float(gain * one_eth_to_usd_price),
                                                "profit_eth": float(profit),
                                                "profit_usd": float(profit_usd),
                                                "exchange_address": exchange_address,
                                                "exchange_name": exchange_name,
                                                "token_address": token_address,
                                                "token_name": token_name,
                                                "first_transaction_eth_amount": str(eth_spent),
                                                "whale_transaction_eth_amount": str(eth_whale),
                                                "second_transaction_eth_amount": str(eth_received),
                                                "first_transaction_token_amount": str(_value_a1),
                                                "whale_transaction_token_amount": str(_value_w),
                                                "second_transaction_token_amount": str(_value_a2),
                                                "interface": interface,
                                                "bot_address": bot_address,
                                                "same_sender": same_sender,
                                                "same_receiver": same_receiver,
                                                "same_token_amount": same_token_amount
                                            }
                                            collection = mongo_connection["front_running"]["insertion_results"]
                                            collection.insert_one(finding)
                                            # Indexing...
                                            if 'block_number' not in collection.index_information():
                                                collection.create_index('block_number')
                                                collection.create_index('block_timestamp')
                                                collection.create_index('eth_usd_price')
                                                collection.create_index('cost_eth')
                                                collection.create_index('cost_usd')
                                                collection.create_index('gain_eth')
                                                collection.create_index('gain_usd')
                                                collection.create_index('profit_eth')
                                                collection.create_index('profit_usd')
                                                collection.create_index('exchange_address')
                                                collection.create_index('exchange_name')
                                                collection.create_index('token_address')
                                                collection.create_index('token_name')
                                                collection.create_index('first_transaction_eth_amount')
                                                collection.create_index('whale_transaction_eth_amount')
                                                collection.create_index('second_transaction_eth_amount')
                                                collection.create_index('first_transaction_token_amount')
                                                collection.create_index('whale_transaction_token_amount')
                                                collection.create_index('second_transaction_token_amount')
                                                collection.create_index('interface')
                                                collection.create_index('bot_address')
                                                collection.create_index('same_sender')
                                                collection.create_index('same_receiver')
                                                collection.create_index('same_token_amount')

                    transfer_to[event["address"]+_to] = event
                    if event["address"] not in asset_transfers:
                        asset_transfers[event["address"]] = []
                    asset_transfers[event["address"]].append(event)

    end = time.time()
    collection = mongo_connection["front_running"]["insertion_status"]
    collection.insert_one({"block_number": block_number, "execution_time": end-start})
    # Indexing...
    if 'block_number' not in collection.index_information():
        collection.create_index('block_number')

    return end - start

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
        execution_times += pool.map(analyze_block, range(block_range_start, block_range_end+1))
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
