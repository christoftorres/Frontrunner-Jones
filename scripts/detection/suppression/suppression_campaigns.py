#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import numpy
import decimal
import pymongo
import hashlib
import multiprocessing

from web3 import Web3
from http import client
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from utils.settings import *
from utils.utils import colors, get_prices, get_one_eth_to_usd, request_debug_trace

def get_round_info(campaign, block):
    m = hashlib.sha256()
    m.update(campaign["suppressed_contract_address"].encode('utf-8'))
    round_info = dict()

    try:
        getCurrentRoundInfo_abi = [{"constant":True,"inputs":[],"name":"getCurrentRoundInfo","outputs":[{"name":"","type":"uint256"},{"name":"","type":"uint256"},{"name":"","type":"uint256"},{"name":"","type":"uint256"},{"name":"","type":"uint256"},{"name":"","type":"uint256"},{"name":"","type":"uint256"},{"name":"","type":"address"},{"name":"","type":"bytes32"},{"name":"","type":"uint256"},{"name":"","type":"uint256"},{"name":"","type":"uint256"},{"name":"","type":"uint256"},{"name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"}]
        contract = w3.eth.contract(address=campaign["suppressed_contract_address"], abi=getCurrentRoundInfo_abi)
        info = contract.functions.getCurrentRoundInfo().call(block_identifier=block["number"])
        print("Attacker: "+str(campaign["attacker"]))
        if info[7].lower() == campaign["attacker"].lower():
            print(colors.OK+"Leader: \t "+str(info[7])+colors.END)
        else:
            print(colors.FAIL+"Leader: \t "+str(info[7])+colors.END)
        print()
        print("Player Address:  "+str(info[7]))
        print("Player Name: \t "+str(info[8].decode("utf-8").replace(u"\u0000", "")))
        print("Round ID: \t "+str(info[1]))
        print("Jackpot: \t "+"{:.2f}".format(Web3.fromWei(info[5], 'ether'))+" ETH")
        print("Total Invested:  "+"{:.2f}".format(Web3.fromWei(info[9], 'ether'))+" ETH")
        print("Round Start: \t "+datetime.utcfromtimestamp(info[4]).strftime('%Y-%m-%d %H:%M:%S'))
        print("Round End: \t "+datetime.utcfromtimestamp(info[3]).strftime('%Y-%m-%d %H:%M:%S'))
        print("Timestamp: \t "+datetime.utcfromtimestamp(block["timestamp"]).strftime('%Y-%m-%d %H:%M:%S'))
        print()
        m.update(str(info[1]).encode('utf-8'))
        m.update(str(info[4]).encode('utf-8'))

        round_info["game_leader"] = info[7]
        round_info["game_jackpot"] = float(Web3.fromWei(info[5], 'ether'))
        round_info["game_round_start"] = info[4]
        round_info["game_round_end"] = info[3]
        round_info["game_round_id"] = info[1]

        return round_info, m.digest().hex()[:8], False
    except:
        try:
            getCurrentRoundInfo_2_abi = [{"constant":True,"inputs":[],"name":"getCurrentRoundInfo","outputs":[{"name":"","type":"uint256"},{"name":"","type":"uint256"},{"name":"","type":"uint256"},{"name":"","type":"uint256"},{"name":"","type":"uint256"},{"name":"","type":"uint256"},{"name":"","type":"address"},{"name":"","type":"bytes32"},{"name":"","type":"uint256"},{"name":"","type":"uint256"},{"name":"","type":"uint256"},{"name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"}]
            contract = w3.eth.contract(address=campaign["suppressed_contract_address"], abi=getCurrentRoundInfo_2_abi)
            info = contract.functions.getCurrentRoundInfo().call(block_identifier=block["number"])
            print("Attacker: "+str(campaign["attacker"]))
            if info[6].lower() == campaign["attacker"].lower():
                print(colors.OK+"Leader: \t "+str(info[6])+colors.END)
            else:
                print(colors.FAIL+"Leader: \t "+str(info[6])+colors.END)
            print()
            print("Player Address:  "+str(info[6]))
            print("Round ID: \t "+str(info[0]))
            print("Jackpot: \t "+"{:.2f}".format(Web3.fromWei(info[4], 'ether'))+" ETH")
            print("Round Start: \t "+datetime.utcfromtimestamp(info[3]).strftime('%Y-%m-%d %H:%M:%S'))
            try:
                print("Round End: \t "+datetime.utcfromtimestamp(info[2]).strftime('%Y-%m-%d %H:%M:%S'))
                round_info["game_round_end"] = info[2]
            except:
                round_info["game_round_end"] = None
            print("Timestamp: \t "+datetime.utcfromtimestamp(block["timestamp"]).strftime('%Y-%m-%d %H:%M:%S'))
            print()
            m.update(str(info[0]).encode('utf-8'))
            m.update(str(info[3]).encode('utf-8'))

            round_info["game_leader"] = info[6]
            round_info["game_jackpot"] = float(Web3.fromWei(info[4], 'ether'))
            round_info["game_round_start"] = info[3]
            round_info["game_round_id"] = info[0]

            return round_info, m.digest().hex()[:8], False
        except:
            try:
                # Get round ID
                stuffed_block = w3.eth.getBlock(campaign["last_block"], True)
                round_id = None
                for tx in stuffed_block["transactions"]:
                    if tx["to"] == campaign["bot_address"]:
                        connection = client.HTTPConnection(WEB3_HTTP_RPC_HOST, WEB3_HTTP_RPC_PORT)
                        response = request_debug_trace(connection, tx["hash"].hex())
                        if response and "result" in response:
                            for call in response["result"]:
                                if call["from"].lower() == campaign["bot_address"].lower() and call["to"].lower() == campaign["suppressed_contract_address"].lower() and call["input"].startswith("0x427f0b00"):
                                    round_id = int(call["input"][8:])
                                    break
                        connection.close()
                    if round_id != None:
                        break

                roundInfo_abi = [{"constant":True,"inputs":[{"name":"roundID","type":"uint256"}],"name":"roundInfo","outputs":[{"name":"leader","type":"address"},{"name":"price","type":"uint256"},{"name":"secondaryPrice","type":"uint256"},{"name":"priceMultiplier","type":"uint256"},{"name":"priceIncreasePeriod","type":"uint256"},{"name":"jackpot","type":"uint256"},{"name":"dailyJackpot","type":"uint256"},{"name":"lastDailyJackpot","type":"uint256"},{"name":"shares","type":"uint256"},{"name":"totalInvested","type":"uint256"},{"name":"distributedReturns","type":"uint256"},{"name":"_softDeadline","type":"uint256"},{"name":"finalized","type":"bool"}],"payable":False,"stateMutability":"view","type":"function"}]
                contract = w3.eth.contract(address=campaign["suppressed_contract_address"], abi=roundInfo_abi)
                info = contract.functions.roundInfo(round_id).call(block_identifier=block["number"])
                print("Attacker: "+str(campaign["attacker"]))
                if info[0].lower() == campaign["attacker"].lower():
                    print(colors.OK+"Leader: \t "+str(info[0])+colors.END)
                else:
                    print(colors.FAIL+"Leader: \t "+str(info[0])+colors.END)
                print()
                print("Player Address:  "+str(info[0]))
                print("Block Number: \t "+str(block["number"]))
                print("Jackpot: \t "+"{:.2f}".format(Web3.fromWei(info[5], 'ether'))+" ETH")
                print("Total Invested:  "+"{:.2f}".format(Web3.fromWei(info[9], 'ether'))+" ETH")
                print("Last Jackpot: \t "+datetime.utcfromtimestamp(info[7]).strftime('%Y-%m-%d %H:%M:%S'))
                print("Round End: \t "+datetime.utcfromtimestamp(info[11]).strftime('%Y-%m-%d %H:%M:%S'))
                print("Timestamp: \t "+datetime.utcfromtimestamp(block["timestamp"]).strftime('%Y-%m-%d %H:%M:%S'))
                print("Finalized: \t "+str(info[12]))
                print()
                m.update(str(info[7]).encode('utf-8'))
                round_id = m.digest().hex()[:8]

                round_info["game_leader"] = info[0]
                round_info["game_jackpot"] = float(Web3.fromWei(info[5], 'ether'))
                round_info["game_round_start"] = info[7]
                round_info["game_round_end"] = info[11]
                round_info["game_round_id"] = round_id

                return round_info, round_id, info[11] < block["timestamp"]
            except Exception as e:
                print(str(e)+" \t "+str(campaign["suppressed_contract_address"]))
                pass
    return None, None, None

def finalize_round(round, campaign, force_campaign_end):
    # Find last transaction before block stuffing round began (for a maximum of 100 blocks)
    found = False
    for i in range(0, 1000):
        block = w3.eth.getBlock(round["first_block"] - i, True)
        for tx in reversed(block["transactions"]):
            if tx["to"] and tx["to"].lower() == campaign["suppressed_contract_address"].lower() and tx["value"]:
                tx = dict(tx)
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

                block = w3.eth.getBlock(tx["blockNumber"], False)
                tx["timestamp"] = block["timestamp"]
                one_eth_to_usd = decimal.Decimal(float(get_one_eth_to_usd(block["timestamp"], prices)))

                round["eth_usd_price"] = float(one_eth_to_usd)
                round["costs"] += tx["gasUsed"] * tx["gasPrice"] + tx["value"]
                round["investment_transaction"] = tx

                if "attacker" not in campaign:
                    campaign["attacker"] = tx["from"]

                found = True
                break
        if found:
            break
    if found:
        campaign["last_block"] = round["last_block"]
        campaign["last_block_timestamp"] = round["last_block_timestamp"]

        # Find first transaction after block stuffing round finished (for a maximum of 100 blocks)
        found = False
        previous_round_info, previous_round_id, round_finished = get_round_info(campaign, w3.eth.getBlock(round["last_block"]    , False))
        current_round_info ,  current_round_id, round_finished = get_round_info(campaign, w3.eth.getBlock(round["last_block"] + 1, False))
        campaign_finished = False
        if previous_round_id != current_round_id or round_finished:
            print(colors.INFO+"!!!!! Campaign Finished !!!!!"+colors.END)
            campaign_finished = True
            round["round_info"] = previous_round_info
        else:
            round["round_info"] = current_round_info

        gain = 0
        if campaign_finished:
            for i in range(0, 1000):
                block = w3.eth.getBlock(round["last_block"] + i, True)
                for tx in block["transactions"]:
                    if tx["to"] and tx["to"].lower() == campaign["suppressed_contract_address"].lower() and not tx["value"] and tx["from"].lower() == round["investment_transaction"]["from"].lower():
                        connection = client.HTTPConnection(RPC_HOST, RPC_PORT)
                        response = request_debug_trace(connection, tx["hash"].hex())
                        if response and "result" in response:
                            for call in response["result"]:
                                if call["from"].lower() == campaign["suppressed_contract_address"].lower() and call["to"].lower() == tx["from"].lower() and call["input"] == "0x" and call["value"] > 0:
                                    gain = Web3.fromWei(call["value"], 'ether')
                                    print(colors.FAIL+"Jackpot: "+str(gain)+colors.END)
                                    print(colors.FAIL+"Found at block: "+str(block["number"])+" ("+tx["hash"].hex()+")"+colors.END)
                        connection.close()

                        tx = dict(tx)
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

                        block = w3.eth.getBlock(tx["blockNumber"], False)
                        tx["timestamp"] = block["timestamp"]
                        one_eth_to_usd = decimal.Decimal(float(get_one_eth_to_usd(block["timestamp"], prices)))

                        round["eth_usd_price"] = float(one_eth_to_usd)
                        round["costs"] += tx["gasUsed"] * tx["gasPrice"] + tx["value"]
                        round["withdrawal_transaction"] = tx
                        found = True
                        break
                if found:
                    break

        round["costs_eth"] = Web3.fromWei(round["costs"], 'ether')
        del round["costs"]
        round["costs_usd"] = float(round["costs_eth"] * one_eth_to_usd)
        round["costs_eth"] = float(round["costs_eth"])

        campaign["rounds"].append(round)
        campaign["nr_of_rounds"] = len(campaign["rounds"])
        campaign["nr_of_blocks"] = sum([r["nr_of_blocks"] for r in campaign["rounds"]])
        campaign["nr_of_transactions"] = sum([r["nr_of_transactions"] for r in campaign["rounds"]])
        campaign["eth_usd_price"] = float(one_eth_to_usd)
        campaign["costs_usd"] = float(sum([r["costs_eth"] for r in campaign["rounds"]]) * float(one_eth_to_usd))
        campaign["costs_eth"] = float(sum([r["costs_eth"] for r in campaign["rounds"]]))
        campaign["gain_usd"] = float(gain * one_eth_to_usd)
        campaign["gain_eth"] = float(gain)
        campaign["profit_usd"] = float((campaign["gain_eth"] - campaign["costs_eth"]) * float(one_eth_to_usd))
        campaign["profit_eth"] = float((campaign["gain_eth"] - campaign["costs_eth"]))
        campaign["successful"] = campaign_finished and found and gain > 0

        if campaign_finished or force_campaign_end:
            collection = mongo_connection["front_running"]["suppression_campaigns"]
            collection.insert_one(campaign)
            # Indexing...
            if 'bot_address' not in collection.index_information():
                collection.create_index('bot_address')
                collection.create_index('first_block')
                collection.create_index('first_block_timestamp')
                collection.create_index('last_block')
                collection.create_index('last_block_timestamp')
                collection.create_index('suppressed_contract_address')
                collection.create_index('suppressed_contract_name')
                collection.create_index('attacker')
                collection.create_index('nr_of_rounds')
                collection.create_index('nr_of_blocks')
                collection.create_index('nr_of_transactions')
                collection.create_index('eth_usd_price')
                collection.create_index('costs_usd')
                collection.create_index('costs_eth')
                collection.create_index('gain_usd')
                collection.create_index('gain_eth')
                collection.create_index('profit_usd')
                collection.create_index('profit_eth')
                collection.create_index('successful')
            return True
        return False

def analyze_bot(bot):
    print("Analyzing bot: "+bot)
    start = time.time()
    cursor = mongo_connection["front_running"]["suppression_results"].find({"bot_address": bot}).sort("block_number")
    campaign = None
    round = None
    for document in cursor:
        costs = 0
        for tx in document["transactions"]:
            costs += tx["gasUsed"] * tx["gasPrice"] + tx["value"]
        block = w3.eth.getBlock(document["block_number"], False)
        if campaign == None:
            # Create a new campaign
            campaign = {
                "bot_address": bot,
                "suppressed_contract_address": document["suppressed_contract_address"],
                "suppressed_contract_name": document["suppressed_contract_name"],
                "first_block": document["block_number"],
                "first_block_timestamp": block["timestamp"],
                "last_block": None,
                "last_block_timestamp": None,
                "rounds": [],
                "nr_of_rounds": 0,
                "nr_of_blocks": 0,
                "nr_of_transactions": 0,
                "costs_eth": 0,
                "costs_usd": 0,
                "gain_eth": 0,
                "gain_usd": 0,
                "profit_eth": 0,
                "profit_usd": 0,
            }
        if round == None:
            # Create a new round
            round = {
                "first_block": document["block_number"],
                "first_block_timestamp": block["timestamp"],
                "last_block": document["block_number"],
                "last_block_timestamp": block["timestamp"],
                "blocks": [document["block_number"]],
                "nr_of_blocks": 1,
                "nr_of_transactions": len(document["transactions"]),
                "costs": costs,
            }
            print(document["suppressed_contract_name"]+" \t "+document["suppressed_contract_address"])
            print(document["block_number"])
        else:
            # Add to existing round
            if (document["block_number"] == round["last_block"] + 1):
                round["last_block"] = document["block_number"]
                round["last_block_timestamp"] = block["timestamp"]
                round["blocks"].append(document["block_number"])
                round["nr_of_blocks"] += 1
                round["nr_of_transactions"] += len(document["transactions"])
                round["costs"] += costs
                print(document["block_number"])
            # Round finished
            else:
                campaign_finished = finalize_round(round, campaign, False)
                print()

                if campaign_finished:
                    # Create a new campaign
                    campaign = {
                        "bot_address": bot,
                        "suppressed_contract_address": document["suppressed_contract_address"],
                        "suppressed_contract_name": document["suppressed_contract_name"],
                        "first_block": document["block_number"],
                        "first_block_timestamp": block["timestamp"],
                        "last_block": None,
                        "last_block_timestamp": None,
                        "rounds": [],
                        "nr_of_rounds": 0,
                        "nr_of_blocks": 0,
                        "nr_of_transactions": 0,
                        "costs_eth": 0,
                        "costs_usd": 0,
                        "gain_eth": 0,
                        "gain_usd": 0,
                        "profit_eth": 0,
                        "profit_usd": 0,
                    }

                # Create a new round
                round = {
                    "first_block": document["block_number"],
                    "first_block_timestamp": block["timestamp"],
                    "last_block": document["block_number"],
                    "last_block_timestamp": block["timestamp"],
                    "blocks": [document["block_number"]],
                    "nr_of_blocks": 1,
                    "nr_of_transactions": len(document["transactions"]),
                    "costs": costs,
                }
                print(document["suppressed_contract_name"]+" \t "+document["suppressed_contract_address"])
                print(document["block_number"])

    # End existing round
    if round:
        finalize_round(round, campaign, True)
        print()
    return time.time() - start

def init_process(prices):
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
    mongo_connection = pymongo.MongoClient("mongodb://"+MONGO_HOST+":"+str(MONGO_PORT), maxPoolSize=None)

    execution_times = []
    prices = get_prices()
    multiprocessing.set_start_method('fork')
    print("Running detection of insertion frontrunning attacks with "+str(multiprocessing.cpu_count())+" CPUs")
    print("Initializing workers...")
    with multiprocessing.Pool(processes=multiprocessing.cpu_count(), initializer=init_process, initargs=(prices,)) as pool:
        start_total = time.time()
        bot_addresses = mongo_connection["front_running"]["suppression_results"].distinct("bot_address")
        print("Number of bots: "+str(len(bot_addresses)))
        execution_times += pool.map(analyze_bot, bot_addresses)
        end_total = time.time()
        print("Total execution time: "+str(end_total - start_total))
        print("Found "+str(mongo_connection["front_running"]["suppression_campaigns"].count_documents({}))+" suppression campaigns.")
        print()
        if execution_times:
            print("Max execution time: "+str(numpy.max(execution_times)))
            print("Mean execution time: "+str(numpy.mean(execution_times)))
            print("Median execution time: "+str(numpy.median(execution_times)))
            print("Min execution time: "+str(numpy.min(execution_times)))

if __name__ == "__main__":
    main()
