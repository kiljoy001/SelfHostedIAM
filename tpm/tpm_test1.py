from tpm2_pytss import *
from tpm2_pytss.types import *
import base64


class TPMManager:
    def __init__(self, tcti=None):
        self.esys = ESAPI(tcti)
        self.signing_key = self._create_primary_key()

    def _create_primary_key(self):
        # Define the public template for an RSA2048 signing key using RSASSA with SHA-256
        in_public = TPM2B_PUBLIC(
            publicArea=TPMT_PUBLIC(
                type=TPM2_ALG.RSA,
                nameAlg=TPM2_ALG.SHA256,
                objectAttributes=(
                    TPMA_OBJECT.USERWITHAUTH |
                    TPMA_OBJECT.SIGN_ENCRYPT |
                    TPMA_OBJECT.FIXEDTPM |
                    TPMA_OBJECT.FIXEDPARENT |
                    TPMA_OBJECT.SENSITIVEDATAORIGIN
                ),
                parameters=TPMU_PUBLIC_PARMS(
                    rsaDetail=TPMS_RSA_PARMS(
                        symmetric=TPMT_SYM_DEF_OBJECT(algorithm=TPM2_ALG.NULL),
                        scheme=TPMT_RSA_SCHEME(
                            scheme=TPM2_ALG.RSASSA,
                            details=TPMU_ASYM_SCHEME(
                                rsassa=TPMS_SCHEME_HASH(hashAlg=TPM2_ALG.SHA256)
                            )
                        ),
                        keyBits=2048,
                        exponent=0
                    )
                ),
                unique=TPMU_PUBLIC_ID(
                    rsa=TPM2B_PUBLIC_KEY_RSA(bytes(256))  # Placeholder, TPM generates the key
                )
            )
        )

        # Create the primary key under the owner hierarchy with empty auth
        signing_key, _, _, _, _ = self.esys.create_primary(
            TPM2B_SENSITIVE_CREATE(),
            in_public,
            ESYS_TR.OWNER,  # positional
            TPM2B_DATA(),  # positional
            TPML_PCR_SELECTION()  # positional
        )
        return signing_key

    def sign_data(self, data, block_size=4096):
        # Start a hash sequence with SHA-256
        hash_sequence = self.esys.hash_sequence_start(
            auth=TPM2B_AUTH(),
            hash_alg=TPM2_ALG.SHA256
        )

        # Process data in specified blocks
        for i in range(0, len(data), block_size):
            block = data[i:i + block_size]
            self.esys.sequence_update(
                hash_sequence,
                TPM2B_MAX_BUFFER(block)
            )

        # Complete the hash sequence to get the digest and validation ticket
        digest, validation_ticket = self.esys.sequence_complete(
            hash_sequence,
            buffer=None,
            hierarchy=ESYS_TR.OWNER
        )

        # Sign the digest using the primary key
        signature = self.esys.sign(
            self.signing_key,
            digest,
            in_scheme=TPMT_SIG_SCHEME(
                scheme=TPM2_ALG.RSASSA,
                details=TPMU_SIG_SCHEME(rsassa=TPMS_SCHEME_HASH(hashAlg=TPM2_ALG.SHA256))
            ),
            validation=validation_ticket
        )
         # Extract raw bytes from the TPMT_SIGNATURE
        if signature.sigAlg == TPM2_ALG.RSASSA:
            raw_signature = bytes(signature.signature.rsassa.sig.buffer)
        else:
            raise ValueError("Unsupported signature algorithm")


        return raw_signature

    def close(self):
        # Clean up resources
        if self.signing_key:
            self.esys.flush_context(self.signing_key)
        self.esys.close()

if __name__ == '__main__':
    manager = TPMManager()
    message = "Hello World!"
    data = message.encode("utf-8")
    signature = manager.sign_data(data)
    hex_sig = signature.hex()
    b64_sig = base64.b64encode(signature).decode()
    print(f"Signature: {hex_sig},")
    print(f"b64 Signature: {b64_sig}")
