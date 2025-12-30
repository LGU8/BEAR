from datetime import datetime


def now14() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")
