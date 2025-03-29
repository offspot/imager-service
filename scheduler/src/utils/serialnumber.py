import base64


def get_check_digit(number: int) -> int:
    return number % 37


def to_b32(number: int, nb_bytes=2) -> str:
    return (
        base64.b32encode(number.to_bytes(nb_bytes, byteorder="little"))
        .decode("ASCII")
        .replace(nb_bytes * "==", "")
    )


def from_b32(text: str) -> int:
    nb_chars = len(text)
    padding = (8 - nb_chars) * "="
    return int.from_bytes(base64.b32decode(text + padding), byteorder="little")


def encode_serial(number: int) -> str:
    check_digit = get_check_digit(number)

    b32_number = to_b32(number)
    b32_check_digit = to_b32(check_digit, nb_bytes=1)
    separator = ""
    return f"{b32_number}{separator}{b32_check_digit}"


def decode_serial(text: str) -> int:
    try:
        text = text.upper()
        serial_text, check_text = text[:-2], text[-2:]

        check_digit = from_b32(check_text)
        number = from_b32(serial_text)
        if get_check_digit(number) == check_digit:
            return number
    except Exception as exc:
        return -1

    return -1


def is_valid_serial(text: str) -> bool:
    """ whether string is a valid S/N"""
    number = decode_serial(text)
    try:
        sn = encode_serial(number)
    except Exception:
        return False
    return text == sn and number >= 1024
