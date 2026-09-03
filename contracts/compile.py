"""
Compiles contracts/HashRegistry.sol and writes the ABI + bytecode to
artifacts/HashRegistry.json.

Run once (or whenever the contract source changes):
    python contracts/compile.py
"""
import json
from pathlib import Path

import solcx

SOLC_VERSION = "0.8.24"
CONTRACT_PATH = Path(__file__).parent / "HashRegistry.sol"
ARTIFACT_PATH = Path(__file__).parent.parent / "artifacts" / "HashRegistry.json"


def main():
    installed = solcx.get_installed_solc_versions()
    if SOLC_VERSION not in [str(v) for v in installed]:
        print(f"Installing solc {SOLC_VERSION} ...")
        solcx.install_solc(SOLC_VERSION)
    solcx.set_solc_version(SOLC_VERSION)

    source = CONTRACT_PATH.read_text()
    compiled = solcx.compile_source(
        source,
        output_values=["abi", "bin"],
        solc_version=SOLC_VERSION,
    )
    contract_id, contract_interface = next(iter(compiled.items()))

    ARTIFACT_PATH.parent.mkdir(exist_ok=True)
    ARTIFACT_PATH.write_text(
        json.dumps(
            {
                "abi": contract_interface["abi"],
                "bytecode": contract_interface["bin"],
            },
            indent=2,
        )
    )
    print(f"Compiled {CONTRACT_PATH.name} -> {ARTIFACT_PATH}")


if __name__ == "__main__":
    main()
