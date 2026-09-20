ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]

TENS = [
    "", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"
]


def convert_two_digits(num: int) -> str:
    if num == 0:
        return ""
    if num < 20:
        return ONES[num]
    ten = num // 10
    rem = num % 10
    ten_word = TENS[ten]
    rem_word = ONES[rem]
    return ten_word if rem == 0 else f"{ten_word} {rem_word}"


def convert_three_digits(num: int) -> str:
    hundred = num // 100
    rem = num % 100
    if hundred == 0:
        return convert_two_digits(rem)
    hundred_str = f"{ONES[hundred]} Hundred"
    if rem == 0:
        return hundred_str
    return f"{hundred_str} {convert_two_digits(rem)}"


def amount_to_indian_words(amount: float | int | None) -> str:
    """
    Converts numeric amount into standard Indian currency words (Crore, Lakh, Thousand, Hundred)
    Matching standard Indian GST challan / invoice formats.
    Example: 13902.00 -> 'Thirteen Thousand Nine Hundred Two Only'
    """
    if amount is None or amount == 0:
        return "Zero Only"

    val = abs(float(amount))
    int_part = int(val)
    decimal_part = round((val - int_part) * 100)

    parts: list[str] = []
    rem = int_part

    crore = rem // 10000000
    rem %= 10000000

    lakh = rem // 100000
    rem %= 100000

    thousand = rem // 1000
    rem %= 1000

    hundred_and_below = rem

    if crore > 0:
        parts.append(f"{convert_three_digits(crore)} Crore")
    if lakh > 0:
        parts.append(f"{convert_three_digits(lakh)} Lakh")
    if thousand > 0:
        parts.append(f"{convert_three_digits(thousand)} Thousand")
    if hundred_and_below > 0:
        parts.append(convert_three_digits(hundred_and_below))

    words = " ".join(parts).strip()
    if decimal_part > 0:
        paise_str = convert_two_digits(decimal_part)
        words = f"{words} and {paise_str} Paise" if words else f"{paise_str} Paise"

    return f"{words} Only" if words else "Zero Only"
