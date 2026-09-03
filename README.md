# Face Identity Verifier

This is a consent-based, command-line verification pipeline for finding a
public post that contains your face and recording tamper-evident evidence of
that match on the Ethereum Sepolia testnet.

It is intended only for verifying your own face and accounts, or material for
which you have explicit permission. It is not a tool for identifying other
people or for searching accounts without consent.

## Pipeline

```text
local reference face image
          |
          v
DeepFace: detect + ArcFace encode
          |
          v
live post discovery
  - X/Twitter v2 user timeline API (optional), or
  - SerpApi Google Lens visual search (default live-search path)
          |
          v
DeepFace: compare each discovered post image
          |
          v
canonical evidence JSON -> SHA-256 -> HashRegistry on Sepolia
          |
          v
read the chain record back and later re-verify the evidence file
```

The pipeline will only anchor a result obtained from a live post discovery
step. Profile photos and manually listed `direct_images` are labelled as
comparison-only and cannot independently reach the blockchain stage.

## What it does

1. `src/face_match.py` detects a face in `--face` and creates an ArcFace
   embedding with DeepFace. It compares every candidate post image using the
   same model and DeepFace's verified threshold.
2. `src/profile_search.py` can use the official X/Twitter v2 API to retrieve
   photo posts from accounts you explicitly configure. It checks actual post
   URLs, not profile avatars.
3. `src/reverse_image_search.py` performs a genuine Google Lens visual search
   through SerpApi when `SERPAPI_KEY` is set. By default it uploads the local
   `--face` image to SerpApi and filters results to individual public social
   post URL shapes (X, Instagram, Facebook, TikTok, YouTube, LinkedIn, and
   Reddit). No result is hardcoded.
4. `src/records.py` produces canonical evidence JSON. It contains the matched
   image SHA-256, post URL, discovery method, match score, and hashes of any
   post text/title. The actual face embedding and raw post text are not put on
   chain.
5. `src/blockchain.py` hashes that canonical JSON, registers it through
   `HashRegistry`, waits for the Sepolia receipt, and reads the contract back
   to prove the stored metadata is byte-for-byte identical.

## Blockchain

The project uses the **Ethereum Sepolia testnet** and the small custom
`contracts/HashRegistry.sol` contract. The contract stores a SHA-256 `bytes32`
key, the submitter, the block timestamp, and the canonical metadata JSON. It
does not allow an existing hash to be overwritten. The client rejects an RPC
endpoint that is not Sepolia (chain ID `11155111`).

Sepolia records are public and tamper-evident, but the testnet has no legal,
financial, or notarization value.

## Setup

Use Python 3.10 through 3.12 and a throwaway Sepolia wallet only.

```bash
git clone <your-GitHub-repository-URL>
cd face-identity-verifier
python -m venv .venv
```

Activate the environment, then install dependencies.

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
Copy-Item config\profiles.example.yaml config\profiles.yaml
```

```bash
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp config/profiles.example.yaml config/profiles.yaml
```

Set the following values in `.env`:

| Variable | Required | Purpose |
| --- | --- | --- |
| `SEPOLIA_RPC_URL` | yes for the blockchain stage | A Sepolia RPC endpoint. |
| `WALLET_PRIVATE_KEY` | yes for deployment/registration | A funded, throwaway Sepolia wallet. Never use a mainnet key. |
| `CONTRACT_ADDRESS` | after deployment | Filled by the deploy script. |
| `SERPAPI_KEY` | one live-search option | Enables Google Lens local-image visual search. |
| `TWITTER_BEARER_TOKEN` | optional | Enables discovery of photo posts on configured X/Twitter accounts. |

At least one live discovery option is needed: `SERPAPI_KEY`, or an X/Twitter
bearer token together with an account listed in `profiles.yaml`.

### Compile and deploy the contract

```bash
python contracts/compile.py
python scripts/deploy_contract.py
```

The deploy script checks that its RPC is Sepolia, waits for a successful
receipt, and writes `CONTRACT_ADDRESS` into `.env`.

### Run the end-to-end pipeline

```bash
python pipeline.py --face path/to/your_face.jpg --profiles config/profiles.yaml
```

Google Lens uploads local JPG, JPEG, PNG, or WebP files up to 500 KB. For a
larger image, first make it available at a URL you control and pass it
explicitly:

```bash
python pipeline.py --face path/to/your_face.jpg \
  --reverse-image-url https://example.org/your_face.jpg
```

On a verified match, the command prints the Sepolia transaction, saves the
canonical evidence as `records/<hash>.json`, submits it, and immediately
re-reads the on-chain record. `records/` is git-ignored because it is runtime
evidence rather than source code.

## Independent re-verification

Anyone with the RPC URL and contract address can verify an evidence record
without a private key:

```bash
python scripts/verify_onchain.py --metadata records/<hash>.json
```

This recomputes the SHA-256 from the evidence JSON, reads that exact key from
Sepolia, and checks that the metadata stored by the contract is identical. If
you save a byte-identical copy of the matched post image, verify its content
fingerprint as well:

```bash
python scripts/verify_onchain.py --metadata records/<hash>.json --image saved-post-image.jpg
```

You may use `--hash 0x...` for a lookup-only chain read, but `--metadata` is
the full data-to-chain verification path.

## Tests

```bash
pytest -q
```

The unit tests are network-free and do not download a DeepFace model or send
a blockchain transaction. A genuine end-to-end run still needs the credentials
and testnet ETH described above.

## Known limitations

- Face-match scores are probabilistic. Lighting, age, pose, compression, and
  lookalikes can cause false positives or negatives. Treat a verified match as
  evidence to review, not proof of identity.
- Google Lens results depend on its current index. A missing result does not
  prove that a post does not exist. The SerpApi upload is short-lived, but it
  still sends your image to a third-party provider; use it only with informed
  consent.
- The X/Twitter endpoint is subject to the account's API tier, post visibility,
  and media availability. Other platforms are discovered through Google Lens
  rather than scraped directly.
- The post URL can later disappear or the platform can transform its image.
  The on-chain record proves the exact evidence metadata and image fingerprint
  observed at verification time; it cannot guarantee continued availability.
- No website is included. This project is intentionally a CLI pipeline.

## License

MIT. See [LICENSE](LICENSE).
