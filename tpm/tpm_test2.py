from tpm2_pytss import *
from tpm2_pytss.types import *
import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

class TPMManager:
    def __init__(self, tcti=None):
        self.esys = ESAPI(tcti)
        self.signing_key = self._create_signing_key()

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
            ESYS_TR.ENDORSEMENT,
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
            hash_sequence, buffer=None, hierarchy=ESYS_TR.ENDORSEMENT
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

if __name__ == "__main__":
    manager = TPMManager()
    message = "Hello World!"
    data = message.encode("utf-8")
    signature = manager.sign_data(data)
    hex_sig = signature.hex()
    b64_sig = base64.b64encode(signature).decode()
    public_pem = manager.get_public_key_pem()
    print(f"Signature: {hex_sig}")
    print(f"Base64: {b64_sig}")
    print(f"Public Key (PEM):\n{public_pem.decode()}")
    manager.close()