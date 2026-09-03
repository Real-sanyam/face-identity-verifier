// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title HashRegistry
/// @notice A minimal tamper-evident registry: anyone can register a
///         SHA-256 fingerprint of some off-chain data (here, a confirmed
///         face-match record) along with a pointer to that data. Once
///         written, a record cannot be altered or deleted, and anyone can
///         independently re-verify it by reading the contract.
contract HashRegistry {
    struct Record {
        address submitter;
        uint256 timestamp;
        string metadataURI; // free-form pointer/description of the data that was hashed
        bool exists;
    }

    mapping(bytes32 => Record) private records;

    event HashRegistered(
        bytes32 indexed dataHash,
        address indexed submitter,
        uint256 timestamp,
        string metadataURI
    );

    /// @notice Register a new fingerprint. Reverts if this exact hash was
    ///         already registered, so records can't be silently overwritten.
    function registerHash(bytes32 dataHash, string calldata metadataURI) external {
        require(!records[dataHash].exists, "HashRegistry: hash already registered");

        records[dataHash] = Record({
            submitter: msg.sender,
            timestamp: block.timestamp,
            metadataURI: metadataURI,
            exists: true
        });

        emit HashRegistered(dataHash, msg.sender, block.timestamp, metadataURI);
    }

    /// @notice Read back a registered record for independent re-verification.
    function verifyHash(bytes32 dataHash)
        external
        view
        returns (bool exists, address submitter, uint256 timestamp, string memory metadataURI)
    {
        Record storage r = records[dataHash];
        return (r.exists, r.submitter, r.timestamp, r.metadataURI);
    }
}
