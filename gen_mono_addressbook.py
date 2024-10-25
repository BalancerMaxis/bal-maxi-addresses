#### Note this script has to run from the monorepo. It's just here until we figure out how to create a source of truth
#### that doesn't need this file and/or something like it is provided in the monorepo

### It generates addressbook.json

import os
import re
import json
from pathlib import Path
from typing import Dict
from bal_addresses import AddrBook
from bal_tools import Web3Rpc
import requests
from collections import defaultdict, OrderedDict
from typing import Dict


DEPLOYMENTS_ADDRESS_ROOT_URL = "https://raw.githubusercontent.com/balancer/balancer-deployments/refs/heads/master/addresses/"


def main():
    # Get deployments
    results = process_deloyments_json()
    # Create a pointer to the active part of the deployments
    active = results["active"]
    with open("outputs/deployments.json", "w") as f:
        json.dump(results, f, indent=2)
    ### Add extras
    for chain in active.keys():
        with open("extras/multisigs.json", "r") as f:
            data = json.load(f)
            data = data.get(chain, {})
            data = AddrBook.checksum_address_dict(data)
        if "multisigs" not in active[chain].keys():
            active[chain]["multisigs"] = {}
        for multisig, address in data.items():
            active[chain]["multisigs"][multisig] = address
        ### add signers
        if "EOA" not in active[chain].keys():
            active[chain]["EOA"] = {}
        with open("extras/signers.json", "r") as f:
            data = json.load(f)
            data = AddrBook.checksum_address_dict(data)
            active[chain]["EOA"] = data
        ### add pools
        if "pools" not in active[chain]:
            active[chain]["pools"] = {}
        with open("outputs/pools.json", "r") as f:
            data = json.load(f)
            data = data.get(chain, {})
            data = AddrBook.checksum_address_dict(data)
            active[chain]["pools"] = data
        ### add gauges
        if "gauges" not in active[chain]:
            active[chain]["gauges"] = {}
        with open("outputs/gauges.json", "r") as f:
            data = json.load(f)
            data = data.get(chain, {})
            data = AddrBook.checksum_address_dict(data)
            active[chain]["gauges"] = data
        ### add extras
        try:
            with open(f"extras/{chain}.json") as f:
                data = json.load(f)
                data = AddrBook.checksum_address_dict(data)
        except:
            data = {}
        active[chain] = data | active[chain]
        ### add injectors
        injectors = process_v2_injectors(chain)

        active[chain].setdefault("maxiKeepers", {}).setdefault("injectorV2", {})[
            "deployed"
        ] = injectors
        with open("outputs/addressbook.json", "w") as f:
            json.dump(results, f, indent=2)


def process_deloyments_json():
    results = {"active": defaultdict(dict), "deprecated": defaultdict(dict)}

    for chain in AddrBook.chain_ids_by_name.keys():
        try:
            r = requests.get(f"{DEPLOYMENTS_ADDRESS_ROOT_URL}{chain}.json")
            r.raise_for_status()
            data = r.json()
        except:
            print(f"Error fetching deployments for {chain}")

        for deployment_name, deployment in data.items():
            status = deployment["status"].lower()
            if status in ["script"]:
                continue
            contracts = deployment["contracts"]
            for contract in contracts:
                address = contract["address"]
                name = contract["name"]
                results[status].setdefault(chain, {}).setdefault(deployment_name, {})[
                    name
                ] = address
    ## Old method had chains alphabetized
    results["active"] = OrderedDict(sorted(results["active"].items()))
    return results


def process_v2_injectors(chain) -> Dict[str, str]:
    """
    Add injector V2's to the addressbook from the factory
    Will first use any injectors defined in extras.maxiKeepers.injectorV2.injectors
    If that is not defined, it will try to fetch all injectors from the factory and get info for naming that way
    """
    try:
        f = open("extras/v2injectors_override.json", "r")
        override_data = json.load(f)
        override_data = override_data.get(chain, {})
    except Exception as e:
        print(f"No extras/v2injectors_override.json file found: {e}")
        override_data = {}

    a = AddrBook(chain)
    results = {}
    try:
        factory = a.extras.maxiKeepers.injectorV2.factory
    except:
        print(f"No V2 Injector factory found for {a.chain}")
        return {}
    factory_abi = json.load(open("bal_addresses/abis/InjectorV2Factory.json"))
    logic_abi = json.load(open("bal_addresses/abis/InjectorV2Logic.json"))
    erc20_abi = json.load(open("bal_addresses/abis/ERC20.json"))
    ## try to get a list of all injectors from the factory
    w3 = Web3Rpc(chain, os.getenv("DRPC_KEY"))
    try:
        injectors = (
            w3.eth.contract(address=factory, abi=factory_abi)
            .functions.getDeployedInjectors()
            .call()
        )
    except:
        print(f"Error fetching injectors from factory {factory}")
        return {}
    for injector_address in injectors:
        if injector_address in override_data.keys():
            injector_name = override_data[injector_address]
        else:
            logic = w3.eth.contract(address=injector_address, abi=logic_abi)
            reward_token = logic.functions.InjectTokenAddress().call()
            try:
                token_interface = w3.eth.contract(address=reward_token, abi=erc20_abi)
                reward_token = token_interface.functions.symbol().call()
            except:
                print(
                    f"Can't connect to token {a.chain}{reward_token} to resolve name for injector scheduling. Using address."
                )
            injector_name = f"{reward_token}_{injector_address[-6:]}"
        results[injector_address] = injector_name
    return results


if __name__ == "__main__":
    main()
