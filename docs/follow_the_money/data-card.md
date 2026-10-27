# Data card

The source manifest is `config/follow_the_money/manifest.json`; the acquisition
allowlist is `sources.json`. Every acquired data artifact has URL, licence or
terms status, retrieval timestamp, byte count and SHA-256. Raw downloads,
recordings, model weights and local case databases are under ignored `data/`.
Do not commit them. Dependencies/tool caches use the task's prescribed toolchain
directories; development-tool/schema receipts are distinguished from evidence.

| Source | Acquired/used | Limits |
|---|---|---|
| Authored fixture worlds | Frozen fictional BTC/TRON transactions, labels, freeze event and branch/stop tasks | No real individuals or wrongdoing; variant graphs are isomorphic |
| Ransomwhere 1.1.0, Zenodo 13999026 | CC BY 4.0, 5,572,091 bytes; 11,178 parsed Bitcoin seed rows | Published seed assertions, not ownership findings; attribution retained |
| GraphSense TagPacks | Pinned MIT-licensed two-address Binance pack and licence | Historical assertions; no current-control guarantee |
| OFAC crypto address snapshot | Pinned public BTC 532 / TRON 261 addresses | Published assertions; mirror snapshot may lag current OFAC data |
| OpenSanctions CryptoWallet | Typed adapter and authored fixture only | Current terms/use permission not established; no download |
| Bitcoin mempool.space | Genesis plus cited 2025 funding/spending/outspends/address-page recordings | Seven physical public GETs total; rate-limited, cached; replay makes zero live calls |
| TronGrid / TronScan | API-shaped authored transfers and historical USDT event | No key/live verification; different schemas and pagination tested |
| DOJ Colonial 2021 affidavit | 411,664 bytes; rendered pages inspected | Full addresses redacted, no txids; excluded from gold endpoint denominator |
| DOJ 2025 civil filing | 1,308,900 bytes; affidavit page 13, paragraphs 35–38, figures 1–2 | One exact publicly cited hop; allegations are not findings |
| Elliptic++ | Access/licence metadata inspected, no data downloaded | No verified permission covering selected downloadable files |
| Elliptic2 | Metadata inspected, no dataset downloaded | 25,805,701,153 bytes, above approved 2 GB; CC BY-NC-ND terms need review |

Gold annotations are `gold-traces.json`. Full txids and exact outpoints are
recorded only when present in published evidence and verified against the
explorer response. The 2025 filing's abbreviated address suffix and narrative
intermediary discrepancy are documented; no extra hop is invented. Neither
private account identities nor investigator profile details are imported.

Source licence/term receipts are for the specific acquisition, not a blanket
permission for every source file or future use. Published wallet labels retain
source provenance and conflict rather than forcing one asserted owner.
Ransomwhere citation/attribution: [dataset release](https://zenodo.org/records/13999026).
[GraphSense TagPacks](https://github.com/graphsense/graphsense-tagpacks) provide
source packs; the exact pinned subset and licence hashes are in the manifest.
[Colonial affidavit](https://www.justice.gov/archives/opa/press-release/file/1402056/dl?inline)
and [2025 filing](https://www.justice.gov/usao-ma/media/1390101/dl?inline=) are
public US federal documents, used as cited historical evidence.

Memory contains approved research hypotheses and analyst opinions. Corrected
cases/clusters are excluded from recall. Deletion is a tombstone preserving
historical audit data, not physical erasure. API keys are operator secrets;
only hashes belong in the local key file, never in source or receipts.
