# app.py (Updated)
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
import sqlite3
import hashlib
import subprocess
from merkletools import MerkleTools
import ipfshttpclient
from tpm2_pytss import ESAPI, TPM2_ALG
from yggdrasilctl import AdminAPI, APIError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec



app = Flask(__name__)
auth = HTTPBasicAuth()

# Configuration
CONFIG = {
    "emercoin_rpc": "http://user:pass@localhost:6662",
    "ipfs_cluster": ["/ip4/127.0.0.1/tcp/9094"],
    "yggdrasil_peers": ["tcp://public.peer1.yggdrasil.io:80"],
    "tpm_persistent_handle": 0x81010001
}


class TPMManager:
    def __init__(self, tcti=None):
        self.esys = ESAPI(tcti)
        self.signing_key = self._create_primary_key()

    def _create_primary_key(self):
        in_public = TPM2B_PUBLIC(
            publicArea=TPMT_PUBLIC(
                type=TPM2_ALG.ECC,
                nameAlg=TPM2_ALG.SHA256,
                objectAttributes=(
                    TPMA_OBJECT.USERWITHAUTH
                    | TPMA_OBJECT.SIGN_ENCRYPT
                    | TPMA_OBJECT.FIXEDTPM
                    | TPMA_OBJECT.FIXEDPARENT
                    | TPMA_OBJECT.SENSITIVEDATAORIGIN
                ),
                parameters=TPMU_PUBLIC_PARMS(
                    eccDetail=TPMS_ECC_PARMS(
                        symmetric=TPMT_SYM_DEF_OBJECT(algorithm=TPM2_ALG.NULL),
                        scheme=TPMT_ECC_SCHEME(
                            scheme=TPM2_ALG.ECDSA,
                            details=TPMU_ASYM_SCHEME(
                                ecdsa=TPMS_SCHEME_HASH(hashAlg=TPM2_ALG.SHA256)
                            ),
                        ),
                        curveID=TPM2_ECC_CURVE.NIST_P256,
                        kdf=TPMT_KDF_SCHEME(scheme=TPM2_ALG.NULL),  # Corrected
                    )
                ),
                unique=TPMU_PUBLIC_ID(
                    ecc=TPMS_ECC_POINT(
                        x=TPM2B_ECC_PARAMETER(b""),
                        y=TPM2B_ECC_PARAMETER(b""),
                    )
                ),
            )
        )

        signing_key, public, _, _, _ = self.esys.create_primary(
            TPM2B_SENSITIVE_CREATE(),
            in_public,
            ESYS_TR.OWNER,
            TPM2B_DATA(),
            TPML_PCR_SELECTION(),
        )
        self.public_key = public
        return signing_key

    def sign_data(self, data, block_size=4096):
        hash_sequence = self.esys.hash_sequence_start(
            auth=TPM2B_AUTH(), hash_alg=TPM2_ALG.SHA256
        )

        for i in range(0, len(data), block_size):
            block = data[i : i + block_size]
            self.esys.sequence_update(hash_sequence, TPM2B_MAX_BUFFER(block))

        digest, validation_ticket = self.esys.sequence_complete(
            hash_sequence, buffer=None, hierarchy=ESYS_TR.OWNER
        )

        # Use ECDSA scheme
        signature = self.esys.sign(
            self.signing_key,
            digest,
            in_scheme=TPMT_SIG_SCHEME(
                scheme=TPM2_ALG.ECDSA,
                details=TPMU_SIG_SCHEME(
                    ecdsa=TPMS_SCHEME_HASH(hashAlg=TPM2_ALG.SHA256)
                ),
            ),
            validation=validation_ticket,
        )

        # Extract ECDSA signature
        if signature.sigAlg == TPM2_ALG.ECDSA:
            r = bytes(signature.signature.ecdsa.signatureR.buffer)
            s = bytes(signature.signature.ecdsa.signatureS.buffer)
            raw_signature = r + s
        else:
            raise ValueError("Unsupported algorithm")

        return raw_signature

    def get_public_key_pem(self):
    # Ensure the key is ECC (NIST P-256)
        if self.public_key.publicArea.type != TPM2_ALG.ECC:
            raise ValueError("Unsupported key type: Only ECC is supported")

        # Extract x and y coordinates from the TPM's public key
        ecc_point = self.public_key.publicArea.unique.ecc
        x = int.from_bytes(ecc_point.x.buffer, byteorder="big")
        y = int.from_bytes(ecc_point.y.buffer, byteorder="big")

        # Create an ECC public key object
        public_numbers = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1())
        public_key = public_numbers.public_key()

        # Serialize to PEM
        pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return pem

    def close(self):
        if self.signing_key:
            self.esys.flush_context(self.signing_key)
        self.esys.close()



class YggdrasilNetwork:
    def __init__(self):
        self.node = yggdrasil.Node()
        self.node.start(peers=CONFIG["yggdrasil_peers"])

    @property
    def address(self):
        return self.node.get_address()

    def send(self, dest, data):
        return self.node.send(dest, json.dumps(data).encode())

    def receive(self):
        return json.loads(self.node.receive().decode())


