from tpm2_pytss import *
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature
import sys

def test_tpm_operations():
    try:
        # 1. Test TPM connection
        ctx = ESAPI()
        print("✓ TPM connection established")

        # 2. Test EK creation
        ek_handle = ctx.create_primary(
            ESYS_TR.ENDORSEMENT, 
            TPM2B_PUBLIC(tpmt_public=TPMT_PUBLIC(
                type=TPM2_ALG.ECC,
                nameAlg=TPM2_ALG.SHA256,
                objectAttributes=TPMA_OBJECT.RESTRICTED|TPMA_OBJECT.DECRYPT,
                parameters=TPMU_PUBLIC_PARMS(
                    eccDetail=TPMS_ECC_PARMS(
                        curveID=TPM2_ECC_CURVE.NIST_P256
                    )
                )
            ))
        )[0]
        print("✓ Endorsement Key created")

        # 3. Test signing key creation
        signing_key = ctx.create(
            ek_handle,
            TPM2B_SENSITIVE_CREATE(),
            TPM2B_PUBLIC(tpmt_public=TPMT_PUBLIC(
                type=TPM2_ALG.ECC,
                nameAlg=TPM2_ALG.SHA256,
                objectAttributes=TPMA_OBJECT.SIGN_ENCRYPT,
                parameters=TPMU_PUBLIC_PARMS(
                    eccDetail=TPMS_ECC_PARMS(
                        scheme=TPMT_ECC_SCHEME(scheme=TPM2_ALG.ECDSA),
                        curveID=TPM2_ECC_CURVE.NIST_P256
                    )
                )
            )
        )
        )
        print("✓ Signing key created")

        # 4. Test signing/verification
        message = b"TPM Test Message"
        digest = hashes.Hash(hashes.SHA256())
        digest.update(message)
        hashed = digest.finalize()
        
        signature = ctx.sign(
            signing_key,
            TPM2B_DIGEST(hashed),
            TPMT_SIG_SCHEME(scheme=TPM2_ALG.ECDSA)
        )
        print("✓ Data signed successfully")

        # 5. Verify signature externally
        public_key = ctx.read_public(signing_key)[1]
        ecc_pub = public_key.publicArea.unique.ecc
        x = int.from_bytes(ecc_pub.x.buffer, "big")
        y = int.from_bytes(ecc_pub.y.buffer, "big")
        
        verifier = ec.EllipticCurvePublicNumbers(
            x, y, ec.SECP256R1()
        ).public_key().verifier(
            signature.signature.ecdsa.signatureR.buffer + 
            signature.signature.ecdsa.signatureS.buffer,
            ec.ECDSA(hashes.SHA256())
        )
        
        verifier.update(message)
        verifier.verify()
        print("✓ Signature verified externally")

        return 0
    except Exception as e:
        print(f"! Test failed: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(test_tpm_operations())