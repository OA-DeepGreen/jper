import random
import string


def create_random_id(n_char=10) -> str:
    s = string.ascii_letters + string.digits
    return ''.join(random.choices(s, k=n_char))


