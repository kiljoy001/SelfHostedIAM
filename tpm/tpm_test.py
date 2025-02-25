from tpm2_pytss import ESAPI, TPM2_ALG

class TPMManager:
    def __init__(self):
        self.esapi = ESAPI()
        self._init_tpm()

    def _init_tpm(self):
        # Create persistent signing key
        self.esapi.create_primary(None, "owner", {"algorithm": TPM2_ALG.SHA256})
        self.esapi.create(
            None,
            {
                "algorithm": TPM2_ALG.ECC,
                "keyBits": 256,
                "scheme": TPM2_ALG.ECDSA
            },
            "null", None, None, None
        )
        self.esapi.evictcontrol("owner", self.esapi.tr_from_tpmpublic(0x81010001))

    def sign(self, data):
        return self.esapi.sign(
            0x81010001,
            data,
            TPM2_ALG.SHA256,
            TPM2_ALG.ECDSA
        )

if __name__ == '__main__':
    manager = TPMManager()
    message = "Hello World!"
    data = message.encode("utf-8")
    signature = manager.sign(data)
    print(f"Signature: {signature}")
