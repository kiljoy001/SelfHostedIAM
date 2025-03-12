from helper.script_runner import ScriptRunner
from pathlib import Path

REGISTERED_SCRIPTS = {
    "tpm_provision" : Path("/app/tpm_provisioning.sh"),
    "generate_cert" : Path("/app/tpm_self_signed_cert.sh"),
    "random_number" : Path("/app/tpm_random_number.sh")
}
def print_dictionary(d):
    for key in d:
        print(f"{key}:{d[key]}")


if __name__ == '__main__':
    
    runner = ScriptRunner(REGISTERED_SCRIPTS)
    provision_result = runner.execute("tpm_provision")
    generate_cert_result = runner.execute("generate_cert")
    random_number_result = runner.execute("random_number")

    print_dictionary(provision_result)
    print_dictionary(generate_cert_result)
    print_dictionary(random_number_result)


