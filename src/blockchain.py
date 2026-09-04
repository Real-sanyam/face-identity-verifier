"""
web3.py wrapper around the deployed HashRegistry contract: submits a hash +
metadata pointer, then immediately reads it back for independent
re-verification. Also used standalone by scripts/verify_onchain.py.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from web3 import Web3

logger = logging.getLogger(__name__)

ARTIFACT_PATH = Path(__file__).parent.parent / "artifacts" / "HashRegistry.json"
SEPOLIA_CHAIN_ID = 11155111


@dataclass
class OnChainRecord:
    exists: bool
    submitter: str
    timestamp: int
    metadata_uri: str


def _load_artifact() -> dict:
    if not ARTIFACT_PATH.exists():
        raise FileNotFoundError(
            "Contract artifact not found. Run `python contracts/compile.py` first."
        )
    return json.loads(ARTIFACT_PATH.read_text())


def get_web3() -> Web3:
    rpc_url = os.getenv("SEPOLIA_RPC_URL")
    if not rpc_url:
        raise EnvironmentError("SEPOLIA_RPC_URL is not set in the environment (.env).")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        raise ConnectionError(f"Could not connect to Sepolia RPC at {rpc_url}")
    if w3.eth.chain_id != SEPOLIA_CHAIN_ID:
        raise ConnectionError(
            f"RPC is connected to chain {w3.eth.chain_id}, not Sepolia ({SEPOLIA_CHAIN_ID})."
        )
    return w3


def get_contract(w3: Web3):
    contract_address = os.getenv("CONTRACT_ADDRESS")
    if not contract_address:
        raise EnvironmentError(
            "CONTRACT_ADDRESS is not set. Run scripts/deploy_contract.py first."
        )
    artifact = _load_artifact()
    return w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=artifact["abi"])


def register_hash(data_hash_hex: str, metadata_uri: str) -> str:
    """Submits registerHash(dataHash, metadataURI). Returns the tx hash."""
    w3 = get_web3()
    contract = get_contract(w3)

    private_key = os.getenv("WALLET_PRIVATE_KEY")
    if not private_key:
        raise EnvironmentError("WALLET_PRIVATE_KEY is not set in the environment (.env).")
    account = load_account(w3, private_key)

    data_hash_bytes = _parse_hash(data_hash_hex)

    tx = contract.functions.registerHash(data_hash_bytes, metadata_uri).build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "chainId": w3.eth.chain_id,
        }
    )
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        raise RuntimeError(f"registerHash transaction failed: {tx_hash.hex()}")
    logger.info("registerHash confirmed in block %d", receipt.blockNumber)
    return tx_hash.hex()


def verify_hash(data_hash_hex: str) -> OnChainRecord:
    """Read-only call: pulls the record straight from the chain."""
    w3 = get_web3()
    contract = get_contract(w3)
    data_hash_bytes = _parse_hash(data_hash_hex)

    exists, submitter, timestamp, metadata_uri = contract.functions.verifyHash(
        data_hash_bytes
    ).call()
    return OnChainRecord(
        exists=exists, submitter=submitter, timestamp=timestamp, metadata_uri=metadata_uri
    )


def _parse_hash(data_hash_hex: str) -> bytes:
    """Validate that a CLI/API hash is exactly the bytes32 registry key."""
    if not isinstance(data_hash_hex, str):
        raise ValueError("Data hash must be a 0x-prefixed hexadecimal string.")
    normalized = data_hash_hex.removeprefix("0x")
    try:
        raw_hash = bytes.fromhex(normalized)
    except ValueError as exc:
        raise ValueError("Data hash must contain only hexadecimal characters.") from exc
    if len(raw_hash) != 32:
        raise ValueError("Data hash must be exactly 32 bytes (64 hexadecimal characters).")
    return raw_hash


def load_account(w3: Web3, private_key: str):
    """Load a 32-byte key with an actionable error for pasted addresses."""
    try:
        return w3.eth.account.from_key(private_key)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "WALLET_PRIVATE_KEY must be a 32-byte private key (0x + 64 hex characters), "
            "not a 20-byte wallet address. Keep it in .env and never paste it into chat."
        ) from exc