class IdentitySystem:
    def __init__(self):
        self.tpm = TPMManager()
        self.ygg = YggdrasilNetwork()
        self.mt = MerkleTools()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect('identities.db') as db:
            db.execute('''CREATE TABLE IF NOT EXISTS identities
                        (id TEXT PRIMARY KEY,
                         pubkey TEXT,
                         signature TEXT,
                         ipfs_cid TEXT,
                         yggdrasil_ip TEXT)''')

    def create_identity(self):
        # Generate identity data
        pubkey = self.tpm.esapi.get_public(CONFIG["tpm_persistent_handle"])
        data = os.urandom(32)
        signature = self.tpm.sign(data)

        # Store to IPFS
        with ipfshttpclient.connect() as ipfs:
            cid = ipfs.add_json({
                "pubkey": pubkey,
                "signature": signature,
                "data": data.hex()
            })

        # Get Yggdrasil IP
        ygg_ip = self.ygg.address

        # Store record
        with sqlite3.connect('identities.db') as db:
            db.execute('INSERT INTO identities VALUES (?, ?, ?, ?, ?)',
                       (cid, pubkey, signature.hex(), cid, ygg_ip))

        return cid

    def anchor_to_blockchain(self):
        # Build Merkle tree
        with sqlite3.connect('identities.db') as db:
            cursor = db.execute('SELECT * FROM identities')
            for row in cursor:
                leaf = hashlib.sha256(json.dumps(dict(row)).encode()).hexdigest()
                self.mt.add_leaf(leaf)

        self.mt.make_tree()
        merkle_root = self.mt.get_merkle_root()

        # Store to Emercoin
        subprocess.run([
            'emercoin-cli', 'name_new', 'id:merkle_root',
            json.dumps({"root": merkle_root}),
            '3600', '""', '""', 'SIGN=TPMKey'
        ])

        return merkle_root

    def verify_identity(self, cid):
        # Get record from DB
        with sqlite3.connect('identities.db') as db:
            row = db.execute('SELECT * FROM identities WHERE id=?', (cid,)).fetchone()

        # Verify Merkle proof
        leaf = hashlib.sha256(json.dumps(dict(row)).encode()).hexdigest()
        proof = self.mt.get_proof(self.mt.leaves.index(leaf))

        # Verify via Yggdrasil network
        response = self.ygg.send(row['yggdrasil_ip'], {
            'action': 'verify',
            'challenge': os.urandom(32).hex()
        })

        return self.mt.validate_proof(proof, leaf, self.mt.merkle_root) and response['valid']


# Authentication for admin interface
users = {
    "admin": generate_password_hash(os.getenv("ADMIN_PASSWORD", "securepassword"))
}


@auth.verify_password
def verify_password(username, password):
    if username in users and check_password_hash(users.get(username), password):
        return username


# REST API Endpoints
@app.route('/api/v1/verify', methods=['POST'])
def api_verify():
    data = request.json
    if not data or 'cid' not in data:
        return jsonify({"error": "Missing CID"}), 400

    system = IdentitySystem()
    valid = system.verify_identity(data['cid'])
    return jsonify({
        "valid": valid,
        "timestamp": int(time.time())
    })


@app.route('/api/v1/identities/<cid>')
def api_get_identity(cid):
    system = IdentitySystem()
    with sqlite3.connect('identities.db') as db:
        row = db.execute('SELECT * FROM identities WHERE id=?', (cid,)).fetchone()

    if not row:
        return jsonify({"error": "Identity not found"}), 404

    return jsonify({
        "cid": row[0],
        "yggdrasil_ip": row[4],
        "created_at": row[5],
        "merkle_proof": system.mt.get_proof(row[0])
    })


@app.route('/api/v1/merkle-root')
def api_merkle_root():
    system = IdentitySystem()
    return jsonify({
        "root": system.anchor_to_blockchain(),
        "block": subprocess.check_output(['emercoin-cli', 'getblockcount']).decode().strip()
    })


# Admin Interface
@app.route('/admin')
@auth.login_required
def admin_dashboard():
    system = IdentitySystem()

    # System Stats
    with sqlite3.connect('identities.db') as db:
        total_identities = db.execute('SELECT COUNT(*) FROM identities').fetchone()[0]
        last_identity = db.execute('SELECT * FROM identities ORDER BY created_at DESC LIMIT 1').fetchone()

    # Blockchain Info
    blockchain_info = json.loads(subprocess.check_output([
        'emercoin-cli', 'getblockchaininfo'
    ]).decode())

    # Yggdrasil Peers
    ygg_peers = subprocess.check_output(['yggdrasil', '-getpeers']).decode().splitlines()

    return render_template('admin.html',
                           total_identities=total_identities,
                           last_identity=last_identity,
                           blockchain_info=blockchain_info,
                           ygg_peers=ygg_peers)


@app.route('/admin/anchor', methods=['POST'])
@auth.login_required
def admin_anchor():
    system = IdentitySystem()
    root = system.anchor_to_blockchain()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/create', methods=['POST'])
@auth.login_required
def admin_create():
    system = IdentitySystem()
    cid = system.create_identity()
    return redirect(url_for('admin_dashboard'))


if __name__ == '__main__':
    app.run(host='::', port=5000, threaded=True)