"""
Deploys HashRegistry to Sepolia and writes the resulting address into .env
as CONTRACT_ADDRESS.

Run once, after contracts/compile.py:
    python scripts/deploy_contract.py
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv, set_key
from web3 import Web3

ARTIFACT_PATH = Path(__file__).parent.parent / "artifacts" / "HashRegistry.json"
ENV_PATH = Path(__file__).parent.parent / ".env"
SEPOLIA_CHAIN_ID = 11155111


def main():
    load_dotenv(ENV_PATH)

    rpc_url = os.getenv("SEPOLIA_RPC_URL")
    private_key = os.getenv("WALLET_PRIVATE_KEY")
    if not rpc_url or not private_key:
        raise EnvironmentError("Set SEPOLIA_RPC_URL and WALLET_PRIVATE_KEY in .env first.")

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        raise ConnectionError(f"Could not connect to {rpc_url}")
    if w3.eth.chain_id != SEPOLIA_CHAIN_ID:
        raise ConnectionError(
            f"RPC is connected to chain {w3.eth.chain_id}, not Sepolia ({SEPOLIA_CHAIN_ID})."
        )

    if not ARTIFACT_PATH.exists():
        raise FileNotFoundError("Contract artifact not found. Run `python contracts/compile.py` first.")

    artifact = json.loads(ARTIFACT_PATH.read_text())
    account = w3.eth.account.from_key(private_key)

    contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
    tx = contract.constructor().build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "chainId": w3.eth.chain_id,
        }
    )
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"Deploying... tx: {tx_hash.hex()}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1 or not receipt.contractAddress:
        raise RuntimeError(f"Contract deployment failed: {tx_hash.hex()}")
    address = receipt.contractAddress
    print(f"Deployed HashRegistry at {address} (block {receipt.blockNumber})")

    set_key(str(ENV_PATH), "CONTRACT_ADDRESS", address)
    print("Wrote CONTRACT_ADDRESS to .env")


if __name__ == "__main__":
    main()
