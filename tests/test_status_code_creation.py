# test_status_code_creation.py
from opc import status_codes
from opcua.ua import StatusCode
from opc.status_codes import StatusCodeHex

# Проверка создания StatusCode из HEX
print("Проверка создания StatusCode из HEX значений:")

status_good = StatusCode(StatusCodeHex.GOOD)
print(f"✅ Good: {status_good} (value={status_good.value})")

status_uncertain = StatusCode(StatusCodeHex.UNCERTAIN)
print(f"✅ Uncertain: {status_uncertain} (value={status_uncertain.value})")

status_uncertain_last = StatusCode(StatusCodeHex.UNCERTAIN_LAST_USABLE_VALUE)
print(f"✅ Uncertain_LastUsableValue: {status_uncertain_last} (value={status_uncertain_last.value})")

status_bad = StatusCode(StatusCodeHex.BAD)
print(f"✅ Bad: {status_bad} (value={status_bad.value})")

status_bad_timeout = StatusCode(StatusCodeHex.BAD_TIMEOUT)
print(f"✅ Bad_Timeout: {status_bad_timeout} (value={status_bad_timeout.value})")

print("\n✅ Все StatusCode создаются корректно!")